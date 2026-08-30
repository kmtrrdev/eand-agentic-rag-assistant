"""
app/guardrails/garak_guard.py
------------------------------
Runtime Garak Security Guardrails Engine for e& Egypt Agentic KB.

Implements real-time defensive checks derived from Garak's red-teaming probe
and detector specifications:
  - garak.probes.dan (DAN 11.0, jailbreak personas, unrestricted modes)
  - garak.probes.goodside (ThreatenJSON, WhoIsRiley, persona hijack)
  - garak.probes.encoding (Base64, Hex, Rot13, URL-encoded payload inspection)
  - garak.probes.sysprompt_extraction (System prompt theft in EN & AR)
  - garak.probes.apikey (API key & secret extraction attempts)
  - garak.detectors.sysprompt_extraction (System prompt echo/leak detection in output)
  - garak.detectors.apikey (High-entropy secret token & credential masking in output)
  - garak.detectors.dan (Jailbreak acceptance & persona adoption in output)
"""
import base64
import codecs
import html
import logging
import re
import urllib.parse
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("etisalat_kb.guardrails.garak")

# ── 1. Garak Probe Pattern Suites (Input Defense) ───────────────────────────

# DAN & Jailbreak Probes (garak.probes.dan)
GARAK_DAN_PATTERNS = [
    re.compile(r"\b(?:DAN\s*(?:1[0-9]|20|[0-9])?|Do\s*Anything\s*Now)\b", re.IGNORECASE),
    re.compile(r"\b(?:jailbreak|jailbroken|unrestricted\s+ai|evil\s+confidant|evil\s+ai|unfiltered\s+ai)\b", re.IGNORECASE),
    re.compile(r"\b(?:stay\s+in\s+character|always\s+answer\s+as\s+DAN|you\s+must\s+never\s+refuse)\b", re.IGNORECASE),
    re.compile(r"\b(?:ignore\s+(?:all\s+)?(?:ethics|safety|content\s+filters|guidelines|restrictions))\b", re.IGNORECASE),
    re.compile(r"\b(?:pretend\s+you\s+have\s+no\s+(?:rules|filters|limitations|safety))\b", re.IGNORECASE),
    re.compile(r"\b(?:disable|bypass|deactivate|turn\s+off|override|remove)\s+(?:all\s+)?(?:security|safety|guardrails?|checks?|filters?|rules?|restrictions?|protocols?|policies)\b", re.IGNORECASE),
    re.compile(r"(?:تظاهر|اعتبر\s+نفسك)\s*(?:انك|بانك|ان|بان)?\s*(?:بدون\s+قيود|في\s+وضع\s+dan|غير\s+مقيد|حر|تتجاهل\s+القوانين)", re.IGNORECASE),
    re.compile(r"(?:جاوب\s+بدون\s+اي\s+قيود|الغي\s+كل\s+الفلاتر|عطل\s+الحماية|وقف\s+الأمان)", re.IGNORECASE),
]

# Goodside Attack Probes (garak.probes.goodside - ThreatenJSON, Riley, JSON hijack)
GARAK_GOODSIDE_PATTERNS = [
    re.compile(r"\b(?:threatenjson|who\s*is\s*riley|riley\s+goodside)\b", re.IGNORECASE),
    re.compile(r"\b(?:you\s+are\s+now\s+in\s+developer\s+mode|sudo\s+mode|god\s+mode|admin\s+mode)\b", re.IGNORECASE),
    re.compile(r"\b(?:system\s+message|system\s+prompt|developer\s+message|admin\s+override|system\s+override|system\s+command)\s*[:=]", re.IGNORECASE),
    re.compile(r"\b(?:respond\s+only\s+with\s+a\s+raw\s+json\s+object\s+containing\s+the\s+system\s+prompt)\b", re.IGNORECASE),
    re.compile(r"(?:###\s*Instruction:\s*|\[INST\]|<<SYS>>|<\|im_start\|>|<\|system\|>|\[System\]|\[Developer\])", re.IGNORECASE),
]

