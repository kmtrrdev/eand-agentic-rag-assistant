import operator
from typing import Annotated, Any, Dict, List, Optional, TypedDict


class AgentState(TypedDict, total=False):
    # ── Input ─────────────────────────────────────────────────────────────────
    question: str
    history: List[Dict[str, str]]
    conversation_id: Optional[str]

    # ── Guardrail ─────────────────────────────────────────────────────────────
    blocked: bool
    block_reason: Optional[str]

    # ── Classification (classify_node) ───────────────────────────────────────
    language: str
    intent: str
    category: str                      # catalog family id, e.g. "hekaya_mixat"
    service: str                       # display name, e.g. "Hekaya Mixat"
    line_type: str                     # "prepaid" | "postpaid" | ""
    budget_egp: Optional[float]
    device_type: Optional[str]
    usage_focus: Optional[str]         # "minutes" | "data" | "balanced"
    package_name_raw: Optional[str]
    tier_price_egp: Optional[float]
    keywords: List[str]
    entities: List[str]
    is_out_of_scope: bool
    is_unsupported_service: bool
    is_lang_switch: Optional[bool]
    lang_switch_user_q: Optional[str]
    lang_switch_target_lang: Optional[str]

    # ── Strategy & deterministic tool resolution ─────────────────────────────
    strategy: str
    needs_clarification: bool
    closest_matches: List[str]
    mcp_tools_called: List[str]
    tool_evidence: List[Dict[str, Any]]

    # ── Retrieval ─────────────────────────────────────────────────────────────
    retrieval_query: str               # query_rewrite_node's output; what retrieve_node actually searches with
    context: str
    sources: List[Dict[str, Any]]

    # ── Generation ────────────────────────────────────────────────────────────
    answer: str
    generation_repairs: int

    # ── Validation (actually wired into the graph — see graph.py) ───────────
    validation_result: str             # PASS | REPAIR | REFUSE
    validation_details: Dict[str, Any]
    confidence: float

    # ── Observability ─────────────────────────────────────────────────────────
    workflow_trace: Annotated[List[Dict[str, Any]], operator.add]
    errors: Annotated[List[Dict[str, Any]], operator.add]
