"""
greeting_node.py
----------------
Fast Greeting Node — generates dynamic, warm, natural greetings and pleasantries
using a dedicated lightweight LLM call, with instant deterministic fallback.
"""

import logging
import re
from typing import Any, Dict, List
from langchain_core.prompts import ChatPromptTemplate
from app.guardrails.security_utils import is_arabic_text
from app.guardrails.output_guard import sanitize_output
from app.llm.client import get_llm
from app.llm.prompts import GREETING_LLM_PROMPT

logger = logging.getLogger("etisalat_kb.node.greeting")


def _has_prior_greeting(history: List[Dict[str, Any]]) -> bool:
    """Returns True if the bot has already introduced itself in this session."""
    for msg in history:
        if msg.get("role") == "assistant":
            content = msg.get("content", "")
            if any(k in content for k in [
                "اتصالات مصر", "e& Egypt", "Hekaya", "حكاية", "Emerald",
                "telecom assistant", "المساعد الذكي"
            ]):
                return True
    return False


def _build_greeting_history(history: List[Dict[str, Any]]) -> str:
    """Builds a concise history string for the greeting prompt."""
    if not history:
        return "No previous conversation (initial turn)."
    recent = history[-4:]
    lines = []
    for msg in recent:
        role = "Assistant" if msg.get("role") == "assistant" else "Customer"
        content = (msg.get("content") or "").strip()
        if content:
            lines.append(f"[{role}]: {content}")
    return "\n".join(lines) if lines else "No previous conversation (initial turn)."



def _classify_greeting_type(question: str):
    """
    Classify the greeting type for deterministic fallback responses.
    All boolean flags are computed here so they are ALWAYS defined before use.
    This fixes the NameError crash that occurred when the LLM call failed and
    the code fell through to the conditional block at the bottom of greeting_node.

    Returns:
        tuple: (is_closing, is_thanks, is_wellbeing, is_islamic, is_morning, is_evening)
    """
    q_lower = question.lower().strip()

    is_closing = any(k in q_lower for k in [
        "\u0645\u0639 \u0627\u0644\u0633\u0644\u0627\u0645\u0629",  # with peace
        "\u0628\u0627\u064a",  # bye (ar)
        "goodbye", "bye", "see you", "take care", "have a nice day",
        "\u0648\u062f\u0627\u0639\u0627",  # farewell (ar)
        "\u0625\u0644\u0649 \u0627\u0644\u0644\u0642\u0627\u0621",  # until we meet (ar)
    ])

    is_thanks = any(k in q_lower for k in [
        "\u0634\u0643\u0631\u0627",  # shukran
        "\u0634\u0643\u0631\u064b\u0627",  # shukran with tanwin
        "\u062a\u0633\u0644\u0645",  # tislam
        "\u0645\u0634\u0643\u0648\u0631",  # mashkoor
        "\u0634\u0643\u0631\u0627 \u062c\u0632\u064a\u0644\u0627",  # full thanks
        "thanks", "thank you", "thx", "ty", "thanks a lot", "thank you so much",
    ])

    is_wellbeing = any(k in q_lower for k in [
        "\u0627\u0632\u064a\u0643",  # izayak
        "\u0639\u0627\u0645\u0644 \u0627\u064a\u0647",  # aamel eh
        "\u0643\u064a\u0641\u0643",  # kayfak
        "\u0643\u064a\u0641 \u062d\u0627\u0644\u0643",  # kayf halak
        "\u0634\u062e\u0628\u0627\u0631\u0643",  # shakhbarak
        "how are you", "how are u", "how r u", "how are things",
        "how is it going", "how have you been", "how do you do",
    ])

    is_islamic = any(k in q_lower for k in [
        "\u0627\u0644\u0633\u0644\u0627\u0645 \u0639\u0644\u064a\u0643\u0645",
        "\u0633\u0644\u0627\u0645 \u0639\u0644\u064a\u0643\u0645",
        "\u0648\u0639\u0644\u064a\u0643\u0645 \u0627\u0644\u0633\u0644\u0627\u0645",
        "assalamu", "as-salamu", "peace be upon",
    ])

    is_morning = any(k in q_lower for k in [
        "\u0635\u0628\u0627\u062d \u0627\u0644\u062e\u064a\u0631",
        "\u0635\u0628\u0627\u062d \u0627\u0644\u0646\u0648\u0631",
        "\u0635\u0628\u0627\u062d \u0627\u0644\u0641\u0644",
        "\u0635\u0628\u0627\u062d\u0648",
        "good morning",
    ])

    is_evening = any(k in q_lower for k in [
        "\u0645\u0633\u0627\u0621 \u0627\u0644\u062e\u064a\u0631",
        "\u0645\u0633\u0627\u0621 \u0627\u0644\u0646\u0648\u0631",
        "\u0645\u0633\u0627\u0621 \u0627\u0644\u0641\u0644",
        "good evening", "good afternoon",
    ])

    return is_closing, is_thanks, is_wellbeing, is_islamic, is_morning, is_evening


