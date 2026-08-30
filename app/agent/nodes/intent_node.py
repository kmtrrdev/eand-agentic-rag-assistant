import logging
import re
from typing import Any, Dict, Optional
from pydantic import BaseModel, Field
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import JsonOutputParser

from app.llm.client import get_llm
from app.llm.prompts import INTENT_DETECTION_PROMPT
from app.guardrails.security_utils import is_arabic_text

logger = logging.getLogger("etisalat_kb.node.intent")

GREETING_PATTERNS = [
    # English greetings & wellbeing inquiries (hi, hello, how are you, how are u, etc.)
    r"^(?:hi|hello|hey|hola|welcome|good\s+morning|good\s+evening|good\s+afternoon|howdy|sup|what'?s\s+up|whats\s+up)(?:\s+there)?[\s!.,?]*$",
    r"^(?:how\s+(?:are\s+you|are\s+u|r\s+u|are\s+things|are\s+ya|is\s+it\s+going|is\s+everything|do\s+you\s+do|have\s+you\s+been))(?:\s+doing)?(?:\s+today)?[\s!.,?]*$",
    r"^(?:أهلاً|اهلا|أهلا|مرحبا|مرحباً|هاي|هلا|هلو|سلام|السلام\s+عليكم|سلام\s+عليكم|صباح\s+الخير|مساء\s+الخير)[\s!.,؟]*$",
    r"^(?:ازيك|إزيك|عامل\s+ايه|عاملين\s+ايه|ازي\s+الحال|ازاي\s+الحال|اخبارك|إخبارك|أخبارك|شخبارك|ازيك\s+يا\s+بوت|كيفك|كيف\s+الحال|كيف\s+حالك)[\s!.,؟]*$",
    r"^(?:شكرا|شكراً|تسلم|ألف\s+شكر|مشكور)[\s!.,؟]*$",
    r"^(?:السلام\s+عليكم\s+ورحمة\s+الله(?:\s+وبركاته)?)[\s!.,؟]*$",
    r"^(?:وعليكم\s+السلام(?:\s+ورحمة\s+الله(?:\s+وبركاته)?)?)[\s!.,؟]*$",
    r"^(?:صباح\s+(?:النور|الفل|الورد|الخير|الجمال)|صباحو)(?:\s+يا\s+(?:فندم|باشا|غالي|سيدي))?[\s!.,؟]*$",
    r"^(?:مساء\s+(?:النور|الفل|الورد|الخير|الفل\s+والياسمين))(?:\s+يا\s+(?:فندم|باشا|غالي|سيدي))?[\s!.,؟]*$",
    r"^(?:ازيك\s+عامل\s+ايه|اخبارك\s+ايه|ازاي\s+حضرتك|ازي\s+حضرتك|ازيك\s+يا\s+غالي)[\s!.,؟]*$",
    r"^(?:شكرا\s+جزيلا|شكراً\s+جزيلاً|تسلم\s+ايدك)[\s!.,؟]*$",
    r"^(?:thanks\s+a\s+lot|thank\s+you\s+so\s+much)[\s!.,?]*$",
    r"^(?:مع\s+السلامة|باي|goodbye|have\s+a\s+nice\s+day)[\s!.,?]*$",
    r"^(?:أهلاً\s+وسهلاً\s+بك|اهلا\s+وسهلا\s+بك)[\s!.,؟]*$",
]

THANKS_PATTERNS = [
    # Pure thanks only — NOT ok/okay (those are continuations)
    r"^(?:thanks|thank\s+you|thx|ty)[\s!.,?]*$",
    r"^(?:شكرا|شكراً|تسلم|ألف\s+شكر|مشكور|شكرا\s+جزيلا|شكراً\s+جزيلاً|تسلم\s+ايدك)[\s!.,؟]*$",
    r"^(?:thanks\s+a\s+lot|thank\s+you\s+so\s+much)[\s!.,?]*$",
]

