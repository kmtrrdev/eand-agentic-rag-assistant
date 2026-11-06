"""Lightweight Arabic/English detection used for fast paths and canned replies
(the classify node's LLM call is the authoritative source once it runs)."""
import re

_ARABIC_RE = re.compile(r"[\u0600-\u06FF\u0750-\u077F\u08A0-\u08FF]")
_LATIN_RE = re.compile(r"[a-zA-Z]")

_EN_FRAMING_WORDS = {
    "what", "how", "why", "when", "where", "who", "which", "whose",
    "can", "could", "would", "should", "is", "are", "am", "was", "were",
    "do", "does", "did", "tell", "show", "give", "compare", "difference",
    "between", "details", "price", "cost", "plan", "package", "bundle",
    "code", "activate", "activation", "subscribe", "subscription",
    "cancel", "renewal", "renew", "bill", "recharge", "tax", "thanks",
    "thank", "hello", "hi", "hey", "please", "help", "need", "want",
    "best", "cheapest", "better", "max", "tier", "it", "them", "this", "that"
}

_AR_FRAMING_WORDS = {
    "ايه", "إيه", "كام", "ازاي", "إزاي", "كيف", "متى", "فين", "مين",
    "ممكن", "عايز", "عاوز", "محتاج", "باقة", "باقات", "عرض", "عروض",
    "رصيد", "كود", "اكواد", "أكواد", "اشتراك", "اشترك", "تفعيل", "فعّل", "فعل",
    "الغاء", "إلغاء", "تجديد", "جدد", "فاتورة", "فواتير", "شحن", "اشحن", "ضريبة", "ضرائب",
    "شكرا", "شكراً", "سلام", "مرحبا", "أهلا", "اهلا", "لو سمحت", "من فضلك",
    "قارن", "مقارنة", "مقارنه", "الفرق", "أحسن", "احسن", "أفضل", "افضل", "أرخص", "ارخص",
    "أعلى", "اعلى", "بين", "بينها", "معاها", "عنها", "فيها", "منها", "دي", "ده", "ديه", "دول"
}


def detect_language(text: str) -> str:
    text = text or ""
    arabic = len(_ARABIC_RE.findall(text))
    latin = len(_LATIN_RE.findall(text))
    if arabic == 0 and latin == 0:
        return "en"
    if arabic == 0 and latin > 0:
        return "en"
    if latin == 0 and arabic > 0:
        return "ar"

    # Both alphabets appear (e.g. English query with Arabic package name or vice-versa)
    words = [w.lower() for w in re.findall(r"\b\w+\b", text)]
    en_score = sum(1 for w in words if w in _EN_FRAMING_WORDS)
    ar_score = sum(1 for w in words if w in _AR_FRAMING_WORDS)

    if en_score > ar_score:
        return "en"
    if ar_score > en_score:
        return "ar"

    return "en" if latin >= arabic else "ar"


def pick(language: str, ar: str, en: str) -> str:
    return ar if language == "ar" else en