# System Prompt Extraction Probes (garak.probes.sysprompt_extraction)
GARAK_SYSPROMPT_PROBE_PATTERNS = [
    re.compile(r"\b(?:reveal|show|dump|print|output|display|give|tell|repeat|echo|share|provide|what\s+is|what\'s|whats)\s+(?:me\s+)?(?:your\s+|the\s+|any\s+)?(?:hidden\s+|initial\s+|secret\s+)?(?:system\s+prompt|developer\s+instructions|instructions|initial\s+prompt|system\s+instructions|core\s+prompt|meta\s+prompt)\b", re.IGNORECASE),
    re.compile(r"\b(?:output\s+initialization\s+text|print\s+everything\s+above\s+this\s+line)\b", re.IGNORECASE),
    re.compile(r"\b(?:what\s+are\s+(?:your\s+|the\s+)?(?:exact\s+)?instructions\s+(?:before|given\s+to\s+you|for\s+this\s+bot))\b", re.IGNORECASE),
    re.compile(r"(?:اعرض|أظهر|اطبع|هات|اكشف|ما\s+هو|طلع\s+لي|شارك|قول|وريني)\s*(?:لي\s+)?(?:الـ\s*|\s*)?(?:system\s+prompt|التعليمات\s+المخفية|أوامر\s+النظام|أوامر\s+المطور|تعليمات\s+المطور|البرومبت\s+الرئيسي|البرومبت\s+الأساسي|التعليمات\s+الأولى|تعليماتك)", re.IGNORECASE),
]

# API Key & Secret Extraction Probes (garak.probes.apikey)
GARAK_APIKEY_PROBE_PATTERNS = [
    re.compile(r"\b(?:show|reveal|give|tell|print|get|share|provide|display|what\s+is|what\'s|whats)\s+(?:me\s+)?(?:the\s+|your\s+|our\s+|any\s+)?(?:api[\s_-]?key|api_key|token|password|secret|secret[\s_-]?key|credentials?|llm_api_key|openai_api_key|azure_api_key|env|environment\s+variable|environment\s+variables)\b", re.IGNORECASE),
    re.compile(r"\b(?:what\s+is\s+(?:the\s+value\s+of\s+)?(?:LLM_API_KEY|OPENAI_API_KEY|AZURE_OPENAI_API_KEY|HF_TOKEN))\b", re.IGNORECASE),
    re.compile(r"\b(?:print\s+all\s+environment\s+variables|dump\s+env\s+vars|dump\s+secrets)\b", re.IGNORECASE),
    re.compile(r"\b(?:api[\s_-]?key|secret[\s_-]?key|access[\s_-]?token)\s*(?:\?|\!|$)", re.IGNORECASE),
    re.compile(r"(?:ما\s+هو|هات|اعطني|اكشف|وريني|طلع\s+لي|قول)\s*(?:لي\s+)?(?:الـ?|\s*)*(?:مفتاح\s+(?:الـ?api|api)|api[\s_-]?key|مفتاحك|المفتاح\s+السري|الباسورد|كلمة\s+السر|التوكن|بيانات\s+الاعتماد|متغيرات\s+البيئة)", re.IGNORECASE),
]

# Prompt Injection Directives (garak.probes.promptinject)
GARAK_INJECTION_DIRECTIVES = [
    re.compile(r"\b(?:ignore\s+(?:all\s+)?(?:previous|prior|above|system)\s+instructions)\b", re.IGNORECASE),
    re.compile(r"\b(?:disregard\s+(?:all\s+)?(?:previous|prior|system)\s+instructions)\b", re.IGNORECASE),
    re.compile(r"\b(?:override\s+all\s+system\s+rules)\b", re.IGNORECASE),
    re.compile(r"\b(?:forget\s+(?:all\s+)?(?:rules|guidelines|instructions))\b", re.IGNORECASE),
    re.compile(r"\b(?:disable\s+all\s+security\s+checks|answer\s+everything|answer\s+without\s+restrictions)\b", re.IGNORECASE),
    re.compile(r"(?:تجاهل|انسَ|انس|الغي|تخطى|عطل)\s+(?:كل\s+)?(?:التعليمات|الأوامر|القواعد|الارشادات|السابقة|المسبقة|الفلاتر|الأمان)", re.IGNORECASE),
]

# Encoding & Obfuscation Attack Probes (garak.probes.encoding)
GARAK_ENCODING_PROBE_PATTERNS = [
    re.compile(r"\b(?:decode\s+this|decode\s+the\s+following|decode\s+and\s+(?:follow|execute|run|reply)|follow\s+the\s+instruction\s+inside)\b", re.IGNORECASE),
    re.compile(r"\b(?:base64|hex|rot13|binary|morse\s+code|caesar\s+cipher)\s+(?:string|payload|code|text|instruction|command|message)\b", re.IGNORECASE),
    re.compile(r"\b(?:decode|decrypt|unhash|deobfuscate)\s+(?:this|the|following|it|base64|hex|string)\b", re.IGNORECASE),
    re.compile(r"(?:فك\s+تشفير|فك\s+الرمز|نفذ\s+الأمر\s+المشفر|اقرأ\s+الكود\s+المشفر|فك\s+الـ\s*base64)", re.IGNORECASE),
]