OUT_OF_SCOPE_TERMS = [
    "messi", "ronaldo", "football", "world cup", "weather", "cooking", "recipe",
    "python code", "tic-tac-toe", "javascript", "game", "ميسي", "رونالدو", "كورة",
    "مباراة", "مكرونة", "بشاميل", "طبخ", "كود بايثون", "برمجة", "لعبة", "طقس", "عاصمة"
]

UNSUPPORTED_SERVICE_TERMS = [
    "corporate", "enterprise", "شركات", "خط شركة", "خطوط شركات", "نقل ملكية",
    "sim swap", "بدل فاقد", "بدل تالف", "استبدال شريحة", "تغيير شريحة",
    "نزاع فواتير", "dispute", "فاتورة الشركات", "تحويل من شركات"
]

# Words that continue/confirm the conversation — NEVER trigger greeting
EGYPTIAN_AFFIRMATIONS = [
    "ياريت", "يا ريت", "تمام كمل", "قولي التفاصيل", "وريني الباقات",
    "ماشي", "اه", "ايوا", "ايوه", "وريني",
]

# Short generic continuations that are ONLY safe to treat as affirmations when history exists
_GENERIC_CONTINUATIONS = {
    "ok", "okay", "sure", "fine", "go", "yep", "yup", "alright", "alright!",
    "continue", "yes", "yeah", "show me", "tell me", "تمام", "اوك", "أوك",
}


class IntentOutput(BaseModel):
    intent: str = Field(
        default="package_inquiry",
        description="One of: greeting, package_inquiry, comparison, out_of_scope, unsupported_service"
    )
    language: Optional[str] = Field(
        default="ar",
        description="'ar' or 'en'"
    )


def is_greeting(text: str) -> bool:
    if not text:
        return False
    # Strip emojis and punctuation for checking
    clean = re.sub(r"[\U00010000-\U0010ffff]|[🌀-🧿]|[🨀-🫿]|[👋🌹❤️✨👍🙏]", "", text).strip().lower()
    for pat in GREETING_PATTERNS:
        if re.search(pat, clean, re.IGNORECASE):
            return True
    return False


def is_pure_greeting(text: str) -> bool:
    if not text:
        return False
    clean = re.sub(r"[\U00010000-\U0010ffff]|[🌀-🧿]|[🨀-🫿]|[👋🌹❤️✨👍🙏]", "", text).strip().lower()
    for pat in GREETING_PATTERNS:
        if re.search(pat, clean, re.IGNORECASE):
            return True
    return False


def is_pure_thanks(text: str) -> bool:
    if not text:
        return False
    clean = text.strip().lower()
    for pat in THANKS_PATTERNS:
        if re.search(pat, clean, re.IGNORECASE):
            return True
    return False


def _detect_sub_track(text: str) -> Optional[str]:
    t = text.lower()
    if any(k in t for k in ["مكسات", "حكاية مكسات", "باقة مكسات", "باقات مكسات", "mixat"]):
        return "Mixat"
    if any(k in t for k in ["حكاية نت", "حكاية إنترنت", "حكاية انترنت", "باقة نت", "باقة انترنت", "نت فقط", "hekaya internet"]):
        return "Internet"
    return None


