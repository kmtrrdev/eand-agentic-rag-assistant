from app.agent.lang import pick
from app.agent.state import AgentState
from app.agent.trace import elapsed_ms, now, step

GREETING_AR = (
    "أهلاً بيك في اتصالات مصر! أقدر أساعدك تعرف كل حاجة عن باقات وأسعار وأكواد "
    "تفعيل حكاية، أقوى كارت، داتا لاين، سوبر كونكت، وإمرالد. تحب تسأل عن إيه؟"
)
GREETING_EN = (
    "Welcome to e& Egypt! I can help you with packages, prices, and activation codes "
    "for Hekaya, Aqwa Card, DataLine, Super Connect, and Emerald. What would you like to know?"
)


def greeting_node(state: AgentState) -> dict:
    start = now()
    language = state.get("language") or "en"
    question = (state.get("question") or "").lower()

    # Contextual check: Did user ask how the assistant is doing, bot identity, or thank the assistant?
    is_how_are_you = any(k in question for k in (
        "how are you", "how r u", "how's it going", "hows it going", "how are you doing", "how do you do",
        "ازيك", "إزيك", "عامل ايه", "عامل إيه", "اخبارك", "أخبارك", "كيفك", "كيف حالك", "كويس", "تمام"
    ))
    is_identity = any(k in question for k in (
        "who are you", "what are you", "what can you do", "مين انت", "من انت", "انت مين", "إنت مين", "عرفني بنفسك"
    ))
    is_thanks = any(k in question for k in (
        "thank", "thx", "ty", "شكرا", "شكراً", "تسلم", "الله يخليك", "مشكور", "الف شكر", "ألف شكر"
    ))
    is_bye = any(k in question for k in (
        "bye", "goodbye", "see you", "مع السلامة", "سلام بقى", "مع سلامه"
    ))

    if is_how_are_you:
        ar_ans = (
            "أهلاً بيك! أنا بخير والحمد لله، وجاهز لمساعدتك في كل ما يخص باقات وخدمات اتصالات مصر "
            "(حكاية، أقوى كارت، سوبر كونكت، إمرالد، وداتا لاين). تحب تسأل عن إيه النهارده؟"
        )
        en_ans = (
            "Hello! I'm doing great, thank you for asking! I'm ready to help you with e& Egypt packages, "
            "prices, and activation codes (Hekaya, Aqwa Card, Super Connect, Emerald, DataLine). What would you like to know?"
        )
    elif is_identity:
        ar_ans = (
            "أنا المساعد الذكي لخدمة عملاء اتصالات مصر (e& Egypt). أقدر أساعدك في معرفة تفاصيل الباقات، "
            "حساب الأسعار شاملة الضريبة، أكواد التفعيل، وترشيح الباقة الأنسب لاحتياجك وميزانيتك. تحب تبدأ بإيه؟"
        )
        en_ans = (
            "I am the e& Egypt AI customer-service assistant. I can help you find package details, "
            "calculate after-tax recharge prices, get USSD activation codes, and recommend the best plan for you. How can I help you today?"
        )
    elif is_thanks:
        ar_ans = "العفو! تحت أمرك في أي وقت لو عندك أي استفسار عن باقات وخدمات اتصالات مصر."
        en_ans = "You're very welcome! Feel free to ask whenever you need help with e& Egypt packages or services."
    elif is_bye:
        ar_ans = "مع السلامة! يومك سعيد، وتحت أمرك في أي وقت."
        en_ans = "Goodbye! Have a great day, and feel free to return whenever you need assistance."
    else:
        ar_ans = GREETING_AR
        en_ans = GREETING_EN

    answer = pick(language, ar_ans, en_ans)
    return {
        "answer": answer,
        "confidence": 1.0,
        "workflow_trace": [step(
            "greeting", "3. Fast Greeting", "٣. رد ترحيبي فوري",
            description_en="Recognized greeting — answered instantly without retrieval.",
            badge="Done", status="completed",
            latency_ms=elapsed_ms(start),
        )],
    }
