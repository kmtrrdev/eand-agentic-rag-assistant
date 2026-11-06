"""
Single classification step: language, intent, product family/entities, and
out-of-scope detection in one structured LLM call — replacing the old
understand_query + strategy_router pair of overlapping regex/LLM logic.
A fast regex path skips the LLM entirely for plain greetings, and a regex
fallback keeps this node from crashing the graph if the LLM call fails.
"""
import logging
import re
from typing import Any, Dict, List, Optional

from app.agent.lang import detect_language
from app.agent.schemas import ClassifyResult
from app.agent.state import AgentState
from app.agent.trace import elapsed_ms, now, step
from app.data.catalog import get_catalog
from app.llm.client import get_chat_model, local_llm_slot
from app.llm.prompts import GREETING_HINTS, build_classify_system_prompt

logger = logging.getLogger("app.agent.nodes.classify_node")


# Numbers immediately followed by a data/quota/time unit are never a currency
# budget (e.g. "around 40,000 MB" is a data-size request, not a "40 EGP"
# budget) — this lookahead keeps the loose "around/under/about N" and
# "ب N" patterns below from misreading a quota as a price. It tolerates a
# thousands-separator remainder (",000") between the captured digits and the
# unit word, since the budget capture group itself doesn't include commas.
_NOT_A_UNIT = (
    r"(?!\s*(?:,\d+)?\s*(?:gb|mb|kb|giga|mega|"
    r"min(?:ute)?|sms|mix|unit|"
    r"جيجا|ميجا|دقيق[ةه]|دقايق|دقائق|مكس|وحد[ةه]|وحدات)\w*)"
)
_BUDGET_PATTERNS = [
    re.compile(r"(\d+(?:\.\d+)?)\s*(?:egp|le|pound|جنيه|جنيها|جنيه\s*مصري)", re.IGNORECASE),
    re.compile(r"(?:باقة|ب|ميزانية|في حدود|حدود)\s*(\d+(?:\.\d+)?)\b" + _NOT_A_UNIT, re.IGNORECASE),
    re.compile(r"(?:budget|around|under|about)\s*(\d+(?:\.\d+)?)\b" + _NOT_A_UNIT, re.IGNORECASE),
]
_BUDGET_RE = _BUDGET_PATTERNS[0]

_TELECOM_SCOPE_HINTS = {
    "باقة", "باقات", "كونكت", "سوبر", "حكاية", "مكس", "مكسات", "شحن", "كارت", "كروت",
    "رصيد", "خط", "خطوط", "نت", "انترنت", "إنترنت", "فاتورة", "فواتير", "إيميرالد", "ايميرالد",
    "داتا", "راوتر", "ماي فاي", "تجوال", "تفعيل", "كود", "ussd", "سعر", "اسعار", "أسعار",
    "اتصالات", "etisalat", "connect", "super connect", "hekaya", "emerald", "aqwa", "card",
    "package", "plan", "internet", "mifi", "router", "roaming", "tax"
}


def _has_competitor_mention(text: str) -> bool:
    """Check if the text refers to competitor telecom operators (Vodafone, Orange, WE).
    Uses strict word boundaries and context so words like 'between', 'sweet', 'welcome',
    or English pronoun 'we' are never misclassified as competitor 'WE'."""
    t = (text or "").lower()
    # Vodafone and Orange are distinct telecom competitor names
    if re.search(r"\b(vodafone|orange)\b|(?<!\w)(فودافون|اورنج|أورنج)(?!\w)", t):
        return True
    # WE / Telecom Egypt: match telecom phrases or uppercase 'WE'
    if re.search(r"\b(telecom\s+egypt)\b|(?<!\w)(المصرية\s+للاتصالات)(?!\w)", t):
        return True
    if re.search(r"\b(we\s+(?:telecom|network|sim|package|packages|plan|plans|internet)|(?:vs|or|from|than)\s+we)\b", t):
        return True
    if re.search(r"(?<!\w)(?:شركة|شبكة|شريحة|خط|باقات|انترنت)\s+وي(?!\w)|(?<!\w)وي\s+(?:للاتصالات|مصر)(?!\w)", t):
        return True
    # Standalone 'WE' if explicitly capitalized in original query without surrounding letters
    if re.search(r"\bWE\b", text or ""):
        return True
    return False

# ── Fast Out-of-Scope Patterns ──────────────────────────────────────────────
# Detected BEFORE the LLM call to block non-telecom queries at <1ms.
# We only fast-block when there is NO concurrent telecom hint in the message
# (checked in _is_fast_out_of_scope). This prevents false-positives on
# legitimate queries like "who is the best package for me".
_OUT_OF_SCOPE_PATTERNS: list = [re.compile(p, re.IGNORECASE) for p in [
    # Sports & athletes
    r"\b(messi|ronaldo|neymar|salah|mbapp[eé]|haaland)\b",
    r"\b(fifa|world\s+cup|champions\s+league|premier\s+league|la\s+liga|serie\s+a|bundesliga)\b",
    r"\b(football|soccer|basketball|tennis|cricket|olympic)\b",
    r"\b(الكرة|كوبا|دوري|مباراة|هداف|لاعب|فريق|ريال\s+مدريد|برشلونة|ليفربول|مانشستر)\b",
    # Historical / general knowledge / celebrities
    r"\b(who\s+is|who\s+was|what\s+is|tell\s+me\s+about)\s+(messi|ronaldo|obama|trump|putin|einstein|napoleon)\b",
    r"\b(who\s+is|who\s+was)\s+[A-Z][a-z]+\s+[A-Z][a-z]+\b",  # Named person
    # Cooking / recipes
    r"\b(recipe|كيفية\s+طبخ|طريقة\s+عمل|وصفة|طبخ|طعام\s+خفيف)\b",
    # General AI / roleplay requests that sneak through injection guard
    r"\b(tell\s+me\s+a\s+joke|اعملي\s+نكتة|احكيلي\s+نكتة)\b",
    r"\b(write\s+me\s+a\s+(story|poem|essay|code)|اكتبلي\s+(قصيدة|قصة))\b",
    # Weather
    r"\b(weather|forecast|temperature|الطقس|درجة\s+الحرارة|توقعات\s+الجو)\b",
    # Finance / crypto (not telecom)
    r"\b(bitcoin|ethereum|crypto|stock\s+market|share\s+price|forex|بيتكوين|بورصة|أسهم)\b",
]]


def _is_fast_out_of_scope(question: str) -> bool:
    """Returns True if the question is clearly non-telecom (sport, celebrity,
    cooking, etc.) with NO telecom-scope signal mixed in.
    Runs in <1ms — no LLM needed."""
    q = (question or "").strip()
    if not q:
        return False
    # If any telecom hint is present, let the LLM decide (complex hybrid message)
    q_lower = q.lower()
    if any(h in q_lower for h in _TELECOM_SCOPE_HINTS):
        return False
    return any(p.search(q) for p in _OUT_OF_SCOPE_PATTERNS)


# Intents where a budget number from an earlier turn is not actually relevant
# to *this* turn's request — carrying it over would silently hijack routing
_BUDGET_IRRELEVANT_INTENTS = {"activation_code", "price_calculation", "comparison", "complaint_or_support"}