def greeting_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    Fast Greeting Node with dedicated dynamic LLM generation.
    """
    question = state.get("question", "").strip()
    history = state.get("history", [])
    is_ar = is_arabic_text(question)
    q_lower = question.lower()
    already_greeted = _has_prior_greeting(history)

    # ── 1. Try Dynamic LLM Generation for fresh, natural responses ───────────
    try:
        prompt = ChatPromptTemplate.from_messages([
            ("system", GREETING_LLM_PROMPT),
            ("human", "Conversation History:\n{history_context}\n\nCustomer Message: {question}")
        ])
        history_context = _build_greeting_history(history)
        # temperature=0.3, not the global default 0.0: GREETING_LLM_PROMPT explicitly
        # asks for "varied, fresh" phrasing, which is structurally unachievable at
        # temperature 0 (near-identical output every call). Greetings carry no
        # grounding/hallucination risk (validate_answer's Level 0 auto-support skips
        # claim-checking on them entirely), so a small amount of sampling temperature
        # here has no correctness cost — unlike generate_answer_node, which stays at 0.
        llm = get_llm(timeout=4.0, max_tokens=150, temperature=0.3)
        chain = prompt | llm
        res = chain.invoke({
            "history_context": history_context,
            "question": question
        })
        raw_ans = (res.content or "").strip()
        if "<think>" in raw_ans:
            raw_ans = re.sub(r"<think>.*?</think>", "", raw_ans, flags=re.DOTALL).strip()
        cleaned_ans = sanitize_output(raw_ans)

        if cleaned_ans:
            step_info = {
                "node": "greeting",
                "title_en": "Dynamic Greeting Response",
                "status": "completed",
                "badge": "👋 Dynamic Greeting",
                "description_en": "Generated dynamic, natural greeting response via dedicated LLM.",
                "details": {
                    "is_arabic": is_ar,
                    "returning_user": already_greeted,
                    "dynamic_llm": True,
                },
            }
            return {
                "answer": cleaned_ans,
                "confidence": 1.0,
                "sources": [],
                "documents": [],
                "context": "",
                "workflow_trace": [step_info],
            }
    except Exception as exc:
        logger.warning("Dynamic greeting LLM call failed, falling back to deterministic greeting: %s", exc)
        # Fall back seamlessly to deterministic responses

    # ── OLD-2. Fallback to Deterministic Responses ──
    # ── 2. Compute greeting type flags (defined here, before use) ─────────────
    #    Previously these were undefined, causing NameError when LLM failed.
    is_closing, is_thanks, is_wellbeing, is_islamic, is_morning, is_evening = \
        _classify_greeting_type(question)

    # ── 3. Select deterministic response based on greeting type ───────────────
    if is_closing:
        answer = (
            "مع ألف سلامة! أتمنى لك يوماً سعيداً. 🟢\n"
            "لو احتجت أي مساعدة في باقات اتصالات مصر، أنا هنا دايماً!"
        ) if is_ar else (
            "Goodbye and have a wonderful day! 🟢\n"
            "Whenever you need help with e& Egypt packages, I am here!"
        )

    elif is_thanks:
        answer = (
            "العفو! يسعدني مساعدتك دائماً. 😊\n"
            "في أي استفسار ثاني عن باقات اتصالات مصر؟"
        ) if is_ar else (
            "You're most welcome! Always happy to help. 😊\n"
            "Any other questions about e& Egypt packages?"
        )

    elif already_greeted:
        # ── Returning turn: short, conversational, asks what they need ──
        if is_wellbeing:
            answer = (
                "تمام شكراً! 🟢 عايز تعرف إيه النهارده؟\n"
                "قولي ميزانيتك أو نوع الاستخدام (نت / مكالمات) وأرشحلك الأنسب!"
            ) if is_ar else (
                "I'm great, thank you! 🟢 What can I help you with today?\n"
                "Share your budget or usage preference and I'll find the best plan!"
            )
        elif is_islamic:
            answer = (
                "وعليكم السلام! 🟢 كيف أقدر أساعدك في باقات اتصالات مصر؟"
            ) if is_ar else (
                "Peace be upon you! 🟢 How can I assist you with e& Egypt packages today?"
            )
        elif is_morning:
            answer = (
                "صباح النور! ☀️ إيه اللي تحب تعرفه النهارده عن باقات اتصالات مصر؟"
            ) if is_ar else (
                "Good morning! ☀️ What would you like to know about e& Egypt packages today?"
            )
        elif is_evening:
            answer = (
                "مساء الخير! 🌙 إيه اللي أقدر أساعدك فيه دلوقتي؟"
            ) if is_ar else (
                "Good evening! 🌙 What can I help you with right now?"
            )
        else:
            # Generic follow-up — short and helpful
            answer = (
                "هلا! 🟢 إيه اللي تحب تعرفه؟\n"
                "قولي ميزانيتك أو نوع استخدامك وأجيبلك الباقة الأنسب فوراً!"
            ) if is_ar else (
                "Hey! 🟢 What would you like to know?\n"
                "Tell me your budget or usage type and I'll find the perfect plan for you!"
            )

    else:
        # ── First turn: full welcome ──────────────────────────────────────
        if is_wellbeing:
            answer = (
                "الحمد لله بخير، شكراً لسؤالك! 🟢\n"
                "أنا المساعد الذكي لاتصالات مصر (e& Egypt)، جاهز أساعدك تختار أحسن باقة.\n"
                "قولي ميزانيتك أو استخدامك المفضل وأرشحلك فوراً!"
            ) if is_ar else (
                "I'm doing great, thank you for asking! 🟢\n"
                "I'm the e& Egypt smart telecom assistant. Tell me your budget or usage preference and I'll find the best plan for you!"
            )
        elif is_islamic:
            answer = (
                "وعليكم السلام ورحمة الله وبركاته! 🟢\n"
                "أهلاً بك في اتصالات مصر. أنا المساعد الذكي لمساعدتك في اختيار أنسب باقات المكالمات والإنترنت.\n"
                "كيف يمكنني خدمتك اليوم؟"
            ) if is_ar else (
                "Peace be upon you! Welcome to e& Egypt. 🟢\n"
                "I'm your smart telecom assistant — here to help you find the best mobile and internet plans.\n"
                "How may I assist you today?"
            )
        elif is_morning:
            answer = (
                "صباح النور! ☀️ أهلاً بك في اتصالات مصر.\n"
                "أنا هنا أساعدك تختار أحسن باقة حكاية أو إمرالد أو كارت شحن.\n"
                "إيه اللي تحب تبدأ بيه؟"
            ) if is_ar else (
                "Good morning! ☀️ Welcome to e& Egypt.\n"
                "I'm here to help you explore Hekaya, Emerald, Prepaid, and more.\n"
                "How may I assist you today?"
            )
        elif is_evening:
            answer = (
                "مساء النور! 🌙 أهلاً بك في اتصالات مصر.\n"
                "أنا المساعد الذكي — جاهز أساعدك تختار الباقة المناسبة ليك.\n"
                "إيه اللي تحب تعرفه؟"
            ) if is_ar else (
                "Good evening! 🌙 Welcome to e& Egypt.\n"
                "I'm your smart assistant — ready to help you find the best plan.\n"
                "How may I assist you this evening?"
            )
        else:
            # Default full welcome
            if is_ar:
                answer = (
                    "أهلاً وسهلاً في اتصالات مصر (e& Egypt)! 🟢\n"
                    "أنا المساعد الذكي وهساعدك تختار أنسب باقة:\n"
                    "• 📱 **حكاية مكسات وإنترنت:** باقات شهرية شاملة (مكالمات + نت).\n"
                    "• 💳 **أنظمة الكارت وأقوى كارت:** مرونة شحن بأعلى قيمة.\n"
                    "• ⭐ **إمرالد (Emerald):** باقات فاتورة مميزة مع دقائق دولية وتجوال.\n"
                    "• 📶 **سوبر كونكت وداتا لاين:** باقات نت إضافية وراوتر.\n\n"
                    "قولي ميزانيتك أو استخدامك (نت / مكالمات) وأرشحلك الأنسب فوراً!"
                )
            else:
                answer = (
                    "Welcome to e& Egypt! 🟢\n"
                    "I'm your smart telecom assistant — here to help you find the perfect plan:\n"
                    "• 📱 **Hekaya (Mixat & Internet):** Monthly all-in-one calling and data plans.\n"
                    "• 💳 **Prepaid & Aqwa Card:** Flexible recharges with great value.\n"
                    "• ⭐ **Emerald Postpaid:** Premium monthly plans with international & roaming perks.\n"
                    "• 📶 **Super Connect & Data Line:** Add-on data and MiFi/router packages.\n\n"
                    "Share your monthly budget or preferred usage and I'll find the best match!"
                )

    step_info = {
        "node": "greeting",
        "title_en": "Fast Greeting Response",
        "status": "completed",
        "badge": "👋 Instant Greeting",
        "description_en": "Responded instantly to greeting without vector database lookup.",
        "details": {
            "is_arabic": is_ar,
            "returning_user": already_greeted,
            "fast_path": True,
        },
    }

    return {
        "answer": answer,
        "confidence": 1.0,
        "sources": [],
        "documents": [],
        "context": "",
        "workflow_trace": [step_info],
    }

