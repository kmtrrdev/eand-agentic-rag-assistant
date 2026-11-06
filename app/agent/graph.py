"""
LangGraph wiring for the agentic pipeline:

    input_guard -> classify -> [greeting | safe_response | clarify | strategy_router]
    strategy_router -> [tools | query_rewrite] -> query_rewrite -> retrieve -> generate -> validate
    validate -> generate (one repair loop) | output_guard -> END

Tools and retrieval always run together (tools -> query_rewrite -> retrieve is
a plain, unconditional chain): deterministic facts stay the source of truth
for exact numbers, but retrieval still runs after them to pull in
supplementary context (e.g. Emerald's benefit/terms/roaming chunks, which
live only in the vector store) and to populate the sources shown to the
customer — a tool hit should enrich the answer, not silence retrieval
entirely.

query_rewrite sits between the two entry paths and retrieve so every
retrieval call — whether reached via tools or directly via RAG_ONLY — is
searched with the same rewritten, reference-resolved, bilingually-bridged
query rather than the raw customer message.

Node ids match the vocabulary the frontend's workflow visualization already
understands (see app/agent/trace.py) — greeting/safe_response/clarify
short-circuit straight to output_guard exactly like the diagram's "fast
path" branches.
"""
import functools

from langgraph.graph import END, START, StateGraph

from app.agent.edges import (
    route_after_classify,
    route_after_input_guard,
    route_after_strategy,
    route_after_validate,
)
from app.agent.nodes.classify_node import classify_node
from app.agent.nodes.clarify_node import clarify_node
from app.agent.nodes.generate_node import generate_node
from app.agent.nodes.greeting_node import greeting_node
from app.agent.nodes.input_guard_node import input_guard_node
from app.agent.nodes.output_guard_node import output_guard_node
from app.agent.nodes.query_rewrite_node import query_rewrite_node
from app.agent.nodes.retrieve_node import retrieve_node
from app.agent.nodes.safe_response_node import safe_response_node
from app.agent.nodes.strategy_router_node import strategy_router_node
from app.agent.nodes.tools_node import tools_node
from app.agent.nodes.validate_node import validate_node
from app.agent.state import AgentState


def build_graph():
    graph = StateGraph(AgentState)

    graph.add_node("input_guard", input_guard_node)
    graph.add_node("classify", classify_node)
    graph.add_node("greeting", greeting_node)
    graph.add_node("safe_response", safe_response_node)
    graph.add_node("clarify", clarify_node)
    graph.add_node("strategy_router", strategy_router_node)
    graph.add_node("tools", tools_node)
    graph.add_node("query_rewrite", query_rewrite_node)
    graph.add_node("retrieve", retrieve_node)
    graph.add_node("generate", generate_node)
    graph.add_node("validate", validate_node)
    graph.add_node("output_guard", output_guard_node)

    graph.add_edge(START, "input_guard")
    graph.add_conditional_edges("input_guard", route_after_input_guard, ["classify", "output_guard"])
    graph.add_conditional_edges(
        "classify", route_after_classify, ["greeting", "safe_response", "strategy_router"]
    )
    graph.add_conditional_edges("strategy_router", route_after_strategy, ["tools", "query_rewrite", "clarify"])
    graph.add_edge("tools", "query_rewrite")
    graph.add_edge("query_rewrite", "retrieve")
    graph.add_edge("retrieve", "generate")
    graph.add_edge("generate", "validate")
    graph.add_conditional_edges("validate", route_after_validate, ["generate", "output_guard"])

    graph.add_edge("greeting", "output_guard")
    graph.add_edge("safe_response", "output_guard")
    graph.add_edge("clarify", "output_guard")
    graph.add_edge("output_guard", END)

    return graph.compile()


import threading
from app.retrieval.reranker import warmup_reranker


@functools.lru_cache(maxsize=1)
def get_agent():
    # Warm up cross-encoder in background thread if not already warmed up
    threading.Thread(target=warmup_reranker, daemon=True).start()
    return build_graph()
