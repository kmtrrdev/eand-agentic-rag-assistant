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
    if intent == "greeting":
        strategy = "GREETING"
        reason = "User query is a conversational greeting/thanks"
    elif is_out_of_scope or is_unsupported or intent in {"out_of_scope", "unsupported_service"}:
        strategy = "SAFE_REFUSAL"
        reason = "Query is out of scope or requests an unsupported telecom service"
    elif needs_clarification or intent == "clarification":
        strategy = "CLARIFICATION"
        reason = "Query is ambiguous or requires user clarification"

    # ── 2. Comparison Strategy (Dual/Multi Entities) ─────────────────────────
    elif intent in {"comparison", "compare"} or any(k in q_lower for k in ["قارن", "مقارنة", "الفرق بين", "compare", " vs ", "versus", "احسن ولا"]):
        strategy = "MCP_COMPARISON"
        reason = "Comparative query between packages — using structured MCP ground truth"

    # ── 3. Price & Tax Calculation ───────────────────────────────────────────
    elif any(k in q_lower for k in ["احسب", "حساب", "ضريبة", "شامل الضريبة", "شامل الضريبه", "قبل الضريبة", "المبلغ الاجمالي", "tax", "calculate", "pretax", "inclusive"]) and any(c.isdigit() for c in question) and not entities:
        strategy = "MCP_CALCULATION"
        reason = "Explicit numeric price and tax calculation request"

    # ── 4. Activation Code Lookup ───────────────────────────────────────────
    elif intent == "activation_code" or (any(k in q_lower for k in ["كود", "تفعيل", "اشتراك", "اشترك", "شحن", "تجديد", "ussd", "code", "activate"]) and (entities or any(c.isdigit() for c in question))):
        strategy = "MCP_ACTIVATION"
        reason = "Specific USSD activation code inquiry"

    # ── 5. Budget Recommendation ─────────────────────────────────────────────
    elif (budget_egp is not None and budget_egp > 0) or intent == "recommendation" or any(k in q_lower for k in ["اربت", "رشحلي", "أرشح", "اختارلي", "recommend", "suggest", "في حدود", "ميزانية", "budget"]):
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

    # If MCP is disabled in configuration, fallback RAG-compatible strategies
    if not settings.MCP_ENABLED and strategy.startswith("MCP_"):
        strategy = "RAG_ONLY"
        reason = "MCP disabled in settings; falling back to Hybrid RAG"

    # ── 8. Strategy-Based Tool Permissions & Required Facts Planning ─────────
    ALLOWED_TOOLS_MAP = {
        "GREETING": [],
        "SAFE_REFUSAL": [],
        "CLARIFICATION": [],
        "MCP_EXACT": ["get_package_details", "get_activation_code", "search_knowledge_base"],
        "MCP_CALCULATION": ["calculate_price", "calculate_total_price", "get_package_details"],
        "MCP_ACTIVATION": ["get_activation_code", "get_package_details", "search_knowledge_base"],
        "MCP_RECOMMENDATION": ["recommend_package", "get_package_details", "search_knowledge_base"],
        "MCP_COMPARISON": ["get_package_details", "get_activation_code", "search_knowledge_base"],
        "MCP_PLUS_RAG": ["get_package_details", "search_knowledge_base"],
        "RAG_ONLY": ["search_knowledge_base"],
    }
    allowed_tools = ALLOWED_TOOLS_MAP.get(strategy, ["search_knowledge_base"])

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
