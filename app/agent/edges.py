from app.agent.state import AgentState


def route_after_input_guard(state: AgentState) -> str:
    return "output_guard" if state.get("blocked") else "classify"


def route_after_classify(state: AgentState) -> str:
    if state.get("intent") == "greeting":
        return "greeting"
    if state.get("is_out_of_scope"):
        return "safe_response"
    return "strategy_router"


def route_after_strategy(state: AgentState) -> str:
    strategy = state.get("strategy")
    if strategy in ("CLARIFY_DEVICE", "CLARIFY_USAGE"):
        return "clarify"
    return "query_rewrite" if strategy == "RAG_ONLY" else "tools"


def route_after_validate(state: AgentState) -> str:
    return "generate" if state.get("validation_result") == "REPAIR" else "output_guard"
