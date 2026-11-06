from typing import Any, Dict

from app.agent.state import AgentState
from app.agent.trace import elapsed_ms, now, step
from app.guardrails import sanitize_output


def output_guard_node(state: AgentState) -> Dict[str, Any]:
    start = now()
    cleaned = sanitize_output(state.get("answer", ""))
    return {
        "answer": cleaned,
        "workflow_trace": [step(
            "output_guard", "10. Output Guardrail", "١٠. حارس المخرجات والتنقيح",
            description_en="Sanitized the final response before sending it to the customer.",
            badge="Done", status="completed",
            latency_ms=elapsed_ms(start),
        )],
    }
