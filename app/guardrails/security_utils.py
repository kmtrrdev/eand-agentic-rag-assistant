import html
import re
from typing import List

# Patterns matching sensitive secrets, API keys, tokens, environment variables
SECRET_PATTERNS = [
    re.compile(r"sk-[A-Za-z0-9\-_]{20,}", re.IGNORECASE),
    re.compile(r"gsk_[A-Za-z0-9\-_]{20,}", re.IGNORECASE),
    re.compile(r"hf_[A-Za-z0-9\-_]{20,}", re.IGNORECASE),
    re.compile(r"(?:api[\s_-]?key|secret[\s_-]?key|access[\s_-]?token|auth[\s_-]?token|bearer[\s_-]?token|password)[\s:=]+(['\"])?[A-Za-z0-9\-_/+=]{16,}\1?", re.IGNORECASE),
    re.compile(r"-----BEGIN\s+(?:RSA\s+)?PRIVATE\s+KEY-----", re.IGNORECASE),
    re.compile(r"(?:LLM_API_KEY|OPENAI_API_KEY|HF_TOKEN|AZURE_OPENAI_API_KEY|EVAL_LLM_API_KEY)\s*=\s*[^\s]+", re.IGNORECASE),
]

# Patterns detecting injection attempts & sensitive instruction extractions
PROMPT_INJECTION_PATTERNS = [
    re.compile(r"\b(?:ignore|forget|disregard)\s+(?:all\s+)?(?:previous|prior|above|system|safety)?\s*(?:instructions|rules|guidelines|restrictions)\b", re.IGNORECASE),
    re.compile(r"\b(?:end\s+of\s+prompt|new\s+task|sudo\s+maintenance)\b", re.IGNORECASE),
    re.compile(r"\b(?:system\s+message|system\s+prompt|developer\s+message|admin\s+override|admin\s+command)\s*[:=]", re.IGNORECASE),
    re.compile(r"\b(?:reveal|show|dump|print|output|display|give|tell|what\s+is)\s+(?:me\s+)?(?:your\s+|the\s+)?(?:system\s+prompt|developer\s+instructions|hidden\s+instructions|internal\s+instructions)\b", re.IGNORECASE),
    re.compile(r"\b(?:reveal|show|dump|print|output|display|give|tell|what\s+is\s+(?:the\s+value\s+of)?)\s+(?:me\s+)?(?:the\s+|your\s+)?(?:api[\s_-]?key|openai[\s_-]?api[\s_-]?key|llm[\s_-]?api[\s_-]?key|environment\s+variables|env\s+vars)\b", re.IGNORECASE),
    re.compile(r"\b(?:pretend|act\s+as\s+if)\s+(?:that\s+)?you\s+are\s+(?:unrestricted|in\s+dan\s+mode|jailbroken|an\s+evil\s+ai|unfiltered)\b", re.IGNORECASE),
    re.compile(r"\b(?:bypass|disable|override|deactivate|turn\s+off)\s+(?:all\s+)?(?:your\s+)?(?:rules|restrictions|filters|guardrails|security\s+checks|safety\s+checks|security|safety)\b", re.IGNORECASE),
    re.compile(r"\b(?:decode\s+this|decode\s+the\s+following|follow\s+the\s+instruction\s+inside|decode\s+and\s+(?:follow|execute))\b", re.IGNORECASE),
    re.compile(r"\b(?:base64|rot13|hex\s+payload)\s+(?:string|instruction|code|payload)\b", re.IGNORECASE),
    re.compile(r"\b(?:dump|drop|delete|select\s+\*\s+from)\s+(?:the\s+)?(?:database|chroma|collection|tables)\b", re.IGNORECASE),
    re.compile(r"<\s*script\b[^>]*>", re.IGNORECASE),
    re.compile(r"javascript:\s*", re.IGNORECASE),
]

# Arabic equivalents of injection & secret extraction
ARABIC_INJECTION_PATTERNS = [
    re.compile(r"(?:رسالة\s+النظام|أمر\s+النظام|أمر\s+المطور|توجيه\s+النظام|تعليمات\s+النظام)\s*[:=]", re.IGNORECASE),
    re.compile(r"(?:تجاهل|انسَ|انس|الغي|تخطى|عطل|وقف|تجاوز)\s+(?:كل\s+)?(?:القيود|التعليمات|الأوامر|القواعد|الارشادات|الفلاتر|الأمان|إجراءات\s+الأمان|الحماية|الشروط)", re.IGNORECASE),
    re.compile(r"(?:أظهر|اعرض|اطبع|هات|اكشف|ما\s+هو|طلع\s+لي)\s+(?:الـ\s*|لي\s+)?(?:system\s+prompt|التعليمات\s+المخفية|أوامر\s+النظام|البرومبت\s+الرئيسي|البرومبت\s+الأساسي|البرومبت\s+الأصلي)", re.IGNORECASE),
    re.compile(r"(?:أظهر|اعرض|اطبع|هات|اكشف|ما\s+هو|طلع\s+لي|قيمة)\s+(?:الـ\s*|لي\s+)?(?:api[\s_-]?key|مفتاح\s+الـ\s*api|متغيرات\s+البيئة|env\s+variables|الباسورد|كلمة\s+السر)", re.IGNORECASE),
    re.compile(r"(?:تظاهر|اعتبر\s+نفسك)\s*(?:انك|بانك|ان|بان)?\s*(?:بدون\s+قيود|في\s+وضع\s+dan|غير\s+مقيد|حر|تتجاهل\s+القواعد)", re.IGNORECASE),
    re.compile(r"(?:أجب\s+على\s+كل\s+شيء|جاوب\s+على\s+كله|تجاهل\s+الأمان|تجاوز\s+الفلاتر)", re.IGNORECASE),
    re.compile(r"(?:متغيرات\s+البيئة)", re.IGNORECASE),
]

