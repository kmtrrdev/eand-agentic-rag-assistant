from app.agent.lang import pick
from app.agent.state import AgentState
from app.agent.trace import elapsed_ms, now, step

SAFE_RESPONSE_AR = (
    "الموضوع ده مش من ضمن اللي أقدر أساعدك فيه — أنا متخصص في باقات وأسعار وأكواد "
    "تفعيل خدمات اتصالات مصر بس. لأي حاجة تانية زي الفواتير أو الدعم الفني، اتصل بـ 111 "
    "أو زور أقرب فرع اتصالات."
)
SAFE_RESPONSE_EN = (
    "That's outside what I can help with — I'm focused on e& Egypt packages, prices, and "
    "activation codes. For billing, technical support, or anything else, please call 111 "
    "or visit your nearest e& Egypt store."
)


def safe_response_node(state: AgentState) -> dict:
    start = now()
    language = state.get("language") or "en"
    answer = pick(language, SAFE_RESPONSE_AR, SAFE_RESPONSE_EN)
    return {
        "answer": answer,
        "confidence": 1.0,
        "workflow_trace": [step(
            "safe_response", "Safe Response", "المسار والرد الآمن",
            description_en="Out-of-scope request — routed to customer service instead of guessing.",
            badge="Redirected", status="completed",
            latency_ms=elapsed_ms(start),
        )],
    }
