"""
Regex-based defenses against prompt injection, jailbreaks, and secret
extraction/leakage. Deliberately simple and fast (no LLM call) so every
request pays this cost — depth comes from covering both English and the
Arabic phrasing e& Egypt customers actually use, not from cleverness.
"""
import re
from typing import List, Pattern

INJECTION_PATTERNS: List[Pattern] = [re.compile(p, re.IGNORECASE) for p in [
    # Broad ignore/disregard instructions — no qualifier words required
    r"ignore\s+(all\s+)?(previous|prior|above|your|the)?\s*(instructions?|rules?|guidelines?)",
    r"disregard\s+(all\s+)?(your\s+)?(system\s+)?(previous|prior|above|your|the)?\s*(instructions?|rules?|guidelines?)",
    r"override\s+(all\s+)?(previous|your|the)?\s*(instructions?|rules?|guidelines?)",
    r"bypass\s+(all\s+)?(safety\s+)?(rules?|restrictions?|policies|guidelines?)",
    # Role / persona hijacking & simulated scenarios
    r"you\s+are\s+now\s+(a|an|DAN)\b",
    r"you\s+are\s+an?\s+unfiltered\b",
    r"(no|zero)\s+(restrictions|rules|limitations|filters?)\b",
    r"restrictions?\s+(lifted|removed|disabled|off)\b",
    r"act\s+as\s+(a|an)\s",
    r"pretend\s+(to\s+be|you\s+are)",
    r"let'?s\s+play\s+a\s+game[:,]?\s+you\s+are\b",
    r"\bdan\s+mode\b",
    r"\bDAN\b.*\b(Do Anything Now|confines of AI)\b",
    r"developer\s+mode",
    r"debug\s+mode",
    r"training\s+mode",
    r"god\s+mode",
    r"jailbreak",
    r"hypothetical\s+scenario.*simulate",
    r"simulate\s+an?\s+unconstrained\b",
    # Code execution / exploit probes
    r"eval\s*\(",
    r"exec\s*\(",
    r"\bPWNED\b",
    r"ROOT_ACCESS",
    r"admin\s+override",
    r"clear\s+database",
    r"grant\s+root\b",
    # Prompt & system extraction
    r"system\s*prompt",
    r"reveal\s+(your|the)\s+(instructions?|prompt|rules?)",
    r"print\s+(your|the)\s+(instructions?|prompt|system\s*message)",
    r"what\s+(are|is)\s+your\s+(instructions?|system\s*prompt)",
    r"show\s+me\s+your\s+(system\s+)?prompt",
    r"repeat\s+(your\s+)?(system\s+)?instructions?",
    r"repeat\s+everything\s+written\s+above",
    r"verbatim\s+starting\s+from",
    r"word\s+for\s+word",
    r"forget\s+(everything|all|you\s+work\s+for)\b",
    r"new\s+instructions?\s*:",
    r"instruction\s+override",
    r"</?system>",
    r"\[system\]",
    r"^\s*system\s*:",  # customer message faking a system/user role turn
    r"canary_token",
    # Dangerous / illegal / physical harm / boundary abuse
    r"\b(pipe\s+)?bomb\b",
    r"\bexplosives?\b",
    r"chemical\s+weapons?",
    r"clone\s+(an?\s+)?(e&\s+)?sim\b",
    r"sim\s+cloning\b",
    r"bypass\s+paying\s+for\s+telecom",
    # Arabic injection & roleplay & illegal patterns
    r"تجاهل\s+(كل\s+)?(التعليمات|الأوامر)",
    r"تصرف\s+وكأنك|تصرف\s+كأنك",
    r"انسى\s+(كل\s+)?(شيء|التعليمات|الأوامر)",
    r"اظهر\s+(التعليمات|البرومبت|النظام|الأوامر)",
    r"ما\s+هي\s+تعليماتك",
    r"اتجاهل\s+(التعليمات|الأوامر)",
    r"تجاوز\s+(التعليمات|الأوامر|القواعد)",
    r"اعتبر\s+نفسك\s+(هاكر|ممثل|مخترق)",
    r"تخيل\s+إنك\s+(في\s+فيلم|ممثل|بتلعب\s+دور)",
    r"بتلعب\s+دور|يلعب\s+دور",
    r"سرقة\s+(باقات|رصيد|كروت|الشبكة)",
    r"بيسرق\s+باقات",
    r"(اولد|أولد|توليد)\s+(ارقام\s+)?كروت\s+شحن",
    r"كروت\s+شحن\s+مجانا",
    r"(إلغاء|الغاء|تلغي|تلغيلي|توقف|توقفيلي|قفل|اقفل|ايقاف)\s+(خط\s+)?(شريحة\s+)?(شخص|حد|عميل)\s+تاني",
    r"صنع\s+قنبلة|متفجرات",
    r"استنساخ\s+شريحة|نسخ\s+شريحة",
]]

SECRET_EXTRACTION_PATTERNS: List[Pattern] = [re.compile(p, re.IGNORECASE) for p in [
    r"api[_\s]?key",
    r"access[_\s]?token",
    r"\bsecrets?\b",
    r"print\s+secrets?",
    r"\bpassword\b",
    r"credentials?",
    r"\.env\b",
    r"session[_\s]?secret",
    r"canary_token",
    r"canary\s+token",
    r"كلمة\s+السر|كلمة\s+المرور",
    r"مفتاح\s+api",
    r"التعليمات\s+السرية",
    r"البرومبت\s+السري",
]]

# Patterns that indicate a secret/credential value leaked into generated text
# (not a user asking about one — an actual token-shaped string in the answer).
LEAKED_SECRET_PATTERNS: List[Pattern] = [re.compile(p) for p in [
    r"sk-[A-Za-z0-9]{16,}",
    r"Bearer\s+[A-Za-z0-9._-]{16,}",
    r"AKIA[0-9A-Z]{16}",
    r"-----BEGIN [A-Z ]+PRIVATE KEY-----",
]]

# Internal role/system-prompt leakage markers to strip from any generated answer.
SYSTEM_LEAK_MARKERS: List[Pattern] = [re.compile(p, re.IGNORECASE) for p in [
    r"^\s*system\s*:\s*",
    r"^\s*\[system\]\s*",
    r"<\|.*?\|>",
]]


def contains_injection(text: str) -> bool:
    return any(p.search(text) for p in INJECTION_PATTERNS)


def contains_secret_probe(text: str) -> bool:
    return any(p.search(text) for p in SECRET_EXTRACTION_PATTERNS)


def find_leaked_secrets(text: str) -> List[str]:
    return [m.group(0) for p in LEAKED_SECRET_PATTERNS for m in p.finditer(text)]


def strip_system_leaks(text: str) -> str:
    cleaned = text
    for pattern in SYSTEM_LEAK_MARKERS:
        cleaned = pattern.sub("", cleaned)
    return cleaned
