from langgraph.graph import END, START, StateGraph

from app.agent.state import AgentState
from app.agent.instrumentation import instrument_node
from app.agent.edges import (
    route_after_input_guard,
    route_after_intent,
    route_after_understand,
    route_after_strategy,
    route_after_mcp_tool,
    route_after_retrieval,
    route_after_validate,
)
# NOTE: route_after_retrieval decides WEAK/FAILED retrieval -> rewrite vs GOOD -> generate.
# It MUST be wired as a conditional edge after "evaluate" (see below). Previously this
# import was unused and "retrieve" pointed straight at "generate", which silently
# disabled the entire retrieval-quality check and query-rewrite retry loop.
from app.agent.nodes.input_guard_node import input_guard_node
from app.agent.nodes.intent_node import intent_node
from app.agent.nodes.greeting_node import greeting_node
from app.agent.nodes.understand_query import understand_query_node
from app.agent.nodes.strategy_router import strategy_router_node
from app.agent.nodes.safe_response_node import safe_response_node
from app.agent.nodes.mcp_tool_node import mcp_tool_node
from app.agent.nodes.retrieve import retrieve_node
from app.agent.nodes.evaluate_retrieval import evaluate_retrieval_node
from app.agent.nodes.rewrite_query import rewrite_query_node
from app.agent.nodes.generate_answer import generate_answer_node
from app.agent.nodes.output_guard_node import output_guard_node
from app.agent.nodes.validate_answer import validate_answer_node

_cached_agent = None


def build_graph():
    """
    Build and compile the e& Egypt Production State Machine:
    1. Input Guard (Prompt injection defense)
    2. Intent Classification (Fast greeting & scope routing)
    3. Query Understanding (Entity, constraint & budget extraction)
    4. Response Strategy Router (MCP_EXACT, MCP_CALCULATION, MCP_ACTIVATION, MCP_RECOMMENDATION, MCP_COMPARISON, RAG_ONLY)
    5. MCP Tool Dispatch (Deterministic Ground Truth)
    6. Parallel Hybrid Retrieval (Only when RAG is required)
    7. Retrieval Evaluation (Objective multi-dimensional relevance check)
    8. Targeted Query Rewriting (Contextual self-correction with progress detection)
    9. Answer Generation (Grounded generation & targeted repair mode)
    10. Output Guard & Sanitization (Pre-validation secret & tag scrubber)
    11. 3-Tier Fact Validation (PASS / REPAIR / REFUSE)
    12. Fast Greeting & Safe Response (Instant exits without RAG/eval loops)
    """
    graph = StateGraph(AgentState)

    # 1. Register all instrumented nodes
    graph.add_node("input_guard", instrument_node("input_guard")(input_guard_node))
    graph.add_node("intent", instrument_node("intent")(intent_node))
    graph.add_node("greeting", instrument_node("greeting")(greeting_node))
    graph.add_node("understand", instrument_node("understand")(understand_query_node))
    graph.add_node("strategy_router", instrument_node("strategy_router")(strategy_router_node))
    graph.add_node("mcp_tool", instrument_node("mcp_tool")(mcp_tool_node))
    graph.add_node("safe_response", instrument_node("safe_response")(safe_response_node))
    graph.add_node("retrieve", instrument_node("retrieve")(retrieve_node))
    graph.add_node("evaluate", instrument_node("evaluate")(evaluate_retrieval_node))
    graph.add_node("rewrite", instrument_node("rewrite")(rewrite_query_node))
    graph.add_node("generate", instrument_node("generate")(generate_answer_node))
    graph.add_node("output_guard", instrument_node("output_guard")(output_guard_node))
    graph.add_node("validate", instrument_node("validate")(validate_answer_node))

    # 2. Add edges & conditional transitions
    graph.add_edge(START, "input_guard")

    graph.add_conditional_edges(
        "input_guard",
        route_after_input_guard,
        {
            "output_guard": "output_guard",
            "understand": "understand",
        },
    )

    graph.add_conditional_edges(
        "understand",
        route_after_understand,
        {
            "greeting": "greeting",
            "safe_response": "safe_response",
            "strategy_router": "strategy_router",
        },
    )

    graph.add_edge("greeting", "output_guard")
    graph.add_edge("safe_response", "output_guard")

    graph.add_conditional_edges(
        "strategy_router",
        route_after_strategy,
        {
            "greeting": "greeting",
            "safe_response": "safe_response",
            "mcp_tool": "mcp_tool",
            "retrieve": "retrieve",
        },
    )

    graph.add_conditional_edges(
        "mcp_tool",
        route_after_mcp_tool,
        {
            "retrieve": "retrieve",
            "safe_response": "safe_response",
            "generate": "generate",
        },
    )

    # Retrieval -> Evaluation -> (rewrite & retry | generate)
    # This wiring was previously missing: "retrieve" pointed directly at "generate",
    # so evaluate_retrieval_node/rewrite_query_node were registered but unreachable and
    # weak/failed retrievals were silently sent straight to generation instead of being
    # retried with a rewritten query.
    graph.add_edge("retrieve", "evaluate")

    graph.add_conditional_edges(
        "evaluate",
        route_after_retrieval,
        {
            "rewrite": "rewrite",
            "generate": "generate",
        },
    )

    graph.add_edge("rewrite", "retrieve")

    # Correct Pipeline Ordering: Generation -> Validation -> Output Guard (Sanitization) -> END
    graph.add_edge("generate", "validate")

    graph.add_conditional_edges(
        "validate",
        route_after_validate,
        {
            "output_guard": "output_guard",
            "generate": "generate",
            "safe_response": "safe_response",
        },
    )

    graph.add_edge("output_guard", END)

    return graph.compile()


def get_agent():
    """Get or build the cached singleton compiled LangGraph agent."""
    global _cached_agent
    if _cached_agent is None:
        _cached_agent = build_graph()
    return _cached_agent

