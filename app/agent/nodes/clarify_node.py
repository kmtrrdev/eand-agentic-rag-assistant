"""Deterministic clarifying question for a genuinely ambiguous recommendation
request (a budget with no hint of phone/mobile vs. router/MiFi) — asking is
cheaper and more reliable than an LLM guessing which the customer meant."""
from typing import Any, Dict

from app.agent.lang import pick
from app.agent.state import AgentState
from app.agent.trace import elapsed_ms, now, step

CLARIFY_DEVICE_AR = (
    "قبل ما أرشحلك حاجة — عايز باقة لموبايلك (مكالمات/نت) ولا باقة إنترنت بس لراوتر/MiFi؟"
)
CLARIFY_DEVICE_EN = (
    "Before I recommend something — do you want a plan for your phone (calls/data), "
    "or a data-only package for a router/MiFi device?"
)


def clarify_node(state: AgentState) -> Dict[str, Any]:
    start = now()
    language = state.get("language") or "en"
    strategy = state.get("strategy")
    budget_egp = state.get("budget_egp")
    device_type = state.get("device_type")

    b_val = int(budget_egp) if (budget_egp and float(budget_egp).is_integer()) else budget_egp
    b_str_ar = f" في حدود {b_val} جنيه" if b_val else ""
    b_str_en = f" within your {b_val} EGP budget" if b_val else ""
    target_device_ar = " لموبايلك" if device_type == "phone" else ""
    target_device_en = " for your mobile" if device_type == "phone" else ""

    if strategy == "CLARIFY_USAGE":
        answer_ar = (
            f"علشان أرشحلك أفضل باقة تناسبك{target_device_ar}{b_str_ar} بالضبط: "
            f"استخدامك بيتركز أكتر على المكالمات والدقائق (مكسات)، ولا على الإنترنت والتصفح، ولا باقة متوازنة للاثنين مع بعض؟"
        )
        answer_en = (
            f"To recommend the best plan{target_device_en}{b_str_en}: "
            f"do you prioritize voice calls & minutes (Mix units), mobile internet & data, or a balanced mix of both?"
        )
        step_title_en = "Usage Clarification"
        step_title_ar = "توضيح نوع الاستخدام"
        desc_en = "Budget given without usage focus (calls vs. data vs. balanced) — asked customer to clarify priority."
    else:
        answer_ar = CLARIFY_DEVICE_AR
        answer_en = CLARIFY_DEVICE_EN
        step_title_en = "Device Clarification"
        step_title_ar = "توضيح نوع الجهاز"
        desc_en = "Budget given but device type (phone vs. router/MiFi) is ambiguous — asked instead of guessing."

    answer = pick(language, answer_ar, answer_en)
    return {
        "answer": answer,
        "confidence": 1.0,
        "needs_clarification": True,
        "workflow_trace": [step(
            "clarify", step_title_en, step_title_ar,
            description_en=desc_en,
            badge="Clarify", status="completed",
            latency_ms=elapsed_ms(start),
        )],
    }