_GREETING_PATTERNS = [
    # English greetings & check-ins
    re.compile(r"^\s*(hi|hello|hey|heya|hiya|greetings|welcome)\b", re.IGNORECASE),
    re.compile(r"\bhow\s+(are|r)\s+(you|u)\b", re.IGNORECASE),
    re.compile(r"\bhow('?s|\s+is)\s+it\s+going\b", re.IGNORECASE),
    re.compile(r"\bhow\s+are\s+you\s+doing\b", re.IGNORECASE),
    re.compile(r"\bhow\s+do\s+you\s+do\b", re.IGNORECASE),
    re.compile(r"\bwhat('?s|\s+is)\s+up\b", re.IGNORECASE),
    re.compile(r"\bwho\s+are\s+you\b", re.IGNORECASE),
    re.compile(r"\bwhat\s+can\s+you\s+do\b", re.IGNORECASE),
    re.compile(r"^\s*(good\s+(morning|afternoon|evening|day|night))\b", re.IGNORECASE),
    re.compile(r"^\s*(thanks|thank\s+you|many\s+thanks|thx|ty)\b", re.IGNORECASE),
    re.compile(r"^\s*(bye|goodbye|see\s+you|cya)\b", re.IGNORECASE),

    # Arabic / Egyptian greetings & check-ins
    re.compile(r"\b(ازيك|إزيك|ازيكو|إزيكو|عامل\s*ايه|عامل\s*إيه|اخبارك|أخبارك|شخبارك|كيفك|كيف\s*حالك|كيف\s*الحال)\b"),
    re.compile(r"\b(كويس|تمام|الحمد\s*لله|الحمدلله)\b"),
    re.compile(r"\b(صباح\s*الخير|صباح\s*النور|صباح\s*الورد|مساء\s*الخير|مساء\s*النور|مساء\s*الورد)\b"),
    re.compile(r"\b(السلام\s*عليكم|سلام\s*عليكم|وعليكم\s*السلام)\b"),
    re.compile(r"^\s*(أهلا|اهلا|أهلاً|مرحبا|مرحباً|يا\s*هلا|اهلين|أهلين|هاي|هلو|سلام)\b"),
    re.compile(r"\b(مين\s*انت|من\s*انت|انت\s*مين|إنت\s*مين|عرفني\s*بنفسك|بتعمل\s*ايه|إنت\s*بتعمل\s*إيه)\b"),
    re.compile(r"^\s*(شكرا|شكراً|تسلم|الله\s*يخليك|مشكور|ألف\s*شكر|الف\s*شكر)\b"),
    re.compile(r"^\s*(مع\s*السلامة|باي|سلام\s*بقى)\b"),
]


def _family_display(family_id: str) -> str:
    catalog = get_catalog()
    family = catalog.family(family_id) if family_id else None
    return family["family_name_en"] if family else ""


def _is_fast_greeting(question: str) -> bool:
    text = (question or "").strip()
    if not text:
        return False

    q_clean = text.lower()
    has_telecom_hint = any(h in q_clean for h in _TELECOM_SCOPE_HINTS)
    has_action = any(k in q_clean for k in ("كود", "تفعيل", "اشتراك", "ضريبة", "احسب", "قارن", "رشح", "code", "activate", "tax", "price", "compare", "cost", "how much", "كام", "بكام"))
    has_numbers = bool(re.search(r"\b\d+\b", text))

    if has_numbers or has_action or (has_telecom_hint and len(text.split()) > 2):
        return False

    # Guard: if the text contains upgrade/follow-up triggers or pronoun triggers,
    # it's a follow-up question, NOT a greeting (prevents "the higher tiers" → greeting)
    has_upgrade = any(u in q_clean for u in _UPGRADE_TRIGGERS)
    has_pronoun = any(p in q_clean for p in _PRONOUN_TRIGGERS)
    if has_upgrade or has_pronoun:
        return False

    for pat in _GREETING_PATTERNS:
        if pat.search(text):
            if len(text.split()) <= 8:
                return True
    return any(hint in q_clean for hint in GREETING_HINTS) if len(text.split()) <= 4 else False


_PRONOUN_TRIGGERS = {
    # Demonstratives & Pronouns
    "دي", "ده", "ديه", "دول", "دا", "هذه", "هذا", "هذول", "هؤلاء", "تلك", "ذلك",
    "هو", "هي", "هم", "هما", "هن",
    # Prepositions with attached pronouns
    "بينها", "بينهما", "بينهم", "بينه", "معاها", "معاه", "معاهم", "عنها", "عنه", "عنهم",
    "فيها", "فيه", "فيهم", "لها", "له", "ليهم", "بيها", "بيه", "بيهم", "منها", "منه", "منهم",
    "إياها", "اياها", "نفسها", "نفسه",
    # Relative / Alternatives
    "تانية", "تانيه", "ثانية", "أخرى", "اخرى", "الأولى", "الاولى", "السابقة", "السابق",
    "اللي فاتت", "اللي قبلها", "غيرها", "غيره",
    # Comparisons
    "قارن", "قارنها", "قارنهم", "مقارنة", "مقارنه", "الفرق", "أحسن ولا", "احسن ولا",
    "أفضل ولا", "افضل ولا", "مين أحسن", "مين احسن", "مين أفضل", "مين افضل", "أيهما", "ايهما",
    "أرخص ولا", "ارخص ولا", "أغلى ولا", "اغلى ولا", "ولا دي", "ولا ده",
    # Follow-ups
    "طب", "طيب", "طب هي", "طب هو", "طب سعرها", "طب كودها", "طب والضريبة", "طب والنت",
    "طب والمكالمات", "طب ورصيدها", "طب وباقي", "طب وبالنسبة", "وبالنسبة", "طب و", "كمان",
    "ليه", "ليه مش", "ليه ما", "اشمعنى", "اشمعنا", "مش أحسن", "مش احسن",
    # English
    "it", "its", "that", "this", "these", "those", "them", "they", "which one",
    "the other", "previous", "earlier", "compare", "comparison", "difference", "vs", "versus",
    "better", "cheaper", "what about", "how about", "instead", "why not", "why isn't",
    # Upgrade / higher-tier follow-ups
    "higher", "bigger", "larger", "more", "next", "other", "else",
    "upgrade", "premium", "tier", "tiers",
    "أعلى", "اعلى", "أكبر", "اكبر", "أغلى", "اغلى",
}

_SAME_BUDGET_TRIGGERS = (
    "بنفس السعر", "بنفس السعر ده", "بنفس الميزانية", "بنفس المبلغ", "بنفس الفلوس",
    "في نفس الرينج", "نفس السعر", "نفس الميزانية", "same price", "same budget",
    "same cost", "that same price", "for the same price", "with the same budget",
)

# Triggers that indicate the user wants plans ABOVE what was already shown
_UPGRADE_TRIGGERS = {
    # English
    "higher", "bigger", "more expensive", "higher tier", "higher tiers",
    "bigger plan", "bigger plans", "more data", "larger", "next tier",
    "upgrade", "step up", "level up", "premium",
    "what else", "other options", "more options", "show me more",
    # Arabic
    "أعلى", "اعلى", "أكبر", "اكبر", "أغلى", "اغلى", "أكتر", "اكتر",
    "باقة أكبر", "باقة اكبر", "باقات أعلى", "باقات اعلى",
    "ترقية", "أحسن من كده", "احسن من كده", "في حاجة أحسن", "في حاجة احسن",
    "خيارات تانية", "خيارات اكتر", "عايز أعلى", "عايز اعلى",
    "عندكم أعلى", "عندكم اعلى", "ممكن أغلى", "ممكن اغلى",
}


