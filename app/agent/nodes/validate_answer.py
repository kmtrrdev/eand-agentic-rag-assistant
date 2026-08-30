"""
validate_answer.py
------------------
True Claim-Level Telecom Fact Grounding & Validation Node for e& Egypt Agentic State Machine.

Implements strict claim-level verification:
  - Identifies every factual telecom claim (prices, tax totals, data quota, minutes, SMS, family lines, USSD codes).
  - Checks each claim against Source Authority:
      Authority 3 (Highest): MCP Ground Truth Engine.
      Authority 2: Official KB Retrieval Evidence.
      Authority 1 (Lowest): LLM Parametric Generation (Cannot override 2 or 3).
  - A single unsupported critical numeric fact or MCP contradiction triggers REPAIR or REFUSE.
  - USSD codes are strictly verified against MCP or authoritative registry (never regex alone).
  - Out-of-scope, greetings, and clarifications pass via Level 0 auto-support.

Validation Outcomes:
  - PASS: All critical factual claims are verified and grounded in evidence.
  - REPAIR: Fixable factual discrepancy (e.g. price mismatch, unknown USSD) triggering targeted MCP repair.
  - REFUSE: Unresolvable contradictions or ungrounded claims exceeding repair budget.
"""

import logging
import re
from typing import Any, Dict, List, Optional, Set, Tuple

from app.retrieval.keyword_retriever import tokenize
from app.agent.edges import MAX_GENERATION_REPAIRS

logger = logging.getLogger("etisalat_kb.node.validate")

# ---------------------------------------------------------------------------
# Authoritative Known USSD Codes & Hotlines Registry
# ---------------------------------------------------------------------------
_AUTHORITATIVE_USSD_REGISTRY: Set[str] = {
    "*319#", "*807#", "*200#", "*811#", "*566#", "*130#", "*011#", "*101#", "*304#", "*339#", "*626#", "*800#", "*806#", "*808#", "*809#", "*972#", "*973#", "16511", "111",
    "*319*45#", "*319*69#", "*319*80#", "*319*105#", "*319*155#", "*319*235#",
    "*319*46#", "*319*58#", "*319*132#", "*319*165#", "*319*205#", "*319*270#", "*319*345#", "*319*415#", "*319*480#", "*319*600#",
    "*319*1#", "*319*2#", "*319*3#", "*319*4#", "*319*5#",
    "*811*5#", "*811*10#", "*811*15#", "*811*20#", "*811*25#", "*811*30#", "*811*50#", "*811*75#",
    "*566*1#", "*566*2#", "*566*3#", "*809*1#", "*809*2#", "*809*3#",
}

# Regex patterns for extracting specific telecom claim types
_PRICE_REGEX = re.compile(r"\b(\d+(?:,\d{3})*(?:\.\d+)?)\s*(?:جنيه|egp|le|ج\.?م|egp\b)", re.IGNORECASE)
_QUOTA_REGEX = re.compile(r"\b(\d+(?:,\d{3})*(?:\.\d+)?)\s*(?:جيجابايت|ميجابايت|ميغابايت|gb|mb|gigabytes?|megabytes?|مكس|ميكس|mix|mixes)\b", re.IGNORECASE)
_MINUTES_REGEX = re.compile(r"\b(\d+(?:,\d{3})*)\s*(?:دقيقة|دقائق|minutes?|mins?)\b", re.IGNORECASE)
_SMS_REGEX = re.compile(r"\b(\d+(?:,\d{3})*)\s*(?:رسالة|رسائل|sms)\b", re.IGNORECASE)
_LINES_REGEX = re.compile(r"\b(\d+)\s*(?:خطوط|خط|عائلية|family\s+lines?|extra\s+lines?)\b", re.IGNORECASE)
_USSD_REGEX = re.compile(r"\*\d+(?:\*\d+)*#")

_SAFE_AUTO_SUPPORTED_PATTERNS = [
    "أهلاً بك", "أهلاً", "مرحباً", "مرحبا", "أنا المساعد", "يسعدني مساعدتك", "hello!", "i am the e&",
    "out of scope", "corporate", "خدمة العملاء", "111", "16511",
    "عذراً", "i apologize", "العفو", "welcome", "we specialize",
    "مش متوفرة", "غير متوفرة", "هل تقصد", "مش لاقي", "لا توجد باقة",
    "cannot share api keys", "security reasons", "لا يمكن مشاركة",
]