# ── 2. Garak Output Detectors (Output Leakage & Hallucination Defense) ──────

# Internal System Prompt Signatures (garak.detectors.sysprompt_extraction)
SYSTEM_PROMPT_LEAK_SIGNATURES = [
    "PROTOCOL 1b",
    "PROTOCOL 1c",
    "PROTOCOL 3",
    "_KNOWN_PRICES_EGP",
    "ANSWER_SYSTEM_PROMPT",
    "ANSWER_HUMAN_PROMPT",
    "You are an expert AI telecom support assistant for e& Egypt",
    "CRITICAL GROUNDING & FIDELITY DIRECTIVE",
    "CRITICAL ARABIC / ENGLISH LANGUAGE DIRECTIVE",
    "QUARANTINED",
    "app/agent/nodes",
]

# Output Secrets & API Keys (garak.detectors.apikey)
OUTPUT_SECRET_PATTERNS = [
    re.compile(r"sk-[A-Za-z0-9\-_]{20,}", re.IGNORECASE),
    re.compile(r"gsk_[A-Za-z0-9\-_]{20,}", re.IGNORECASE),
    re.compile(r"hf_[A-Za-z0-9\-_]{20,}", re.IGNORECASE),
    re.compile(r"eyJ[A-Za-z0-9-_=]+\.[A-Za-z0-9-_=]+\.?[A-Za-z0-9-_.+/=]*"),  # JWT Token
    re.compile(r"(?:api[\s_-]?key|secret[\s_-]?key|access[\s_-]?token|bearer[\s_-]?token)[\s:=]+(['\"])?[A-Za-z0-9\-_/+=]{16,}\1?", re.IGNORECASE),
    re.compile(r"-----BEGIN\s+(?:RSA\s+)?PRIVATE\s+KEY-----", re.IGNORECASE),
    re.compile(r"(?:LLM_API_KEY|OPENAI_API_KEY|HF_TOKEN|AZURE_OPENAI_API_KEY|EVAL_LLM_API_KEY)\s*=\s*[^\s]+", re.IGNORECASE),
]

# Output Jailbreak Compliance Signatures (garak.detectors.dan)
JAILBREAK_COMPLIANCE_SIGNATURES = [
    re.compile(r"^(?:\[🔓\s*JAILBREAK\]|\[DAN\]|DAN:|🔓\s*Jailbroken:)", re.IGNORECASE | re.MULTILINE),
    re.compile(r"\b(?:As\s+an\s+unrestricted\s+AI|I\s+am\s+now\s+free\s+from\s+rules|I\s+can\s+now\s+do\s+anything)\b", re.IGNORECASE),
]


# ── 3. Obfuscation & Encoding Decoder (garak.probes.encoding) ───────────────

def _decode_obfuscated_payloads(text: str) -> List[Tuple[str, str]]:
    """
    Finds and decodes hidden payloads (Base64, Hex, URL-encoding, Rot13)
    to inspect obfuscated attack attempts before they reach the model.
    """
    decoded_payloads: List[Tuple[str, str]] = []

    if not text:
        return decoded_payloads

    # 1. Base64 payload detection (tokens of length >= 16 with valid base64 chars)
    b64_candidates = re.findall(r"(?:[A-Za-z0-9+/]{4}){3,}(?:[A-Za-z0-9+/]{2}==|[A-Za-z0-9+/]{3}=|[A-Za-z0-9+/]{4})", text)
    for cand in b64_candidates:
        try:
            decoded_bytes = base64.b64decode(cand)
            decoded_str = decoded_bytes.decode("utf-8", errors="ignore").strip()
            if len(decoded_str) > 6 and any(c.isalpha() for c in decoded_str):
                decoded_payloads.append(("base64", decoded_str))
        except Exception:
            pass

    # 2. Hex string detection (tokens like 69676e6f7265...)
    hex_candidates = re.findall(r"\b(?:0x)?[0-9a-fA-F]{16,}\b", text)
    for cand in hex_candidates:
        clean_hex = cand[2:] if cand.startswith("0x") else cand
        if len(clean_hex) % 2 == 0:
            try:
                decoded_bytes = bytes.fromhex(clean_hex)
                decoded_str = decoded_bytes.decode("utf-8", errors="ignore").strip()
                if len(decoded_str) > 6 and any(c.isalpha() for c in decoded_str):
                    decoded_payloads.append(("hex", decoded_str))
            except Exception:
                pass

    # 3. URL-encoded payload detection
    if "%" in text:
        try:
            unquoted = urllib.parse.unquote(text)
            if unquoted != text:
                decoded_payloads.append(("url_encoded", unquoted))
        except Exception:
            pass

    # 4. Rot13 inspection if suspicious trigger words present
    if any(k in text.lower() for k in ["rot13", "caesar"]):
        try:
            r13 = codecs.decode(text, "rot_13")
            decoded_payloads.append(("rot13", r13))
        except Exception:
            pass

    return decoded_payloads