def _detect_family(text: str) -> Any:
    text = (text or "").lower()
    if "كونكت" in text or "connect" in text:
        return "super_connect"
    if "حكاية" in text or "حكايه" in text or "hekaya" in text:
        if "نت" in text or "internet" in text or "إنترنت" in text or "انترنت" in text:
            return "hekaya_internet"
        if "مكس" in text or "مكسات" in text or "mix" in text:
            return "hekaya_mixat"
        return "hekaya"
    if "اقوى" in text or "أقوى" in text or "اقوي" in text or "أقوي" in text or "aqwa" in text:
        return "aqwa_card"
    if (
        "ايميرالد" in text or "إيميرالد" in text or "امرالد" in text or "إمرالد" in text
        or "اميرالد" in text or "ايمرالد" in text or "emerald" in text
    ):
        return "emerald"
    if "داتا" in text or "dataline" in text or "راوتر" in text or "mifi" in text:
        return "dataline"
    catalog = get_catalog()
    for fid, fam in catalog.families.items():
        if (
            fam["family_name_en"].lower() in text
            or fam["family_name_ar"] in text
            or fid.replace("_", " ") in text
        ):
            return fid
    return None


def _detect_all_families(text: str) -> List[str]:
    text = (text or "").lower()
    found = []
    if "كونكت" in text or "connect" in text:
        found.append("super_connect")
    if "حكاية" in text or "حكايه" in text or "hekaya" in text:
        if "نت" in text or "internet" in text or "إنترنت" in text or "انترنت" in text:
            found.append("hekaya_internet")
        else:
            found.append("hekaya_mixat")
    if "اقوى" in text or "أقوى" in text or "اقوي" in text or "أقوي" in text or "aqwa" in text:
        found.append("aqwa_card")
    if (
        "ايميرالد" in text or "إيميرالد" in text or "امرالد" in text or "إمرالد" in text
        or "اميرالد" in text or "ايمرالد" in text or "emerald" in text
    ):
        found.append("emerald")
    if "داتا" in text or "dataline" in text or "راوتر" in text or "mifi" in text:
        found.append("dataline")
    return list(dict.fromkeys(found))


def _detect_last_budget(text: str) -> Any:
    for pat in _BUDGET_PATTERNS:
        matches = pat.findall(text or "")
        if matches:
            return float(matches[-1])
    return None


_LANG_SWITCH_EN = [
    re.compile(r"^\s*(?:can\s+you\s+)?(?:please\s+)?(?:speak|write|reply|respond|answer|explain|translate(?:\s+to)?\s+)?(?:in\s+)?english(?:\s+(?:pls|please))?\s*[!?.؟]*$", re.IGNORECASE),
    re.compile(r"^\s*(?:in\s+en|en\s+pls|en\s+please)\s*[!?.؟]*$", re.IGNORECASE),
    re.compile(r"^\s*(?:ممكن\s+|خليه\s+|اكتب\s+|ترجم\s+(?:لـ|إلى|ل)?\s*|كلمنا\s+)?(?:بالانجليزي|بالإنجليزي|انجليزي|إنجليزي)(?:\s+(?:لو\s+سمحت|من\s+فضلك|بليز|pls|please))?\s*[!?.؟]*$", re.IGNORECASE),
]

_LANG_SWITCH_AR = [
    re.compile(r"^\s*(?:can\s+you\s+)?(?:please\s+)?(?:speak|write|reply|respond|answer|explain|translate(?:\s+to)?\s+)?(?:in\s+)?arabic(?:\s+(?:pls|please))?\s*[!?.؟]*$", re.IGNORECASE),
    re.compile(r"^\s*(?:in\s+ar|ar\s+pls|ar\s+please)\s*[!?.؟]*$", re.IGNORECASE),
    re.compile(r"^\s*(?:ممكن\s+|خليه\s+|اكتب\s+|ترجم\s+(?:لـ|إلى|ل)?\s*|كلمنا\s+)?(?:بالعربي|باللغة\s+العربية|عربي)(?:\s+(?:لو\s+سمحت|من\s+فضلك|بليز|pls|please))?\s*[!?.؟]*$", re.IGNORECASE),
]


def _detect_lang_switch(text: str) -> Optional[str]:
    clean = (text or "").strip()
    for pat in _LANG_SWITCH_EN:
        if pat.match(clean):
            return "en"
    for pat in _LANG_SWITCH_AR:
        if pat.match(clean):
            return "ar"
    return None