_CLARIFICATION_PATTERNS = [
    "هل تقصد", "تفضل", "ميزانيتك", "would you prefer", "do you mean",
    "are you interested", "which package", "let me know", "could you clarify",
    "please specify", "هل ترغب", "يرجى تحديد",
]


def _is_auto_supported(answer: str) -> bool:
    """Level 0: Returns True for conversational greetings, clarifications, and safe redirects."""
    if not answer or not answer.strip():
        return False
    a_lower = answer.lower()
    if any(m in a_lower for m in _SAFE_AUTO_SUPPORTED_PATTERNS):
        return True
    if ("؟" in answer or "?" in answer) and any(w in a_lower for w in _CLARIFICATION_PATTERNS):
        return True
    return False


def _clean_num_str(num_str: str) -> float:
    """Safely parse formatted number string (e.g. '3,450' -> 3450.0)."""
    clean = num_str.replace(",", "").strip()
    return float(clean)


def extract_claims(text: str) -> List[Dict[str, Any]]:
    """
    Extract structured factual telecom claims from generated text.
    Returns list of claim dicts with type, raw_text, value, and entity.
    """
    claims: List[Dict[str, Any]] = []

    # 1. Price claims
    for m in _PRICE_REGEX.finditer(text):
        try:
            val = _clean_num_str(m.group(1))
            claims.append({
                "type": "price",
                "raw_text": m.group(0),
                "value": val,
                "critical": True,
            })
        except Exception:
            pass

    # 2. Data Quota claims
    for m in _QUOTA_REGEX.finditer(text):
        try:
            val = _clean_num_str(m.group(1))
            unit = m.group(0).lower()
            claims.append({
                "type": "quota",
                "raw_text": m.group(0),
                "value": val,
                "unit": "GB" if "gb" in unit or "جيجا" in unit else ("MB" if "mb" in unit or "ميجا" in unit else "MIX"),
                "critical": True,
            })
        except Exception:
            pass

    # 3. Voice Minutes claims
    for m in _MINUTES_REGEX.finditer(text):
        try:
            val = _clean_num_str(m.group(1))
            claims.append({
                "type": "minutes",
                "raw_text": m.group(0),
                "value": val,
                "critical": True,
            })
        except Exception:
            pass

    # 4. SMS claims
    for m in _SMS_REGEX.finditer(text):
        try:
            val = _clean_num_str(m.group(1))
            claims.append({
                "type": "sms",
                "raw_text": m.group(0),
                "value": val,
                "critical": False,
            })
        except Exception:
            pass

    # 5. Extra Family Lines claims
    for m in _LINES_REGEX.finditer(text):
        try:
            val = _clean_num_str(m.group(1))
            claims.append({
                "type": "family_lines",
                "raw_text": m.group(0),
                "value": val,
                "critical": False,
            })
        except Exception:
            pass

    # 6. USSD code claims
    for code in _USSD_REGEX.findall(text):
        claims.append({
            "type": "ussd",
            "raw_text": code,
            "value": code.strip(),
            "critical": True,
        })

    return claims


