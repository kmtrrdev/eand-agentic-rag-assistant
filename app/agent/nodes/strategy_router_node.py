from typing import Any, Dict

from app.agent.state import AgentState
from app.agent.trace import elapsed_ms, now, step
from app.config import settings


def strategy_router_node(state: AgentState) -> Dict[str, Any]:
    """Deterministic routing from classified intent to an answer strategy —
    no LLM call, so this is essentially free.

    A named family + a budget (possibly carried over from earlier in the
    conversation, e.g. "I have 200 EGP" ... "I need it in Emerald") is checked
    *before* intent-specific routing, regardless of which intent bucket the
    classifier guessed — "does this fit their budget?" is more useful than a
    generic activation/family answer that ignores a budget they already gave.
    """
    start = now()
    category = state.get("category")

    if settings.RAG_ONLY_MODE or not getattr(settings, "MCP_TOOLS_ENABLED", True):
        strategy = "RAG_ONLY"
        return {
            "strategy": strategy,
            "workflow_trace": [step(
                "strategy_router", "4. Strategy Router", "٤. موجه استراتيجية الرد",
                description_en=f"Routed to strategy '{strategy}' (RAG Only Mode).",
                badge=strategy, status="completed",
                details={"category": category or ""},
                latency_ms=elapsed_ms(start),
            )],
        }
    intent = state.get("intent", "")
    package_name_raw = state.get("package_name_raw")
    category = state.get("category")
    budget_egp = state.get("budget_egp")
    device_type = state.get("device_type")

    # A real tier reference always has a number in it ("Aqwa Card 19",
    # "Emerald 430"); a bare family name ("emerald") does not. Don't trust
    # the classifier's package_name_raw as "one specific tier was named" on
    # word alone — it occasionally fills this with just the family name.
    names_specific_tier = bool(package_name_raw) and any(ch.isdigit() for ch in package_name_raw)

    if intent == "price_calculation":
        strategy = "TOOL_CALCULATION"
    elif intent == "activation_code":
        strategy = "TOOL_ACTIVATION"
    elif intent == "comparison":
        strategy = "TOOL_PLUS_RAG"
    elif intent == "recommendation" or budget_egp is not None:
        if state.get("usage_focus") == "data" and not category and not device_type:
            strategy = "CLARIFY_DEVICE"
        elif not category and not state.get("usage_focus") and budget_egp is not None and float(budget_egp) < 400:
            strategy = "CLARIFY_USAGE"
        else:
            strategy = "TOOL_RECOMMENDATION"
    elif names_specific_tier:
        strategy = "TOOL_EXACT"
    elif category:
        strategy = "TOOL_PLUS_RAG"
    else:
        strategy = "RAG_ONLY"

    return {
        "strategy": strategy,
        "workflow_trace": [step(
            "strategy_router", "4. Strategy Router", "٤. موجه استراتيجية الرد",
            description_en=f"Routed to strategy '{strategy}'.",
            badge=strategy, status="completed",
            details={"category": category or ""},
            latency_ms=elapsed_ms(start),
        )],
    }