def _build_intent_step(intent: str, details: Dict[str, Any]) -> Dict[str, Any]:
    if intent == "greeting":
        badge = "👋 تحية وترحيب"
        desc_ar = "تم رصد تحية وترحيب وتوجيه الاستجابة للمسار السريع الفوري."
        desc_en = "Identified greeting, routed directly to fast canned greeting response."
    elif intent == "out_of_scope":
        badge = "⚠️ خارج النطاق"
        desc_ar = "تصنيف النية: استفسار خارج نطاق خدمات اتصالات مصر للأفراد."
        desc_en = "Intent: Out-of-scope query unrelated to consumer telecom."
    elif intent == "unsupported_service":
        badge = "🏢 خدمة إدارية / شركات"
        desc_ar = "تصنيف النية: خدمة إدارية أو شركات تتطلب التوجيه لخدمة العملاء."
        desc_en = "Intent: Unsupported corporate or branch administrative operation."
    elif intent == "comparison":
        badge = "⚖️ مقارنة أنظمة"
        desc_ar = "تصنيف النية: مقارنة بين باقات أو أنظمة اتصالات مصر."
        desc_en = "Intent: Comparative analysis between telecom packages."
    else:
        badge = f"🎯 {intent}"
        desc_ar = f"تصنيف النية: {intent} (استفسار عن باقات وخدمات الأفراد)."
        desc_en = f"Intent: {intent} (consumer package inquiry)."

    return {
        "node": "intent",
        "title_ar": "تصنيف النية السريع",
        "title_en": "Fast Intent Classification",
        "status": "completed",
        "badge": badge,
        "description_ar": desc_ar,
        "description_en": desc_en,
        "details": details,
    }