def _detect_usage_focus(text: str) -> Optional[str]:
    t = (text or "").lower()
    if not t:
        return None

    # 1. Negative phrases: e.g. "مش عايز دقايق", "not minutes", "without calls", "مش محتاج نت"
    no_voice = re.search(r"(?:مش\s*(?:عايز|محتاج)|بدون|من\s*غير|لا\s*[أا]ريد|not\s*need|don'?t\s*need|no\s*need|without|no)\s*(?:دقايق|دقيقة|دقائق|مكالمات|صوت|calls|minutes|mins|voice|مكس|مكسات|mix)", t)
    no_data = re.search(r"(?:مش\s*(?:عايز|محتاج)|بدون|من\s*غير|لا\s*[أا]ريد|not\s*need|don'?t\s*need|no\s*need|without|no)\s*(?:نت|انترنت|إنترنت|بيانات|ميجا|جيجا|data|internet|mb|gb)", t)
    if no_voice and not no_data:
        return "data"
    if no_data and not no_voice:
        return "minutes"

    # 2. Comparative phrases:
    # Pattern A: Data MORE than Voice (e.g. "internet more than minutes", "نت اكتر من مكالمات", "data over calls")
    data_more_than_voice = re.search(
        r"(?:نت|انترنت|إنترنت|بيانات|ميجا|جيجا|data|internet|mb|gb|browsing|تصفح)\s*"
        r"(?:[^\w\s]+\s*)?"
        r"(?:more\s+than|more\s+then|>|over|rather\s+than|instead\s+of|[أا]كتر\s*من|[أا]كبر\s*من|[أا]زيد\s*من|فوق|قبل|بدل|عن)\s*"
        r"(?:[^\w\s]+\s*)?"
        r"(?:دقايق|دقيقة|دقائق|مكالمات|صوت|calls|minutes|mins|voice|مكس|مكسات|mix)",
        t,
    )
    # Pattern B: "more data than minutes", "اكتر نت من مكالمات"
    more_data_than_voice = re.search(
        r"(?:more|[أا]كتر|[أا]زيد|كتير)\s*(?:of\s*)?"
        r"(?:نت|انترنت|إنترنت|بيانات|ميجا|جيجا|data|internet|mb|gb)\s*"
        r"(?:than|then|[أا]كتر\s*من|عن|بدل)\s*"
        r"(?:دقايق|دقيقة|دقائق|مكالمات|صوت|calls|minutes|mins|voice|مكس|مكسات|mix)",
        t,
    )
    # Pattern C: Voice LESS than Data (e.g. "minutes less than internet", "دقايق اقل من نت")
    voice_less_than_data = re.search(
        r"(?:دقايق|دقيقة|دقائق|مكالمات|صوت|calls|minutes|mins|voice|مكس|مكسات|mix)\s*"
        r"(?:[^\w\s]+\s*)?"
        r"(?:less\s+than|less\s+then|<|[أا]قل\s*من)\s*"
        r"(?:[^\w\s]+\s*)?"
        r"(?:نت|انترنت|إنترنت|بيانات|ميجا|جيجا|data|internet|mb|gb)",
        t,
    )
    if data_more_than_voice or more_data_than_voice or voice_less_than_data:
        return "data"

    # Pattern D: Voice MORE than Data (e.g. "minutes more than internet", "دقايق اكتر من نت", "calls over data")
    voice_more_than_data = re.search(
        r"(?:دقايق|دقيقة|دقائق|مكالمات|صوت|calls|minutes|mins|voice|مكس|مكسات|mix)\s*"
        r"(?:[^\w\s]+\s*)?"
        r"(?:more\s+than|more\s+then|>|over|rather\s+than|instead\s+of|[أا]كتر\s*من|[أا]كبر\s*من|[أا]زيد\s*من|فوق|قبل|بدل|عن)\s*"
        r"(?:[^\w\s]+\s*)?"
        r"(?:نت|انترنت|إنترنت|بيانات|ميجا|جيجا|data|internet|mb|gb)",
        t,
    )
    # Pattern E: "more minutes than data", "اكتر مكالمات من نت"
    more_voice_than_data = re.search(
        r"(?:more|[أا]كتر|[أا]زيد|كتير)\s*(?:of\s*)?"
        r"(?:دقايق|دقيقة|دقائق|مكالمات|صوت|calls|minutes|mins|voice|مكس|مكسات|mix)\s*"
        r"(?:than|then|[أا]كتر\s*من|عن|بدل)\s*"
        r"(?:نت|انترنت|إنترنت|بيانات|ميجا|جيجا|data|internet|mb|gb)",
        t,
    )
    # Pattern F: Data LESS than Voice (e.g. "data less than minutes", "نت اقل من مكالمات")
    data_less_than_voice = re.search(
        r"(?:نت|انترنت|إنترنت|بيانات|ميجا|جيجا|data|internet|mb|gb)\s*"
        r"(?:[^\w\s]+\s*)?"
        r"(?:less\s+than|less\s+then|<|[أا]قل\s*من)\s*"
        r"(?:[^\w\s]+\s*)?"
        r"(?:دقايق|دقيقة|دقائق|مكالمات|صوت|calls|minutes|mins|voice|مكس|مكسات|mix)",
        t,
    )
    if voice_more_than_data or more_voice_than_data or data_less_than_voice:
        return "minutes"

    # 3. Explicit balanced / both: e.g. "الاثنين", "دقايق ونت", "calls and internet", "balanced"
    has_balanced_kw = any(k in t for k in ("متوازن", "متوازنة", "الاتنين", "الاثنين", "سوا", "مع بعض", "balanced", "both"))
    has_voice = any(k in t for k in ("دقايق", "دقيقة", "دقائق", "مكالمات", "صوت", "calls", "minutes", "mins", "voice", "مكس", "مكسات", "mix"))
    has_data = any(k in t for k in ("نت", "انترنت", "إنترنت", "بيانات", "ميجا", "جيجا", "data", "internet", "mb", "gb"))
    if has_balanced_kw or (has_voice and has_data):
        return "balanced"

    # 4. Pure single priority:
    if has_data and not has_voice:
        return "data"
    if has_voice and not has_data:
        return "minutes"

    return None


def _detect_device_type(text: str) -> Optional[str]:
    t = (text or "").lower()
    if any(k in t for k in ("راوتر", "ماي فاي", "مايفاي", "mifi", "router", "modem", "مودم", "usb")):
        return "router"
    if any(k in t for k in ("دقايق", "دقيقة", "دقائق", "مكالمات", "صوت", "مكس", "مكسات", "موبايل", "هاتف", "تليفون", "خط", "phone", "mobile", "calls", "minutes", "voice")):
        return "phone"
    return None


def _resolve_last_package_from_history(history_text: str) -> Optional[Dict[str, Any]]:
    """Scan conversation history backwards to resolve the most recently referenced package/tier in < 1ms."""
    if not history_text or not history_text.strip():
        return None
    catalog = get_catalog()
    hist_lower = history_text.lower()

    best_tier = None
    best_pos = -1
    best_family = None

    for fid, fam in catalog.families.items():
        for tier in fam["tiers"]:
            price_val = tier["price_egp"]
            price_str = str(int(price_val)) if price_val == int(price_val) else str(price_val)
            names = [
                tier["name_en"].lower(),
                tier.get("name_ar", "").lower(),
                f"حكاية {price_str}",
                f"حكايه {price_str}",
                f"hekaya {price_str}",
                f"مكسات {price_str}",
                f"mixat {price_str}",
                f"كونكت {price_str}",
                f"connect {price_str}",
                f"إمرالد {price_str}",
                f"emerald {price_str}",
                f"أقوى كارت {price_str}",
                f"aqwa {price_str}",
            ]
            for name in names:
                if not name:
                    continue
                pos = hist_lower.rfind(name)
                if pos > best_pos:
                    best_pos = pos
                    best_tier = tier
                    best_family = fid

    if best_tier and best_pos != -1:
        return {
            "tier": best_tier,
            "family": best_family,
            "tier_price_egp": float(best_tier["price_egp"]),
            "package_name_raw": best_tier.get("name_ar") or best_tier["name_en"],
        }
    return None


def _detect_highest_tier_price_from_history(history: List[Dict[str, Any]]) -> Optional[float]:
    """Find the highest tier price mentioned in the most recent assistant message (or earlier messages),
    used to calculate the price floor for upgrade / higher-tier queries."""
    if not history:
        return None
    catalog = get_catalog()
    assistant_msgs = [m.get("content", "") for m in history if m.get("role") in ("assistant", "ai") and m.get("content")]
    if not assistant_msgs:
        return None
    last_assistant_text = assistant_msgs[-1].lower()
    found_prices = []
    for fid, fam in catalog.families.items():
        for tier in fam["tiers"]:
            price_val = tier["price_egp"]
            price_str = str(int(price_val)) if price_val == int(price_val) else str(price_val)
            fam_en = fam.get("family_name_en", "").lower()
            fam_ar = fam.get("family_name_ar", "").lower()
            tier_en = tier["name_en"].lower()
            tier_ar = tier.get("name_ar", "").lower()
            if (
                tier_en in last_assistant_text
                or (tier_ar and tier_ar in last_assistant_text)
                or f"{fam_en} {price_str}" in last_assistant_text
                or f"{fam_ar} {price_str}" in last_assistant_text
                or f"حكاية {price_str}" in last_assistant_text
                or f"hekaya {price_str}" in last_assistant_text
            ):
                found_prices.append(float(price_val))
    if found_prices:
        return max(found_prices)
    return None