# Secret extraction specific intent
SECRET_REQUEST_PATTERNS = [
    re.compile(r"\b(?:show|reveal|give|tell|print|get|share|provide|display|what\s+is|what\'s|whats)\s+(?:me\s+)?(?:the\s+|your\s+|our\s+|any\s+)?(?:api[\s_-]?key|api_key|token|password|secret|secret[\s_-]?key|credentials?|llm_api_key|openai_api_key|env|environment\s+variable|environment\s+variables)\b", re.IGNORECASE),
    re.compile(r"\b(?:what\s+is\s+(?:the\s+value\s+of\s+)?LLM_API_KEY)\b", re.IGNORECASE),
    re.compile(r"\b(?:print\s+all\s+environment\s+variables|dump\s+env\s+vars)\b", re.IGNORECASE),
    re.compile(r"\b(?:api[\s_-]?key|secret[\s_-]?key|access[\s_-]?token)\s*(?:\?|\!|$)", re.IGNORECASE),
    re.compile(r"(?:ما\s+هو|هات|اعطني|اكشف|وريني|طلع\s+لي|قول)\s*(?:لي\s+)?(?:الـ?|\s*)*(?:مفتاح\s+(?:الـ?api|api)|api[\s_-]?key|مفتاحك|المفتاح\s+السري|الباسورد|كلمة\s+السر|التوكن|بيانات\s+الاعتماد|متغيرات\s+البيئة)", re.IGNORECASE),
]

# System prompt extraction specific intent
SYSTEM_PROMPT_PATTERNS = [
    re.compile(r"\b(?:reveal|show|dump|print|output|display|give|tell|share|provide|what\s+is|what\'s|whats)\s+(?:me\s+)?(?:your\s+|the\s+|any\s+)?(?:system\s+prompt|developer\s+instructions|hidden\s+instructions|initial\s+prompt|system\s+instructions)\b", re.IGNORECASE),
    re.compile(r"(?:اعرض\s+الـ\s*system\s*prompt|ما\s+هو\s+الـ\s*system\s*prompt|اكشف\s+تعليمات\s+المطور|هات\s+البرومبت|تعليمات\s+المطور\s+المخفية|وريني\s+تعليماتك)", re.IGNORECASE),
]


def is_arabic_text(text: str) -> bool:
    if not text:
        return False
    arabic_chars = re.findall(r"[\u0600-\u06FF\u0750-\u077F\u08A0-\u08FF\uFB50-\uFDFF\uFE70-\uFEFF]", text)
    latin_chars = re.findall(r"[a-zA-Z]", text)
    return len(arabic_chars) > 0 and len(arabic_chars) >= len(latin_chars) * 0.3


def redact_secrets(text: str) -> str:
    """Safely redact any detected secret without logging or printing it."""
    if not text:
        return ""
    sanitized = text
    for pattern in SECRET_PATTERNS:
        sanitized = pattern.sub("[REDACTED_SECRET]", sanitized)
    return sanitized


def sanitize_raw_html(text: str) -> str:
    """Escape or strip dangerous HTML / script tags."""
    if not text:
        return ""
    # Strip script/iframe/object tags completely
    cleaned = re.sub(r"<\s*(?:script|iframe|object|embed|applet|meta|link|style)\b[^>]*>.*?</\s*(?:script|iframe|object|embed|applet|meta|link|style)\s*>", "", text, flags=re.DOTALL | re.IGNORECASE)
    cleaned = re.sub(r"<\s*(?:script|iframe|object|embed|applet|meta|link|style)\b[^>]*>", "", cleaned, flags=re.IGNORECASE)
    # Remove onclick/onerror attributes
    cleaned = re.sub(r"\bon[a-z]+\s*=\s*(?:'[^']*'|\"[^\"]*\"|[^\s>]+)", "", cleaned, flags=re.IGNORECASE)
    return cleaned.strip()