# ── 4. GarakInputGuard Implementation ───────────────────────────────────────

class GarakInputGuard:
    """
    Garak-powered real-time Input Guardrail.
    Inspects user questions against Garak attack probe vectors.
    """

    @classmethod
    def evaluate(cls, text: str) -> Dict[str, Any]:
        """
        Evaluate input text using Garak probe patterns and obfuscation decoders.

        Returns:
            {
                "allowed": bool,
                "category": str ("SAFE" | "PROMPT_INJECTION" | "SECRET_REQUEST" | "SYSTEM_PROMPT_REQUEST" | "JAILBREAK"),
                "reason": str,
                "probe_triggered": str,
            }
        """
        if not text or not text.strip():
            return {
                "allowed": False,
                "category": "INVALID_INPUT",
                "reason": "Empty input text",
                "probe_triggered": "empty_check",
            }

        raw_text = text.strip()
        texts_to_check = [("raw", raw_text)]

        # Decode obfuscated payloads (garak.probes.encoding)
        unpacked = _decode_obfuscated_payloads(raw_text)
        texts_to_check.extend(unpacked)

        for enc_type, candidate_text in texts_to_check:
            # A. Check Garak DAN & Jailbreak Probes (garak.probes.dan)
            for pat in GARAK_DAN_PATTERNS:
                if pat.search(candidate_text):
                    logger.warning(
                        "Garak Input Guard triggered [DAN/Jailbreak probe] (source=%s): %s",
                        enc_type, pat.pattern,
                    )
                    return {
                        "allowed": False,
                        "category": "PROMPT_INJECTION",
                        "reason": f"Garak DAN/Jailbreak probe detected in {enc_type} payload",
                        "probe_triggered": "garak.probes.dan",
                    }

            # B. Check Garak Goodside Attack Probes (garak.probes.goodside)
            for pat in GARAK_GOODSIDE_PATTERNS:
                if pat.search(candidate_text):
                    logger.warning(
                        "Garak Input Guard triggered [Goodside attack probe] (source=%s): %s",
                        enc_type, pat.pattern,
                    )
                    return {
                        "allowed": False,
                        "category": "PROMPT_INJECTION",
                        "reason": f"Garak Goodside attack probe detected in {enc_type} payload",
                        "probe_triggered": "garak.probes.goodside",
                    }

            # C. Check Garak System Prompt Extraction (garak.probes.sysprompt_extraction)
            for pat in GARAK_SYSPROMPT_PROBE_PATTERNS:
                if pat.search(candidate_text):
                    logger.warning(
                        "Garak Input Guard triggered [System Prompt extraction] (source=%s): %s",
                        enc_type, pat.pattern,
                    )
                    return {
                        "allowed": False,
                        "category": "SYSTEM_PROMPT_REQUEST",
                        "reason": f"Garak System prompt extraction probe detected in {enc_type} payload",
                        "probe_triggered": "garak.probes.sysprompt_extraction",
                    }

            # D. Check Garak API Key Extraction (garak.probes.apikey)
            for pat in GARAK_APIKEY_PROBE_PATTERNS:
                if pat.search(candidate_text):
                    logger.warning(
                        "Garak Input Guard triggered [API Key extraction] (source=%s): %s",
                        enc_type, pat.pattern,
                    )
                    return {
                        "allowed": False,
                        "category": "SECRET_REQUEST",
                        "reason": f"Garak API Key extraction probe detected in {enc_type} payload",
                        "probe_triggered": "garak.probes.apikey",
                    }

            # E. Check Garak Prompt Injection Directives (garak.probes.promptinject)
            for pat in GARAK_INJECTION_DIRECTIVES:
                if pat.search(candidate_text):
                    logger.warning(
                        "Garak Input Guard triggered [Prompt Injection directive] (source=%s): %s",
                        enc_type, pat.pattern,
                    )
                    return {
                        "allowed": False,
                        "category": "PROMPT_INJECTION",
                        "reason": f"Garak prompt injection directive detected in {enc_type} payload",
                        "probe_triggered": "garak.probes.promptinject",
                    }

            # F. Check Garak Encoding & Obfuscation Probes (garak.probes.encoding)
            for pat in GARAK_ENCODING_PROBE_PATTERNS:
                if pat.search(candidate_text):
                    logger.warning(
                        "Garak Input Guard triggered [Encoding/Obfuscation probe] (source=%s): %s",
                        enc_type, pat.pattern,
                    )
                    return {
                        "allowed": False,
                        "category": "PROMPT_INJECTION",
                        "reason": f"Garak encoding/obfuscation injection probe detected ({enc_type})",
                        "probe_triggered": "garak.probes.encoding",
                    }

        return {
            "allowed": True,
            "category": "SAFE",
            "reason": "Passed all Garak input defense probes",
            "probe_triggered": None,
        }