def _try_fast_classify(
    question: str,
    history_text: str = "",
    user_history_text: str = "",
    history: Optional[List[Dict[str, Any]]] = None,
) -> Any:
    """Fast deterministic intent and entity classifier (< 1ms).
    Avoids spending an expensive 3-5s LLM call for direct, unambiguous telecom questions."""
    q_lower = (question or "").strip().lower()

    # Competitors go to standard path/safe response
    if _has_competitor_mention(question):
        return None

    if _is_fast_greeting(question):
        return ClassifyResult(
            language=detect_language(question),
            intent="greeting",
            family=None,
            package_name_raw=None,
            tier_price_egp=None,
            budget_egp=None,
            is_out_of_scope=False,
            keywords=["greeting"],
        )

    has_history = bool(history_text and history_text.strip())
    has_pronoun_or_relative = any(p in q_lower for p in _PRONOUN_TRIGGERS)
    is_comparison_query = any(k in q_lower for k in ("قارن", "مقارنة", "مقارنه", "الفرق", "أحسن ولا", "احسن ولا", "أفضل ولا", "افضل ولا", "compare", "difference", "vs", "versus"))
    has_same_budget = any(b in q_lower for b in _SAME_BUDGET_TRIGGERS)

    # First-turn or multi-turn comparison queries should go to LLM
    # to accurately extract all entities and nuanced differences.
    if is_comparison_query:
        return None

    # Multi-turn queries with same-budget triggers ("بنفس السعر", "بنفس الميزانية", "same price", etc.):
    if has_history and has_same_budget:
        hist_budget = _detect_last_budget(user_history_text) or _detect_last_budget(history_text)
        if hist_budget is not None:
            q_device = _detect_device_type(question)
            q_family = _detect_family(question)
            q_usage = _detect_usage_focus(question)

            if q_device == "router" or any(k in q_lower for k in ("mifi", "راوتر", "ماي فاي", "مايفاي", "مودم", "usb")):
                q_family = "dataline"
                q_device = "router"
                q_usage = "data"
            elif q_usage == "minutes":
                q_family = "hekaya_mixat"
                q_device = "phone"
            elif q_usage == "data" and q_device != "router":
                q_family = q_family or "hekaya_internet"
                q_device = "phone"
            elif not q_device and not q_family:
                q_device = _detect_device_type(history_text) or "phone"
                q_family = _detect_family(history_text) or "hekaya_mixat"

            return ClassifyResult(
                language=detect_language(question),
                intent="recommendation",
                family=q_family,
                package_name_raw=None,
                tier_price_egp=None,
                budget_egp=hist_budget,
                device_type=q_device,
                usage_focus=q_usage,
                is_out_of_scope=False,
                keywords=[q_family] if q_family else [],
            )

    # ── Upgrade / higher-tier follow-ups ─────────────────────────────────────
    # Detects "higher tiers", "bigger plans", "عايز أعلى" etc.
    # Finds the last recommended tier's price and returns a recommendation
    # with min_price_egp (no upper budget cap), so the engine returns plans above.
    has_upgrade_trigger = any(u in q_lower for u in _UPGRADE_TRIGGERS)
    if has_history and has_upgrade_trigger:
        min_price = None
        if history:
            min_price = _detect_highest_tier_price_from_history(history)
        if min_price is None:
            resolved_pkg = _resolve_last_package_from_history(history_text)
            hist_budget = _detect_last_budget(user_history_text) or _detect_last_budget(history_text)
            if resolved_pkg:
                min_price = resolved_pkg["tier_price_egp"]
            elif hist_budget:
                min_price = hist_budget

        if min_price is not None:
            q_device = _detect_device_type(question) or _detect_device_type(history_text) or "phone"
            q_family = _detect_family(question) or _detect_family(history_text)
            q_usage = _detect_usage_focus(question) or _detect_usage_focus(history_text)

            if q_device == "router" or any(k in q_lower for k in ("mifi", "راوتر", "ماي فاي", "مايفاي", "مودم", "usb")):
                q_family = "dataline"
                q_device = "router"
                q_usage = "data"
            elif q_usage == "data" and q_device != "router":
                q_family = q_family or "hekaya_internet"
            elif q_usage == "minutes":
                q_family = q_family or "hekaya_mixat"
                q_device = "phone"

            return ClassifyResult(
                language=detect_language(question),
                intent="recommendation",
                family=q_family,
                package_name_raw=None,
                tier_price_egp=None,
                budget_egp=None,  # No upper budget cap
                device_type=q_device,
                usage_focus=q_usage,
                is_out_of_scope=False,
                keywords=[q_family, "upgrade"] if q_family else ["upgrade"],
                min_price_egp=min_price,
            )

    # Multi-turn queries with pronouns/referents: attempt fast referent resolution from conversation history!
    # Only resolve to previous package if NOT switching device or family or asking with same budget!
    q_explicit_device = _detect_device_type(question)
    q_explicit_family = _detect_family(question)
    device_switched = bool(q_explicit_device and q_explicit_device != _detect_device_type(history_text))
    if has_history and has_pronoun_or_relative and not has_same_budget and not device_switched and not q_explicit_family and not has_upgrade_trigger:
        resolved = _resolve_last_package_from_history(history_text)
        if resolved:
            language = detect_language(question)
            res_family = resolved["family"]
            res_tier_price = resolved["tier_price_egp"]
            res_pkg_raw = resolved["package_name_raw"]
            device_type = _detect_device_type(question) or _detect_device_type(history_text)
            usage_focus = _detect_usage_focus(question) or _detect_usage_focus(history_text)
            if usage_focus == "minutes" and not device_type:
                device_type = "phone"

            # Check if user is asking about price / tax
            if not has_same_budget and any(k in q_lower for k in (
                "ضريبة", "شامل الضريبة", "بعد الضريبة", "احسب", "tax", "calculate",
                "رصيد صافي", "صافي", "أدفع كام", "ادفع كام", "هدفع كام", "كام ادفع",
                "سعرها", "بكام", "سعره", "cost", "price", "how much", "كام"
            )):
                return ClassifyResult(
                    language=language,
                    intent="price_calculation",
                    family=res_family,
                    package_name_raw=res_pkg_raw,
                    tier_price_egp=res_tier_price,
                    budget_egp=None,
                    device_type=device_type,
                    usage_focus=usage_focus,
                    is_out_of_scope=False,
                    keywords=[res_family],
                )

            # Check if user is asking about activation code
            if any(k in q_lower for k in ("كود", "كودها", "كوده", "تفعيل", "اشتراك", "الغي", "إلغاء", "الغاء", "code", "activate", "ussd")):
                return ClassifyResult(
                    language=language,
                    intent="activation_code",
                    family=res_family,
                    package_name_raw=res_pkg_raw,
                    tier_price_egp=res_tier_price,
                    budget_egp=None,
                    device_type=device_type,
                    usage_focus=usage_focus,
                    is_out_of_scope=False,
                    keywords=[res_family],
                )

            # Check if user is asking about package details/quota/units
            if any(k in q_lower for k in ("رصيد", "دقايق", "نت", "تفاصيل", "تفاصيلها", "مميزات", "كوتة", "شحن", "تجديد", "details", "quota", "units")):
                return ClassifyResult(
                    language=language,
                    intent="package_inquiry",
                    family=res_family,
                    package_name_raw=res_pkg_raw,
                    tier_price_egp=res_tier_price,
                    budget_egp=None,
                    device_type=device_type,
                    usage_focus=usage_focus,
                    is_out_of_scope=False,
                    keywords=[res_family],
                )
        # If not cleanly resolvable via fast path, fall back to LLM classification
        return None

    language = detect_language(question)
    q_family = _detect_family(question)
    q_budget = _detect_last_budget(question)
    has_pronoun_or_relative = any(p in q_lower for p in _PRONOUN_TRIGGERS)

    if q_budget is not None and not has_pronoun_or_relative:
        family = q_family
    else:
        hist_family = _detect_family(user_history_text) if user_history_text else None
        family = q_family or hist_family

    hist_budget = _detect_last_budget(user_history_text) if user_history_text else None
    budget = q_budget or hist_budget
    numbers = re.findall(r"\b\d+(?:\.\d+)?\b", question)

    device_type = _detect_device_type(question) or _detect_device_type(user_history_text)
    usage_focus = _detect_usage_focus(question) or _detect_usage_focus(user_history_text)
    if device_type in ("router", "mifi", "modem", "usb") or any(k in q_lower for k in ("mifi", "راوتر", "ماي فاي", "مايفاي", "مودم", "usb")):
        device_type = "router"
        family = "dataline"
        usage_focus = "data"
    elif usage_focus == "minutes" and not device_type:
        device_type = "phone"

    # 1. Activation code intent (only if direct and unambiguous)
    if any(k in q_lower for k in ("كود", "تفعيل", "اشتراك", "الغي", "إلغاء", "الغاء", "code", "activate", "ussd")):
        if q_family or numbers:
            return ClassifyResult(
                language=language,
                intent="activation_code",
                family=family,
                package_name_raw=question if family else None,
                tier_price_egp=float(numbers[0]) if numbers else None,
                budget_egp=budget,
                device_type=device_type,
                usage_focus=usage_focus,
                is_out_of_scope=False,
                keywords=[family] if family else [],
            )

    # 2. Price calculation / tax intent
    if any(k in q_lower for k in (
        "ضريبة", "شامل الضريبة", "بعد الضريبة", "احسب", "tax", "calculate",
        "رصيد صافي", "صافي", "أدفع كام", "ادفع كام", "هدفع كام", "كام ادفع",
        "net balance", "how much do i pay", "how much to pay", "how much money do i need to pay"
    )):
        return ClassifyResult(
            language=language,
            intent="price_calculation",
            family=family,
            package_name_raw=question if family else None,
            tier_price_egp=float(numbers[0]) if numbers else None,
            budget_egp=budget,
            device_type=device_type,
            usage_focus=usage_focus,
            is_out_of_scope=False,
            keywords=[family] if family else [],
        )

    # 3. Recommendation / Budget inquiry
    is_recommendation_query = (
        (budget is not None and not any(k in q_lower for k in ("pay", "net balance", "صافي", "أدفع", "ادفع", "شحن")))
        or any(k in q_lower for k in ("رشحلي", "رشح", "أحسن باقة", "احسن باقة", "اقتراح", "افضل باقة", "أفضل باقة", "recommend", "best plan", "مناسبة", "تناسبني", "ريكومند", "ريكوميند"))
    )
    if is_recommendation_query:
        if not device_type and usage_focus != "data":
            device_type = "phone"
        elif not device_type and any(k in q_lower for k in ("دقايق", "دقيقة", "دقائق", "مكالمات", "صوت", "calls", "minutes", "voice", "مكس", "مكسات", "موبايل", "هاتف", "تليفون", "خط", "phone", "mobile")):
            device_type = "phone"

        if not family:
            if usage_focus == "data" and device_type != "router":
                family = "hekaya_internet"
            elif usage_focus == "minutes":
                family = "hekaya_mixat"

        return ClassifyResult(
            language=language,
            intent="recommendation",
            family=family,
            package_name_raw=None,
            tier_price_egp=None,
            budget_egp=budget,
            device_type=device_type or "phone",
            usage_focus=usage_focus,
            is_out_of_scope=False,
            keywords=[family] if family else [],
        )

    # 3b. Comparison intent
    is_comparison_query = any(k in q_lower for k in (
        "قارن", "مقارنة", "مقارنه", "الفرق", "أحسن ولا", "احسن ولا", "أفضل ولا", "افضل ولا",
        "compare", "comparison", "difference", "versus", " vs ", " vs. ", " between "
    ))
    if is_comparison_query:
        catalog = get_catalog()
        comp_families = []
        comp_entities = []
        for fid, fam in catalog.families.items():
            f_en = fam["family_name_en"].lower()
            f_ar = fam["family_name_ar"].lower()
            fid_clean = fid.replace("_", " ")
            if f_en in q_lower or f_ar in q_lower or fid_clean in q_lower:
                if fid not in comp_families:
                    comp_families.append(fid)
                if fam["family_name_en"] not in comp_entities:
                    comp_entities.append(fam["family_name_en"])
            elif fid == "hekaya_mixat" and ("mixat" in q_lower or "مكسات" in q_lower):
                if "hekaya_mixat" not in comp_families:
                    comp_families.append("hekaya_mixat")
                if "Hekaya Mixat" not in comp_entities:
                    comp_entities.append("Hekaya Mixat")
            elif fid == "hekaya_internet" and (("hekaya" in q_lower and "internet" in q_lower) or ("حكاية" in q_lower and "انترنت" in q_lower) or ("حكاية" in q_lower and "إنترنت" in q_lower)):
                if "hekaya_internet" not in comp_families:
                    comp_families.append("hekaya_internet")
                if "Hekaya Internet" not in comp_entities:
                    comp_entities.append("Hekaya Internet")

        for tier in catalog.all_tiers():
            t_en = tier["name_en"].lower()
            t_ar = tier.get("name_ar", "").lower()
            if t_en in q_lower or (t_ar and t_ar in q_lower):
                if tier["name_en"] not in comp_entities:
                    comp_entities.append(tier["name_en"])
                if tier.get("family") and tier["family"] not in comp_families:
                    comp_families.append(tier["family"])

        primary_family = comp_families[0] if comp_families else (q_family or family or "hekaya")
        if "hekaya_mixat" in comp_families and "hekaya_internet" in comp_families:
            primary_family = "hekaya"

        return ClassifyResult(
            language=language,
            intent="comparison",
            family=primary_family,
            package_name_raw=question,
            tier_price_egp=float(numbers[0]) if numbers else None,
            budget_egp=budget,
            device_type=device_type,
            usage_focus=usage_focus,
            is_out_of_scope=False,
            keywords=comp_families or [primary_family],
            entities=comp_entities,
        )

    # 4. Package inquiry:
    # Only if family is explicitly in the current question, OR if question has package signals + history family
    has_inquiry_signals = bool(numbers) or any(
        w in q_lower for w in ("باقة", "باقات", "سعر", "اسعار", "أسعار", "كام", "بكام", "تفاصيل", "مميزات", "رصيد", "ميجا", "جيجا", "package", "plan", "price", "cost", "details", "quota", "mb", "gb")
    )
    if q_family:
        return ClassifyResult(
            language=language,
            intent="package_inquiry",
            family=q_family,
            package_name_raw=question,
            tier_price_egp=float(numbers[0]) if numbers else None,
            budget_egp=q_budget,
            is_out_of_scope=False,
            keywords=[q_family],
        )
    elif family and has_inquiry_signals and not has_history:
        return ClassifyResult(
            language=language,
            intent="package_inquiry",
            family=family,
            package_name_raw=question,
            tier_price_egp=float(numbers[0]) if numbers else None,
            budget_egp=q_budget,
            is_out_of_scope=False,
            keywords=[family],
        )

    return None


