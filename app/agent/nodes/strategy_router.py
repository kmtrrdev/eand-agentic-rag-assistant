"""
app/agent/nodes/strategy_router.py
----------------------------------
Response Strategy Router Node for e& Egypt Agentic Telecom State Machine.

Deterministically routes the request to the optimal execution path:
  - GREETING: Fast greeting exit
  - SAFE_REFUSAL: Out-of-scope / unsupported service refusal
  - CLARIFICATION: Ambiguous query or non-existent package clarification
  - MCP_EXACT: Exact package details from structured MCP truth (short-circuits RAG)
  - MCP_CALCULATION: Price & tax calculations from MCP calculator
  - MCP_ACTIVATION: USSD activation code lookup
  - MCP_RECOMMENDATION: Structured package recommendation respecting budget semantics
  - MCP_COMPARISON: Symmetrical structured comparison for dual-package inquiries
  - MCP_PLUS_RAG: Structured MCP facts supplemented with official KB context
  - RAG_ONLY: General open-ended KB questions where no single structured entity exists
"""

import logging
import re
from typing import Any, Dict, List

from app.config import settings

logger = logging.getLogger("etisalat_kb.node.strategy_router")


def strategy_router_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    Evaluates intent, entities, keywords, budget, and clarification flags
    to establish the execution strategy and prevent unnecessary RAG/eval loops.
    """
    question = state.get("question", "")
    q_lower = question.lower()
    intent = state.get("intent", "package_inquiry")
    entities = state.get("entities", [])
    keywords = state.get("keywords", [])
    budget_egp = state.get("budget_egp")
    service = state.get("service", "general")
    sub_track = state.get("sub_track")
    is_out_of_scope = state.get("is_out_of_scope", False)
    is_unsupported = state.get("is_unsupported_service", False)
    needs_clarification = state.get("needs_clarification", False)

    # ── 1. Fast Safe Exits ───────────────────────────────────────────────────
    # NOTE: `intent` here is only ever "greeting", "out_of_scope", "unsupported_service",
    # or the default "package_inquiry" — understand_query_node's LLM/deterministic
    # extraction has no schema field for a richer taxonomy (comparison/activation_code/
    # recommendation/clarification), so checks like `intent == "clarification"` used to
    # be dead disjuncts always covered by the keyword checks alongside them. Removed
    # rather than kept as decoration, since a future edit to one half without the other
    # would silently change nothing.
    if intent == "greeting":
        strategy = "GREETING"
        reason = "User query is a conversational greeting/thanks"
    elif is_out_of_scope or is_unsupported:
        strategy = "SAFE_REFUSAL"
        reason = "Query is out of scope or requests an unsupported telecom service"
    elif needs_clarification:
        strategy = "CLARIFICATION"
        reason = "Query is ambiguous or requires user clarification"

    # ── 2. Comparison Strategy (Dual/Multi Entities) ─────────────────────────
    elif any(k in q_lower for k in ["قارن", "مقارنة", "الفرق بين", "compare", " vs ", "versus", "احسن ولا"]):
        strategy = "MCP_COMPARISON"
        reason = "Comparative query between packages — using structured MCP ground truth"

    # ── 3. Price & Tax Calculation ───────────────────────────────────────────
    elif any(k in q_lower for k in ["احسب", "حساب", "ضريبة", "شامل الضريبة", "شامل الضريبه", "قبل الضريبة", "المبلغ الاجمالي", "tax", "calculate", "pretax", "inclusive"]) and any(c.isdigit() for c in question) and not entities:
        strategy = "MCP_CALCULATION"
        reason = "Explicit numeric price and tax calculation request"

    # ── 4. Activation Code Lookup ───────────────────────────────────────────
    elif any(k in q_lower for k in ["كود", "تفعيل", "اشتراك", "اشترك", "شحن", "تجديد", "ussd", "code", "activate"]) and (entities or any(c.isdigit() for c in question)):
        strategy = "MCP_ACTIVATION"
        reason = "Specific USSD activation code inquiry"

    # ── 5. Budget Recommendation ─────────────────────────────────────────────
    elif (budget_egp is not None and budget_egp > 0) or any(k in q_lower for k in ["اربت", "رشحلي", "أرشح", "اختارلي", "recommend", "suggest", "في حدود", "ميزانية", "budget"]):
        strategy = "MCP_RECOMMENDATION"
        reason = "Package recommendation based on budget or usage constraints"

    # ── 6. Exact Package Facts (MCP Ground Truth Priority) ───────────────────
    elif entities and len(entities) == 1:
        strategy = "MCP_EXACT"
        reason = f"Exact package inquiry targeting entity '{entities[0]}'"

    # Check for exact package mention in text even if entities list was partial
    elif any(re.search(pat, question, re.IGNORECASE) for pat in [
        r"(?:أقوى\s*كارت|اقوى\s*كارت|aqwa\s*card)\s*\d+",
        r"(?:حكاية\s*مكسات|hekaya\s*mixat)\s*\d+",
        r"(?:حكاية\s*إنترنت|حكاية\s*انترنت|hekaya\s*internet)\s*\d+",
        r"(?:إمرالد|امرالد|emerald)\s*\d+",
        r"(?:داتا\s*لاين|dataline)\s*\d+",
        r"(?:باقة|نظام)\s*\d+",
    ]):
        strategy = "MCP_EXACT"
        reason = "Exact package tier detected in query text"

    # ── 7. General Knowledge Base Question ───────────────────────────────────
    else:
        strategy = "RAG_ONLY"
        reason = "Broad telecom or knowledge base inquiry requiring document retrieval"

    # ── MCP_PLUS_RAG upgrade: an exact-entity lookup that also asks for
    # open-ended explanation/detail beyond the tool's compact structured fields
    # (e.g. "why is Emerald 780 worth it" vs just "price of Emerald 780") benefits
    # from KB narrative context on top of the verified facts, not instead of them.
    _explain_keywords = [
        "why", "explain", "tell me about", "details of", "what makes", "benefits of",
        "ليه", "إزاي", "ازاي", "اشرحلي", "وضحلي", "تفاصيل", "مميزات", "فايدة",
    ]
    if strategy == "MCP_EXACT" and any(k in q_lower for k in _explain_keywords):
        strategy = "MCP_PLUS_RAG"
        reason = "Exact package lookup plus an open-ended explanation request — supplementing verified facts with KB narrative context"

    # If MCP is disabled in configuration, fallback RAG-compatible strategies
    if not settings.MCP_ENABLED and strategy.startswith("MCP_"):
        strategy = "RAG_ONLY"
        reason = "MCP disabled in settings; falling back to Hybrid RAG"

    # ── 8. Strategy-Based Tool Permissions & Required Facts Planning ─────────
    # Only names of tools that actually exist in app/tools/ belong here — this list
    # is enforced by mcp_tool_node.call_cached() as a real permission gate for the
    # tools it calls via that path (get_package_details, get_activation_code,
    # calculate_price). "recommend_package" is kept as a documentation label even
    # though that branch calls app/tools/recommendation_engine.py directly rather
    # than going through call_cached. RAG retrieval is a separate graph node
    # (retrieve_node), not a callable tool, so it has no entry here.
    ALLOWED_TOOLS_MAP = {
        "GREETING": [],
        "SAFE_REFUSAL": [],
        "CLARIFICATION": [],
        "MCP_EXACT": ["get_package_details", "get_activation_code"],
        "MCP_CALCULATION": ["calculate_price", "get_package_details"],
        "MCP_ACTIVATION": ["get_activation_code", "get_package_details"],
        "MCP_RECOMMENDATION": ["recommend_package", "get_package_details"],
        "MCP_COMPARISON": ["get_package_details", "get_activation_code"],
        "MCP_PLUS_RAG": ["get_package_details"],
        "RAG_ONLY": [],
    }
    allowed_tools = ALLOWED_TOOLS_MAP.get(strategy, [])

    # Required facts plan based on strategy and intent
    if strategy == "MCP_CALCULATION":
        required_facts = ["base_price", "tax_type", "total_price_egp"]
    elif strategy == "MCP_ACTIVATION":
        required_facts = ["service", "activation_code"]
    elif strategy in {"MCP_EXACT", "MCP_COMPARISON"}:
        required_facts = ["package_name", "price", "quota", "minutes", "activation_code"]
    elif strategy == "MCP_RECOMMENDATION":
        required_facts = ["budget_egp", "recommended_package", "total_price_egp"]
    else:
        required_facts = ["general_telecom_info"]

    step_info = {
        "node": "strategy_router",
        "title_ar": "توجيه استراتيجية التنفيذ",
        "title_en": "Response Strategy Router",
        "status": "completed",
        "badge": f"🧭 {strategy}",
        "description_ar": f"الاستراتيجية المحددة: {strategy} — {reason}",
        "description_en": f"Selected Strategy: {strategy} ({reason})",
        "details": {
            "strategy": strategy,
            "reason": reason,
            "entities": entities,
            "budget_egp": budget_egp,
            "allowed_tools": allowed_tools,
            "required_facts": required_facts,
        },
    }

    return {
        "strategy": strategy,
        "strategy_reason": reason,
        "allowed_tools": allowed_tools,
        "required_facts": required_facts,
        "workflow_trace": [step_info],
    }
