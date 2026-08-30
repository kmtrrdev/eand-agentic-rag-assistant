"""
app/agent/edges.py
------------------
Conditional Routing Edge Functions for e& Egypt Agentic Telecom State Machine.
Implements explicit business decisions and independent retry budgets.
"""

from typing import Any, Dict
from app.config import settings


def route_after_input_guard(state: Dict[str, Any]) -> str:
    """Route blocked prompt injections to output_guard; allowed queries to understand."""
    guardrail_result = state.get("guardrail_result") or {}
    if not guardrail_result.get("allowed", True):
        return "output_guard"
    return "understand"


def route_after_understand(state: Dict[str, Any]) -> str:
    """Route to strategy_router unless understanding identified greeting, safe refusal or clarification."""
    intent = state.get("intent", "package_inquiry")
    is_out_of_scope = state.get("is_out_of_scope", False)
    is_unsupported = state.get("is_unsupported_service", False)
    needs_clarification = state.get("needs_clarification", False)

    if intent == "greeting":
        return "greeting"

    if is_out_of_scope or is_unsupported or intent in {"out_of_scope", "unsupported_service"}:
        return "safe_response"

    if needs_clarification or intent == "clarification":
        return "safe_response"

    return "strategy_router"


# Backwards compatibility alias
route_after_intent = route_after_understand


def route_after_strategy(state: Dict[str, Any]) -> str:
    """
    Routes based on the deterministic response strategy:
      - GREETING -> greeting
      - SAFE_REFUSAL / CLARIFICATION -> safe_response
      - MCP_EXACT / MCP_CALCULATION / MCP_ACTIVATION / MCP_RECOMMENDATION / MCP_COMPARISON -> mcp_tool
      - MCP_PLUS_RAG -> mcp_tool (will branch to retrieve afterwards)
      - RAG_ONLY -> retrieve
    """
    strategy = state.get("strategy", "RAG_ONLY")

    if strategy == "GREETING":
        return "greeting"

    if strategy in {"SAFE_REFUSAL", "CLARIFICATION"}:
        return "safe_response"

    if strategy.startswith("MCP_"):
        return "mcp_tool"

    return "retrieve"


def route_after_mcp_tool(state: Dict[str, Any]) -> str:
    """
    Decides whether MCP tool execution is sufficient or Hybrid RAG is needed:
      - If strategy requires supplemental RAG (MCP_PLUS_RAG) -> retrieve
      - If package was explicitly non-existent and needs clarification -> safe_response
      - Exact MCP strategies (MCP_EXACT, MCP_CALCULATION, MCP_ACTIVATION, MCP_RECOMMENDATION, MCP_COMPARISON) -> generate
      - Otherwise fallback to retrieve
    """
    strategy = state.get("strategy", "")
    needs_clarification = state.get("needs_clarification", False)

    if needs_clarification:
        return "safe_response"

    if strategy == "MCP_PLUS_RAG":
        return "retrieve"

    # Exact package facts, calculations, activation codes, comparisons, recommendations bypass RAG
    if strategy in {"MCP_EXACT", "MCP_CALCULATION", "MCP_ACTIVATION", "MCP_RECOMMENDATION", "MCP_COMPARISON"}:
        return "generate"

    return "retrieve"


def route_after_retrieval(state: Dict[str, Any]) -> str:
    """
    Conditional rewrite retry:
      - Allowed ONLY when retrieval is WEAK/FAILED
      - AND retrieval_attempts < MAX_RETRIEVAL_ATTEMPTS (2)
      - AND rewrite_attempts < MAX_REWRITE_ATTEMPTS (1)
    """
    status = state.get("retrieval_status", "RETRIEVAL_GOOD")
    retrieval_attempts = state.get("retrieval_attempts", 0)
    rewrite_attempts = state.get("rewrite_attempts", 0)

    max_retrieval_attempts = 2
    max_rewrite_attempts = 1

    if (
        status in {"RETRIEVAL_WEAK", "RETRIEVAL_FAILED"}
        and retrieval_attempts < max_retrieval_attempts
        and rewrite_attempts < max_rewrite_attempts
    ):
        return "rewrite"

    return "generate"


def route_after_validate(state: Dict[str, Any]) -> str:
    """
    Evaluates 3-outcome validation result:
      - PASS (or legacy SUPPORTED) -> output_guard
      - REPAIR -> generate (single targeted repair directly from MCP ground truth)
      - REFUSE (or legacy UNSUPPORTED) -> safe_response
    """
    val_result = state.get("validation_result", "PASS")
    generation_repairs = state.get("generation_repairs", 0)
    max_repairs = 1

    if val_result in {"PASS", "SUPPORTED"}:
        return "output_guard"

    if val_result == "REPAIR" and generation_repairs <= max_repairs:
        return "generate"

    return "safe_response"