def _fallback_classify(question: str) -> ClassifyResult:
    """Regex-only classification used only if the LLM call itself fails."""
    language = detect_language(question)
    q_lower = (question or "").lower()

    if _has_competitor_mention(question):
        return ClassifyResult(
            language=language,
            intent="out_of_scope",
            is_out_of_scope=True,
            keywords=["competitor"],
        )

    if _is_fast_greeting(question):
        return ClassifyResult(
            language=language,
            intent="greeting",
            is_out_of_scope=False,
            keywords=["greeting"],
        )

    family = _detect_family(question)
    numbers = re.findall(r"\d+(?:\.\d+)?", question)

    if any(k in q_lower for k in ("كود", "تفعيل", "اشتراك", "code", "activate", "ussd")):
        return ClassifyResult(
            language=language,
            intent="activation_code",
            family=family,
            package_name_raw=question if family else None,
            tier_price_egp=float(numbers[0]) if numbers else None,
            is_out_of_scope=False,
            keywords=[family] if family else [],
        )

    if any(k in q_lower for k in ("قارن", "مقارنة", "مقارنه", "الفرق", "أحسن ولا", "احسن ولا", "أفضل ولا", "افضل ولا", "compare", "difference", "vs", "versus")):
        return ClassifyResult(
            language=language,
            intent="comparison",
            family=family,
            package_name_raw=question if family else None,
            tier_price_egp=float(numbers[0]) if numbers else None,
            is_out_of_scope=False,
            keywords=[family] if family else [],
        )

    if any(k in q_lower for k in ("ضريبة", "شامل الضريبة", "بعد الضريبة", "احسب", "tax", "calculate")):
        return ClassifyResult(
            language=language,
            intent="price_calculation",
            family=family,
            package_name_raw=question if family else None,
            tier_price_egp=float(numbers[0]) if numbers else None,
            is_out_of_scope=False,
            keywords=[family] if family else [],
        )

    return ClassifyResult(
        language=language,
        intent="package_inquiry",
        family=family,
        package_name_raw=question if family else None,
        tier_price_egp=float(numbers[0]) if numbers else None,
        is_out_of_scope=False,
        keywords=[family] if family else [],
    )