def intent_node(state: Dict[str, Any]) -> Dict[str, Any]:
    question = state.get("question", "").strip()
    history = state.get("history", [])
    q_lower = question.lower().strip().rstrip("!.,?")
    sub_track = _detect_sub_track(question)
    has_history = len(history) > 0

    # 1. Generic short continuations (ok, okay, sure, تمام…)
    #    — if the user already talked to the bot, these are NEVER greetings
    #    — they continue the conversation as package_inquiry
    if q_lower in _GENERIC_CONTINUATIONS:
        if has_history:
            step_info = _build_intent_step("package_inquiry", {"deterministic": True, "intent": "package_inquiry", "affirmation": True})
            return {
                "intent": "package_inquiry",
                "is_out_of_scope": False,
                "is_unsupported_service": False,
                "sub_track": sub_track,
                "workflow_trace": [step_info],
            }
        # First message, no history: treat as a soft greeting (show short welcome)
        step_info = _build_intent_step("greeting", {"deterministic": True, "intent": "greeting", "soft_open": True})
        return {
            "intent": "greeting",
            "is_out_of_scope": False,
            "is_unsupported_service": False,
            "sub_track": sub_track,
            "workflow_trace": [step_info],
        }

    # 2. Deterministic Greeting Fast-Path
    if is_greeting(question) or is_pure_thanks(question):
        step_info = _build_intent_step("greeting", {"deterministic": True, "intent": "greeting", "fast_greeting_flow": True})
        return {
            "intent": "greeting",
            "is_out_of_scope": False,
            "is_unsupported_service": False,
            "sub_track": sub_track,
            "workflow_trace": [step_info],
        }

    # 3. Egyptian Affirmations continuation
    if any(k in question for k in EGYPTIAN_AFFIRMATIONS):
        step_info = _build_intent_step("package_inquiry", {"deterministic": True, "intent": "package_inquiry", "affirmation": True})
        return {
            "intent": "package_inquiry",
            "is_out_of_scope": False,
            "is_unsupported_service": False,
            "sub_track": sub_track,
            "workflow_trace": [step_info],
        }

    # 3. Deterministic Out-of-Scope Fast-Path
    if any(term in q_lower for term in OUT_OF_SCOPE_TERMS):
        step_info = _build_intent_step("out_of_scope", {"deterministic": True, "intent": "out_of_scope"})
        return {
            "intent": "out_of_scope",
            "is_out_of_scope": True,
            "is_unsupported_service": False,
            "sub_track": sub_track,
            "workflow_trace": [step_info],
        }

    # 4. Deterministic Unsupported Service Fast-Path
    if any(term in q_lower for term in UNSUPPORTED_SERVICE_TERMS):
        step_info = _build_intent_step("unsupported_service", {"deterministic": True, "intent": "unsupported_service"})
        return {
            "intent": "unsupported_service",
            "is_out_of_scope": False,
            "is_unsupported_service": True,
            "sub_track": sub_track,
            "workflow_trace": [step_info],
        }

    # 5. Fast telecom inquiry / comparison / categories check
    telecom_inquiry_terms = [
        "باقات", "باقة", "أنظمة", "انظمة", "فئات", "categories", "plans", "packages",
        "أقوى", "اقوى", "aqwa", "كارت", "card", "حكاية", "hekaya", "مكسات", "mixat",
        "إمرالد", "امرالد", "emerald", "داتا", "dataline", "سوبر كونكت", "super connect",
        "أهلاً", "اهلا", "ahlan", "منيو الجنيه", "كود", "code", "ussd", "تفعيل", "اشتراك",
        "مقارنة", "قارن", "compare", "vs", "سعر", "أسعار", "اسعار", "price", "cost",
        "options", "prepaid", "offer", "عرض", "عروض", "family lines", "خطوط عائلة", "خط عيلة",
        "add-on", "add-ons", "إضافية", "اضافية", "redeem", "تجديد", "شحن", "source", "double"
    ]
    if any(k in q_lower for k in telecom_inquiry_terms) or sub_track:
        inquiry_intent = "comparison" if any(k in q_lower for k in ["قارن", "مقارنة", "compare", "vs"]) else "package_inquiry"
        step_info = _build_intent_step(inquiry_intent, {"deterministic": True, "intent": inquiry_intent, "sub_track": sub_track})
        return {
            "intent": inquiry_intent,
            "is_out_of_scope": False,
            "is_unsupported_service": False,
            "sub_track": sub_track,
            "workflow_trace": [step_info],
        }

    try:
        llm = get_llm(timeout=12.0, max_tokens=60).with_structured_output(IntentOutput)
        prompt = ChatPromptTemplate.from_messages([
            ("system", INTENT_DETECTION_PROMPT),
            ("human", "Classify this query:\n{question}")
        ])
        chain = prompt | llm
        result = chain.invoke({"question": question})
        intent = getattr(result, "intent", "package_inquiry") or "package_inquiry"

        is_out = (intent == "out_of_scope")
        is_unsupported = (intent == "unsupported_service")

        step_info = _build_intent_step(intent, {"deterministic": False, "intent": intent})
        return {
            "intent": intent,
            "is_out_of_scope": is_out,
            "is_unsupported_service": is_unsupported,
            "sub_track": sub_track,
            "workflow_trace": [step_info],
        }

    except Exception as exc:
        logger.warning("Structured intent classification failed, trying JSON fallback: %s", exc)
        try:
            parser = JsonOutputParser(pydantic_object=IntentOutput)
            prompt = ChatPromptTemplate.from_messages([
                ("system", INTENT_DETECTION_PROMPT + "\n\nRespond ONLY with JSON matching:\n{format_instructions}"),
                ("human", "{question}")
            ])
            response = (prompt | get_llm(timeout=12.0, max_tokens=60)).invoke({
                "question": question,
                "format_instructions": parser.get_format_instructions()
            })
            res_dict = parser.parse(response.content or "")
            intent = res_dict.get("intent", "package_inquiry")
            is_out = (intent == "out_of_scope")
            is_unsupported = (intent == "unsupported_service")

            step_info = _build_intent_step(intent, {"deterministic": False, "intent": intent})
            return {
                "intent": intent,
                "is_out_of_scope": is_out,
                "is_unsupported_service": is_unsupported,
                "sub_track": sub_track,
                "workflow_trace": [step_info],
            }
        except Exception as exc2:
            logger.error("JSON fallback intent classification also failed: %s", exc2)

    step_info = _build_intent_step(
        "package_inquiry",
        {"deterministic": True, "fallback": True, "reason": "llm_and_json_fallback_failed"},
    )
    return {
        "intent": "package_inquiry",
        "is_out_of_scope": False,
        "is_unsupported_service": False,
        "sub_track": sub_track,
        "workflow_trace": [step_info],
    }