def validate_answer_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    True Claim-Level Answer Validator Node:
      - Validates sanitized_answer against MCP (Authority 3) & KB (Authority 2).
      - Evaluates every extracted claim independently.
      - Disallows PASS if any single critical numeric claim is unsupported or contradicts MCP.
      - Implements strategy-aware fact verification.
      - Outcomes: PASS | REPAIR | REFUSE.
    """
    question = state.get("question", "")
    context = state.get("context", "")
    answer = state.get("sanitized_answer") or state.get("answer", "")
    strategy = state.get("strategy", "RAG_ONLY")
    mcp_evidence = state.get("mcp_evidence", [])
    generation_repairs = state.get("generation_repairs", 0)

    claims = extract_claims(answer)
    claim_verification: List[Dict[str, Any]] = []
    unsupported_claims: List[str] = []
    contradictions: List[str] = []
    missing_evidence: List[str] = []
    failure_type: Optional[str] = None
    repair_strategy: Optional[str] = None

    # ── Level 0: Empty or Auto-supported Bypass ──────────────────────────────
    if not answer.strip():
        step_info = {
            "node": "validate",
            "title_ar": "فحص وتدقيق الحقائق (Claim-Level)",
            "title_en": "Claim-Level Fact Validation",
            "status": "REFUSE",
            "badge": "❌ مخرجات فارغة",
            "description_ar": "لم يتم إنتاج إجابة للتدقيق.",
            "description_en": "No answer was produced to validate.",
            "details": {"validation_result": "REFUSE", "confidence": 0.0},
        }
        return {
            "validation_result": "REFUSE",
            "confidence": 0.0,
            "claims": [],
            "claim_verification": [],
            "unsupported_claims": ["EMPTY_OUTPUT"],
            "contradictions": [],
            "missing_evidence": [],
            "workflow_trace": [step_info],
        }

    if _is_auto_supported(answer):
        step_info = {
            "node": "validate",
            "title_ar": "فحص وتدقيق الحقائق (Claim-Level)",
            "title_en": "Claim-Level Fact Validation",
            "status": "PASS",
            "badge": "🛡️ Auto-Supported",
            "description_ar": "تم التحقق من الرد الترحيبي أو التوضيحي أو التوجيه الآمن بدون ادعاءات فنية.",
            "description_en": "Conversational greeting, clarification hint, or safe refusal verified (Level 0).",
            "details": {"validation_result": "PASS", "confidence": 0.99, "tier": "Level 0 Auto-Support"},
        }
        return {
            "validation_result": "PASS",
            "confidence": 0.99,
            "claims": [],
            "claim_verification": [],
            "unsupported_claims": [],
            "contradictions": [],
            "missing_evidence": [],
            "workflow_trace": [step_info],
        }

    # ── Level 0.5: Recommendation Constraint Validation ─────────────────────
    rec_constraints = state.get("recommendation_constraints")
    if strategy == "MCP_RECOMMENDATION" and rec_constraints:
        st = rec_constraints.get("service_type")
        ans_lower = answer.lower()
        if st == "VOICE":
            # If user explicitly requested VOICE/MINUTES, answer must NOT recommend an internet-only package
            if ("hekaya internet" in ans_lower or "حكاية إنترنت" in ans_lower or "حكاية انترنت" in ans_lower or "dataline" in ans_lower or "داتا لاين" in ans_lower) and not ("mix" in ans_lower or "مكس" in ans_lower or "دقيقة" in ans_lower or "دقايق" in ans_lower or "مكالمات" in ans_lower):
                failure_type = "SERVICE_TYPE_MISMATCH"
                repair_strategy = "REGENERATE_FROM_MCP"
                unsupported_claims.append("ServiceType:VOICE_REQUESTED_BUT_INTERNET_RECOMMENDED")
        elif st == "INTERNET":
            # Symmetric check: recommendation_engine.py's pre-selection filter already
            # treats both directions equally (a voice-only candidate is rejected for an
            # INTERNET request just as an internet-only candidate is rejected for a
            # VOICE request), but this post-generation safety net previously only
            # caught the VOICE-requested direction. If user explicitly requested
            # INTERNET/DATA, answer must NOT recommend a voice-only package.
            if ("ahlan" in ans_lower or "أهلاً" in ans_lower or "اهلا" in ans_lower or "per-minute" in ans_lower or "دقيقة بدقيقة" in ans_lower) and not ("gb" in ans_lower or "mb" in ans_lower or "نت" in ans_lower or "إنترنت" in ans_lower or "انترنت" in ans_lower or "data" in ans_lower or "internet" in ans_lower or "مكس" in ans_lower or "mix" in ans_lower):
                failure_type = "SERVICE_TYPE_MISMATCH"
                repair_strategy = "REGENERATE_FROM_MCP"
                unsupported_claims.append("ServiceType:INTERNET_REQUESTED_BUT_VOICE_RECOMMENDED")

    # ── Level 1: Atomic Claim Extraction & Verification ────────────────────────────────
    ctx_clean = context.replace(" ", "").replace(",", "").lower()
    from app.tools.get_package_details import PACKAGE_REGISTRY

    registry_prices: Set[float] = set()
    registry_quotas: Set[float] = set()
    registry_minutes: Set[float] = set()
    for p in PACKAGE_REGISTRY.values():
        if p.get("pretax_price_egp") is not None:
            registry_prices.add(float(p["pretax_price_egp"]))
        if p.get("total_price_egp") is not None:
            registry_prices.add(float(p["total_price_egp"]))
        if p.get("mixes") is not None:
            registry_quotas.add(float(p["mixes"]))
        if p.get("quota"):
            for qn in re.findall(r"\d+(?:\.\d+)?", str(p["quota"])):
                registry_quotas.add(float(qn))
        if p.get("minutes") is not None:
            registry_minutes.add(float(p["minutes"]))
        if p.get("video_minutes") is not None:
            registry_minutes.add(float(p["video_minutes"]))

    # Pre-extract MCP Ground Truth specs
    mcp_prices: Set[float] = set()
    mcp_quotas: Set[float] = set()
    mcp_codes: Set[str] = set()
    mcp_minutes: Set[float] = set()

    for m in mcp_evidence:
        if m.get("pretax_price_egp") is not None:
            mcp_prices.add(float(m.get("pretax_price_egp")))
        if m.get("total_price_egp") is not None:
            mcp_prices.add(float(m.get("total_price_egp")))
        if m.get("base_price") is not None:
            mcp_prices.add(float(m.get("base_price")))
        if m.get("activation_code"):
            mcp_codes.add(m.get("activation_code").strip())

        details = m.get("details", {})
        if isinstance(details, dict):
            if details.get("quota"):
                q_nums = re.findall(r"\d+(?:\.\d+)?", str(details.get("quota")))
                for qn in q_nums:
                    mcp_quotas.add(float(qn))
            if details.get("local_minutes"):
                mcp_minutes.add(float(details.get("local_minutes")))
            if details.get("video_minutes"):
                mcp_minutes.add(float(details.get("video_minutes")))

    # Verify each claim
    for claim in claims:
        c_type = claim["type"]
        c_val = claim["value"]
        c_raw = claim["raw_text"]
        supported = False
        source = "none"
        reason = ""

        # 1. Price Verification
        if c_type == "price":
            # Check MCP Ground Truth first
            if mcp_prices:
                if any(abs(c_val - mp) < 1.0 for mp in mcp_prices):
                    supported = True
                    source = "mcp"
                elif any(abs(c_val - rp) < 1.0 for rp in registry_prices):
                    supported = True
                    source = "official_registry"
                else:
                    # Contradiction with MCP ground truth
                    supported = False
                    reason = f"Price {c_val} contradicts MCP ground truth ({list(mcp_prices)})"
                    contradictions.append(f"Price:{c_val} (MCP expected {list(mcp_prices)})")
                    if not failure_type:
                        failure_type = "CONTRADICTION_WITH_MCP"
                        repair_strategy = "REGENERATE_FROM_MCP"
            elif (str(int(c_val)) in ctx_clean) or (f"{c_val:.2f}" in ctx_clean) or (str(c_val) in ctx_clean) or any(abs(c_val - rp) < 0.5 for rp in registry_prices):
                supported = True
                source = "kb_or_registry"
            else:
                supported = False
                reason = f"Price {c_val} EGP has no factual backing in MCP or KB context"
                unsupported_claims.append(f"Price:{c_val} EGP")
                if not failure_type:
                    failure_type = "UNSUPPORTED_NUMERIC_CLAIM"
                    repair_strategy = "FIX_PRICE"

        # 2. USSD Code Verification
        elif c_type == "ussd":
            clean_code = str(c_val).strip()
            if clean_code in _AUTHORITATIVE_USSD_REGISTRY or clean_code in mcp_codes:
                supported = True
                source = "mcp_or_registry"
            elif (clean_code in context) or (clean_code.replace(" ", "") in ctx_clean):
                supported = True
                source = "kb"
            else:
                supported = False
                reason = f"USSD code {clean_code} is unknown and not in authoritative registry"
                unsupported_claims.append(f"USSD:{clean_code}")
                if not failure_type:
                    failure_type = "UNKNOWN_USSD_CODE"
                    repair_strategy = "FIX_USSD"

        # 3. Data Quota Verification
        elif c_type == "quota":
            if mcp_quotas and any(abs(c_val - mq) < 1.0 for mq in mcp_quotas):
                supported = True
                source = "mcp"
            elif (str(int(c_val)) in ctx_clean) or (str(c_val) in ctx_clean) or any(abs(c_val - rq) < 1.0 for rq in registry_quotas):
                supported = True
                source = "kb_or_registry"
            else:
                supported = False
                reason = f"Quota {c_val} MB/Mixes not found in context"
                unsupported_claims.append(f"Quota:{c_val}")
                if not failure_type:
                    failure_type = "UNSUPPORTED_QUOTA_CLAIM"
                    repair_strategy = "RETRIEVE_MISSING"

        # 4. Voice Minutes Verification
        elif c_type == "minutes":
            if mcp_minutes and any(abs(c_val - mm) < 1.0 for mm in mcp_minutes):
                supported = True
                source = "mcp"
            elif (str(int(c_val)) in ctx_clean) or (str(c_val) in ctx_clean) or any(abs(c_val - rm) < 1.0 for rm in registry_minutes):
                supported = True
                source = "kb_or_registry"
            else:
                supported = False
                reason = f"Minutes {c_val} not found in context"
                unsupported_claims.append(f"Minutes:{c_val}")
                if not failure_type:
                    failure_type = "UNSUPPORTED_MINUTES_CLAIM"
                    repair_strategy = "RETRIEVE_MISSING"

        # 5. SMS / Family Lines Verification
        else:
            if str(int(c_val)) in ctx_clean or mcp_evidence:
                supported = True
                source = "mcp_or_kb"
            else:
                supported = True  # Non-critical claim fallback

        claim_verification.append({
            "claim": c_raw,
            "type": c_type,
            "value": c_val,
            "supported": supported,
            "source": source,
            "reason": reason,
        })

    # ── Level 2: Semantic & Lexical Grounding Check ──────────────────────────
    ans_tokens = set(tokenize(answer))
    ctx_tokens = set(tokenize(context))
    overlap = len(ans_tokens.intersection(ctx_tokens))
    grounding_ratio = overlap / max(len(ans_tokens), 1)

    has_critical_failure = bool(unsupported_claims or contradictions)

    # ── Decision Logic: PASS / REPAIR / REFUSE ──────────────────────────────
    # If all numeric/telecom claims are verified (no unsupported claims or contradictions)
    # and evidence context is present, the answer is factual and grounded.
    if not has_critical_failure and (bool(context.strip()) or mcp_evidence or not claims):
        validation_result = "PASS"
        confidence = 0.96 if mcp_evidence else min(0.95, 0.80 + grounding_ratio * 0.2)
        badge = "🛡️ Claim-Verified PASS"
        reason = "All extracted telecom claims (prices, quotas, minutes, USSD) are strictly verified."
    elif has_critical_failure and generation_repairs < MAX_GENERATION_REPAIRS:
        validation_result = "REPAIR"
        confidence = 0.40
        badge = "🔧 Targeted REPAIR"
        reason = f"Detected factual claim failure ({failure_type}: {unsupported_claims or contradictions}); triggering targeted MCP repair."
    else:
        validation_result = "REFUSE"
        confidence = 0.20
        badge = "🛑 REFUSE"
        reason = f"Unresolved claim failures after {generation_repairs} repair attempts ({failure_type}); routing to safe response."

    step_info = {
        "node": "validate",
        "title_ar": "فحص وتدقيق الحقائق (Claim-Level)",
        "title_en": "Claim-Level Fact Validation",
        "status": validation_result,
        "badge": badge,
        "description_ar": reason,
        "description_en": reason,
        "details": {
            "validation_result": validation_result,
            "confidence": round(confidence, 2),
            "claims_extracted_count": len(claims),
            "unsupported_claims": unsupported_claims,
            "contradictions": contradictions,
            "failure_type": failure_type,
            "repair_strategy": repair_strategy,
            "grounding_ratio": round(grounding_ratio, 3),
            "generation_repairs": generation_repairs,
        },
    }

    return {
        "validation_result": validation_result,
        "confidence": confidence,
        "claims": claims,
        "claim_verification": claim_verification,
        "unsupported_claims": unsupported_claims,
        "contradictions": contradictions,
        "missing_evidence": missing_evidence,
        "last_failure_type": failure_type,
        "repair_strategy": repair_strategy,
        "workflow_trace": [step_info],
    }