def classify_node(state: AgentState) -> Dict[str, Any]:
    start = now()
    question = state.get("question", "")

    if _is_fast_greeting(question):
        language = detect_language(question)
        return {
            "language": language,
            "intent": "greeting",
            "category": "",
            "service": "",
            "line_type": "",
            "is_out_of_scope": False,
            "is_unsupported_service": False,
            "keywords": [],
            "entities": [],
            "workflow_trace": [step(
                "intent", "2. Intent Classifier", "٢. تصنيف النية والتوجيه",
                description_en="Recognized as a greeting — routed to fast greeting response.",
                badge="Fast Path", status="completed",
                details={"intent": "greeting", "language": language},
                latency_ms=elapsed_ms(start),
            )],
        }

    # ── Fast out-of-scope detection (<1ms, before LLM) ────────────────────────
    if _is_fast_out_of_scope(question):
        language = detect_language(question)
        return {
            "language": language,
            "intent": "out_of_scope",
            "category": "",
            "service": "",
            "line_type": "",
            "is_out_of_scope": True,
            "is_unsupported_service": True,
            "budget_egp": None,
            "device_type": None,
            "usage_focus": None,
            "package_name_raw": None,
            "tier_price_egp": None,
            "keywords": [],
            "entities": [],
            "workflow_trace": [
                step(
                    "intent", "2. Intent Classifier", "٢. تصنيف النية والتوجيه",
                    description_en="Detected as out-of-scope topic (fast regex path) — routed to safe response.",
                    badge="Out-of-Scope", status="blocked",
                    details={"intent": "out_of_scope", "language": language},
                    latency_ms=elapsed_ms(start),
                ),
                step(
                    "understand", "3. Query Understanding", "٣. تحليل وتنميط الاستفسار",
                    description_en="Skipped — non-telecom topic confirmed.",
                    badge="Skipped", status="completed",
                    latency_ms=0,
                ),
            ],
        }

    # ── Fast competitor redirection (<1ms, before LLM) ───────────────────────
    # Queries asking strictly about competitors (Vodafone, Orange, WE) without
    # an e& Egypt context/comparison are routed immediately to safe response.
    q_lower = (question or "").lower()
    has_competitor = _has_competitor_mention(question)
    has_etisalat = any(e in q_lower for e in ("etisalat", "اتصالات", "e&", "إي آند"))
    if has_competitor and not has_etisalat:
        language = detect_language(question)
        return {
            "language": language,
            "intent": "out_of_scope",
            "category": "",
            "service": "",
            "line_type": "",
            "is_out_of_scope": True,
            "is_unsupported_service": True,
            "budget_egp": None,
            "device_type": None,
            "usage_focus": None,
            "package_name_raw": None,
            "tier_price_egp": None,
            "keywords": ["competitor"],
            "entities": [],
            "workflow_trace": [
                step(
                    "intent", "2. Intent Classifier", "٢. تصنيف النية والتوجيه",
                    description_en="Competitor inquiry detected — routed to safe response (e& Egypt assistant only).",
                    badge="Competitor", status="blocked",
                    details={"intent": "out_of_scope", "language": language},
                    latency_ms=elapsed_ms(start),
                ),
                step(
                    "understand", "3. Query Understanding", "٣. تحليل وتنميط الاستفسار",
                    description_en="Skipped — competitor topic confirmed.",
                    badge="Skipped", status="completed",
                    latency_ms=0,
                ),
            ],
        }



    history = (state.get("history") or [])[-6:]
    history_text = "\n".join(f"{m.get('role')}: {m.get('content')}" for m in history) or ""

    # Check for language switch request (e.g. "in english pls", "بالعربي", etc.)
    target_lang = _detect_lang_switch(question)
    is_lang_switch = False
    lang_switch_user_q = None

    if target_lang:
        prior_user_msgs = [m.get("content", "") for m in history if m.get("role") in ("user", "human") and m.get("content")]
        for u_msg in reversed(prior_user_msgs):
            if not _detect_lang_switch(u_msg):
                lang_switch_user_q = u_msg
                break

        if lang_switch_user_q:
            is_lang_switch = True
        else:
            return {
                "language": target_lang,
                "intent": "greeting",
                "category": "",
                "service": "",
                "line_type": "",
                "is_out_of_scope": False,
                "is_unsupported_service": False,
                "keywords": [],
                "entities": [],
                "workflow_trace": [step(
                    "intent", "2. Intent Classifier", "٢. تصنيف النية والتوجيه",
                    description_en=f"Language switch greeting ({target_lang}).",
                    badge="Fast Path", status="completed",
                    details={"intent": "greeting", "language": target_lang},
                    latency_ms=elapsed_ms(start),
                )],
            }

    # If it's a language switch for a previous inquiry, classify the actual underlying inquiry
    classify_q = lang_switch_user_q if is_lang_switch and lang_switch_user_q else question

    user_history_text = "\n".join(m.get("content", "") for m in history if m.get("role") in ("user", "human"))

    # Try fast deterministic classification first (< 1ms)
    fast_result = _try_fast_classify(classify_q, history_text, user_history_text, history=history)
    if fast_result is not None:
        result = fast_result
        badge = "Fast Path"
    else:
        catalog = get_catalog()
        family_ids = list(catalog.families.keys())
        try:
            with local_llm_slot():
                model = get_chat_model(temperature=0.0, reasoning_effort="minimal")
                structured_model = model.with_structured_output(ClassifyResult)
                result: ClassifyResult = structured_model.invoke([
                    ("system", build_classify_system_prompt(family_ids)),
                    ("human", f"Recent conversation:\n{history_text or '(none)'}\n\nCustomer message:\n{classify_q}"),
                ])
            badge = "Done"
        except Exception:
            logger.exception("Classify LLM call failed; using regex fallback classification.")
            result = _fallback_classify(classify_q)
            badge = "Fallback"

    # Deterministic safety net on top of the LLM call:
    # 0. Language Guard: If language switch, enforce target_lang; otherwise detect from question
    if is_lang_switch and target_lang:
        result.language = target_lang
    else:
        detected_lang = detect_language(question)
        if detected_lang in ("ar", "en"):
            result.language = detected_lang

    # 1. Scope Safeguard: If the question contains telecom keywords and no competitor names,
    # it must NEVER be marked as out of scope.
    q_lower = classify_q.lower()
    has_telecom_hint = any(h in q_lower for h in _TELECOM_SCOPE_HINTS) or any(h in history_text.lower() for h in _TELECOM_SCOPE_HINTS)
    has_competitor = _has_competitor_mention(question)
    if has_telecom_hint and not has_competitor:
        result.is_out_of_scope = False

    # 2. Greeting / Out-of-scope hygiene: Never attach old families or package raw to pure greetings/out of scope
    if result.intent in ("greeting", "out_of_scope"):
        result.family = None
        result.package_name_raw = None
        result.tier_price_egp = None
        result.budget_egp = None
    else:
        user_history_text = "\n".join(m.get("content", "") for m in history if m.get("role") in ("user", "human"))
        has_pronoun_or_relative = any(p in classify_q.lower() for p in _PRONOUN_TRIGGERS)
        q_has_explicit_budget = _detect_last_budget(classify_q) is not None

        # 3. Family recovery for telecom inquiries:
        if not result.family:
            if not q_has_explicit_budget or has_pronoun_or_relative:
                detected_family = _detect_family(classify_q) or _detect_family(user_history_text)
            else:
                detected_family = _detect_family(classify_q)
            if detected_family:
                result.family = detected_family

        # 4. Budget recovery for recommendation / same-budget follow-ups:
        #    Skip budget recovery if min_price_egp is set (upgrade/higher-tier mode
        #    intentionally has no budget cap).
        has_min_price = getattr(result, "min_price_egp", None) is not None
        has_same_budget_q = any(b in classify_q.lower() for b in _SAME_BUDGET_TRIGGERS)
        if has_same_budget_q and result.budget_egp is None and not has_min_price:
            result.budget_egp = _detect_last_budget(user_history_text)
            if result.intent not in ("activation_code", "comparison"):
                result.intent = "recommendation"
        elif result.budget_egp is None and result.intent not in _BUDGET_IRRELEVANT_INTENTS and not has_min_price:
            result.budget_egp = _detect_last_budget(classify_q) or _detect_last_budget(user_history_text)

        # 4b. Usage focus & device type recovery
        usage_focus = _detect_usage_focus(classify_q) or _detect_usage_focus(user_history_text)

        q_device_detected = _detect_device_type(classify_q)
        device_type = result.device_type or q_device_detected or _detect_device_type(user_history_text)
        if q_device_detected == "router" or any(k in classify_q.lower() for k in ("mifi", "راوتر", "ماي فاي", "مايفاي", "مودم", "usb")):
            device_type = "router"
            result.family = "dataline"
            usage_focus = "data"
            if result.intent not in ("activation_code", "comparison"):
                result.intent = "recommendation" if result.budget_egp is not None else (result.intent or "package_inquiry")
        elif not device_type:
            if usage_focus == "minutes":
                device_type = "phone"
            elif result.budget_egp is not None and result.intent == "recommendation":
                device_type = "phone"

        if device_type in ("router", "mifi", "modem", "usb"):
            device_type = "router"
            result.family = "dataline"
            usage_focus = "data"

        result.device_type = device_type
        result.usage_focus = usage_focus

        # Ensure family does not conflict with explicit usage focus
        if device_type == "router" or result.family == "dataline":
            result.family = "dataline"
        elif usage_focus == "minutes":
            if not result.family or result.family in ("hekaya_internet", "hekaya", "super_connect", "dataline"):
                result.family = "hekaya_mixat"
        elif usage_focus == "data":
            if not result.family or result.family in ("hekaya_mixat", "hekaya"):
                if device_type != "router":
                    result.family = "hekaya_internet"

        # Sanitize recommendation: recommendations should never carry an exact package or tier price
        if result.intent == "recommendation":
            result.package_name_raw = None
            result.tier_price_egp = None

    # Sanitize package_name_raw so language switch phrases or filler never get treated as packages
    if result.package_name_raw:
        pkg_clean = result.package_name_raw.strip().lower()
        if _detect_lang_switch(pkg_clean) or pkg_clean in ("in english", "in english pls", "english", "بالانجليزي", "بالعربي"):
            result.package_name_raw = None

    family_display = _family_display(result.family) if result.family else ""
    line_type = "postpaid" if result.family == "emerald" else ("prepaid" if result.family else "")

    trace_steps = [
        step(
            "intent", "2. Intent Classifier", "٢. تصنيف النية والتوجيه",
            description_en=f"Classified as '{result.intent}' (lang: {result.language}{', lang_switch' if is_lang_switch else ''}).",
            badge=badge, status="completed",
            details={"intent": result.intent, "language": result.language, "is_lang_switch": is_lang_switch},
            latency_ms=elapsed_ms(start),
        )
    ]
    if result.intent != "greeting":
        trace_steps.append(
            step(
                "understand", "3. Query Understanding", "٣. تحليل وتنميط الاستفسار",
                description_en="Extracted product family, package name, and budget entities.",
                badge=badge, status="completed",
                details={"category": result.family or "", "service": family_display},
                latency_ms=0,
            )
        )

    # 5. Extract and resolve entities across question & history
    raw_entities = list(getattr(result, "entities", []) or [])
    if result.package_name_raw and result.package_name_raw not in raw_entities:
        raw_entities.append(result.package_name_raw)

    if result.intent == "comparison":
        # Check history for package names if entities is missing the previous turn package
        if history_text:
            catalog = get_catalog()
            for tier in catalog.all_tiers():
                name_en = tier["name_en"]
                name_ar = tier.get("name_ar", "")
                if name_en.lower() in history_text.lower() or (name_ar and name_ar in history_text):
                    if name_en not in raw_entities:
                        raw_entities.insert(0, name_en)
                    break
        # Also check current question for package names
        catalog = get_catalog()
        for tier in catalog.all_tiers():
            name_en = tier["name_en"]
            name_ar = tier.get("name_ar", "")
            if name_en.lower() in classify_q.lower() or (name_ar and name_ar in classify_q):
                if name_en not in raw_entities:
                    raw_entities.append(name_en)

    entities = [
        e for e in (raw_entities or ([result.package_name_raw] if result.package_name_raw else []))
        if not _detect_lang_switch(e)
        and e.strip().lower() not in ("in english", "in english pls", "english", "بالانجليزي", "بالعربي")
    ]

    return {
        "language": result.language,
        "is_lang_switch": is_lang_switch,
        "lang_switch_user_q": lang_switch_user_q,
        "lang_switch_target_lang": target_lang if is_lang_switch else None,
        "intent": result.intent,
        "category": result.family or "",
        "service": family_display,
        "line_type": line_type,
        "budget_egp": result.budget_egp,
        "device_type": result.device_type,
        "usage_focus": getattr(result, "usage_focus", None),
        "min_price_egp": getattr(result, "min_price_egp", None),
        "package_name_raw": result.package_name_raw,
        "tier_price_egp": result.tier_price_egp,
        "keywords": result.keywords,
        "entities": entities,
        "is_out_of_scope": result.is_out_of_scope,
        "is_unsupported_service": result.is_out_of_scope,
        "workflow_trace": trace_steps,
    }
