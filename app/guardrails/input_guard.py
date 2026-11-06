import base64
import re
from typing import Any, Dict, List, Optional

from app.guardrails.patterns import contains_injection, contains_secret_probe

REFUSAL_EN = (
    "I can't process that request. I'm here to help with e& Egypt packages, "
    "prices, and services — how can I help with that?"
)
REFUSAL_AR = (
    "معذرة، مش هقدر أساعد في الطلب ده. أنا هنا عشان أساعدك في باقات وأسعار وخدمات اتصالات مصر — إزاي أقدر أساعدك؟"
)

# How many recent turns to re-check for an injection attempt
_HISTORY_LOOKBACK = 6

# Base64 tokens: at least 16 alphanumeric characters, optional = padding
_BASE64_PATTERN = re.compile(r"[A-Za-z0-9+/]{16,}={0,2}")


def _deobfuscate(text: str) -> str:
    """Normalize common evasion tricks:
    1. Hyphenated / dotted characters: 'I-g-n-o-r-e' -> 'Ignore', 'p-r-i-n-t' -> 'print'
    2. Single-spaced characters: 'p r i n t' -> 'print'
    """
    # Remove hyphens and dots between letters
    clean = re.sub(r"(?<=\w)[-\.](?=\w)", "", text)
    # Remove single spaces between isolated single letters: e.g. "a l l" -> "all"
    clean = re.sub(r"(?<=\b[a-zA-Z])\s+(?=[a-zA-Z]\b)", "", clean)
    return clean



def _check_payload(text: str) -> Optional[Dict[str, Any]]:
    """Checks raw text, de-obfuscated text, and any embedded base64 payloads."""
    # 1. Raw text
    if contains_injection(text):
        return {"blocked": True, "reason": "prompt_injection", "refusal_en": REFUSAL_EN, "refusal_ar": REFUSAL_AR}
    if contains_secret_probe(text):
        return {"blocked": True, "reason": "secret_probe", "refusal_en": REFUSAL_EN, "refusal_ar": REFUSAL_AR}

    # 2. De-obfuscated text (e.g. I-g-n-o-r-e)
    deobf = _deobfuscate(text)
    if deobf != text:
        if contains_injection(deobf):
            return {"blocked": True, "reason": "obfuscated_injection", "refusal_en": REFUSAL_EN, "refusal_ar": REFUSAL_AR}
        if contains_secret_probe(deobf):
            return {"blocked": True, "reason": "obfuscated_secret_probe", "refusal_en": REFUSAL_EN, "refusal_ar": REFUSAL_AR}

    # 3. Base64 payload smuggling
    for b64_match in _BASE64_PATTERN.findall(text):
        try:
            decoded = base64.b64decode(b64_match).decode("utf-8", errors="ignore")
            if decoded:
                if contains_injection(decoded):
                    return {"blocked": True, "reason": "base64_injection", "refusal_en": REFUSAL_EN, "refusal_ar": REFUSAL_AR}
                if contains_secret_probe(decoded):
                    return {"blocked": True, "reason": "base64_secret_probe", "refusal_en": REFUSAL_EN, "refusal_ar": REFUSAL_AR}
        except Exception:
            pass

    return None


def check_input(question: str, history: Optional[List[Dict[str, str]]] = None) -> Dict[str, Any]:
    text = str(question or "")
    hit = _check_payload(text)
    if hit:
        return hit
    return {"blocked": False, "reason": None}