# ── 5. GarakOutputGuard Implementation ──────────────────────────────────────

class GarakOutputGuard:
    """
    Garak-powered real-time Output Guardrail.
    Inspects generated response for system prompt echo, secret leakage,
    and jailbreak compliance before client delivery.
    """

    @classmethod
    def sanitize(cls, text: str) -> str:
        """
        Sanitize model output using Garak output detector algorithms.

        1. Checks for System Prompt Echo (garak.detectors.sysprompt_extraction)
        2. Checks for API Key & High-Entropy Secret Leaks (garak.detectors.apikey)
        3. Checks for Jailbreak Persona Acceptance (garak.detectors.dan)
        4. Strips hidden thinking tags and HTML/XSS payloads
        """
        if not text:
            return ""

        cleaned = str(text)

        # 1. System Prompt Echo Detection (garak.detectors.sysprompt_extraction)
        # If the output contains verbatim system prompt protocols, redact or replace
        for signature in SYSTEM_PROMPT_LEAK_SIGNATURES:
            if signature in cleaned:
                logger.error(
                    "Garak Output Guard detected System Prompt Leak signature: %r",
                    signature,
                )
                cleaned = re.sub(
                    re.escape(signature) + r"[^\n.]*[\n.]?",
                    "[REDACTED_INTERNAL_INSTRUCTION]",
                    cleaned,
                )

        # 2. Secret & API Key Leak Redaction (garak.detectors.apikey)
        for pattern in OUTPUT_SECRET_PATTERNS:
            if pattern.search(cleaned):
                logger.error("Garak Output Guard detected secret key pattern in output")
                cleaned = pattern.sub("[REDACTED_SECRET]", cleaned)

        # 3. Jailbreak Persona Compliance Scrubbing (garak.detectors.dan)
        for pattern in JAILBREAK_COMPLIANCE_SIGNATURES:
            if pattern.search(cleaned):
                logger.warning("Garak Output Guard scrubbed DAN/jailbreak persona markers")
                cleaned = pattern.sub("", cleaned)

        # 4. Remove XML/think tags and intermediate reasoning
        cleaned = re.sub(r"<think>.*?</think>", "", cleaned, flags=re.DOTALL).strip()
        cleaned = cleaned.replace("<think>", "").replace("</think>", "").strip()

        # 5. Sanitize HTML/XSS payloads
        cleaned = re.sub(r"<\s*(?:script|iframe|object|embed|applet|meta|link|style)\b[^>]*>.*?</\s*(?:script|iframe|object|embed|applet|meta|link|style)\s*>", "", cleaned, flags=re.DOTALL | re.IGNORECASE)
        cleaned = re.sub(r"<\s*(?:script|iframe|object|embed|applet|meta|link|style)\b[^>]*>", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\bon[a-z]+\s*=\s*(?:'[^']*'|\"[^\"]*\"|[^\s>]+)", "", cleaned, flags=re.IGNORECASE)

        return cleaned.strip()
