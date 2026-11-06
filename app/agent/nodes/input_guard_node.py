from app.agent.lang import detect_language
from app.agent.state import AgentState
from app.agent.trace import elapsed_ms, now, step
from app.guardrails import check_input


def input_guard_node(state: AgentState) -> dict:
    start = now()
    question = state.get("question", "")
    result = check_input(question, history=state.get("history"))

    if result["blocked"]:
        language = detect_language(question)
        answer = result["refusal_ar"] if language in ("ar", "mixed") else result["refusal_en"]
        return {
            "blocked": True,
            "block_reason": result["reason"],
            "language": language,
            "answer": answer,
            "workflow_trace": [step(
                "input_guard", "1. Input Guardrail", "١. حارس المدخلات والأمان",
                description_en=f"Blocked: {result['reason']}",
                badge="Blocked", status="blocked",
                details={"reason": result["reason"]},
                latency_ms=elapsed_ms(start),
            )],
        }

    return {
        "blocked": False,
        "block_reason": None,
        "workflow_trace": [step(
            "input_guard", "1. Input Guardrail", "١. حارس المدخلات والأمان",
            description_en="No injection or secret-probing patterns detected.",
            badge="Passed", status="completed",
            latency_ms=elapsed_ms(start),
        )],
    }
