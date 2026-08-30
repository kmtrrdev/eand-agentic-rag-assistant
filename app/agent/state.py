import operator
from typing import Annotated, Any, Dict, List, Optional, TypedDict


class AgentState(TypedDict, total=False):
    # ── User Input & Context ───────────────────────────────────────────────────
    question: str
    history: List[Dict[str, str]]
    conversation_id: Optional[str]

    # ── Guardrails State ──────────────────────────────────────────────────────
    guardrail_result: Optional[Dict[str, Any]]

    # ── Profiling & Query Understanding ────────────────────────────────────────
    intent: str
    category: str
    service: str
    sub_track: Optional[str]          # e.g. "Mixat" | "Internet" for Hekaya
    line_type: str
    data_usage: str
    voice_usage: str
    budget_egp: Optional[float]
    keywords: List[str]
    entities: List[str]
    is_out_of_scope: bool
    is_unsupported_service: bool
    needs_clarification: bool         # True when query is genuinely ambiguous
    clarification_hint: Optional[str] # Suggested clarifying question
    pending_clarification: Optional[str]
    clarification_candidates: List[str]
    analysis_summary: str

    # ── Response Strategy Routing & Tool Policy ───────────────────────────────
    # GREETING | SAFE_REFUSAL | CLARIFICATION | MCP_EXACT | MCP_CALCULATION |
    # MCP_ACTIVATION | MCP_RECOMMENDATION | MCP_COMPARISON | MCP_PLUS_RAG | RAG_ONLY
    strategy: str
    strategy_reason: str
    allowed_tools: List[str]
    required_facts: List[str]

    # ── Recommendation Constraints & Candidate Filtering State ───────────────
    recommendation_constraints: Optional[Dict[str, Any]]
    candidate_packages: List[Dict[str, Any]]
    filtered_candidates: List[Dict[str, Any]]
    rejected_candidates: List[Dict[str, Any]]
    selected_package: Optional[Dict[str, Any]]
    recommendation_validation: Optional[Dict[str, Any]]
    recommendation_attempts: int      # Default ceiling: 2

    # ── MCP Ground Truth State & Cache ────────────────────────────────────────
    mcp_tools_called: List[str]
    mcp_tool_results: List[Dict[str, Any]]
    mcp_evidence: List[Dict[str, Any]]

    # ── Retrieval & Search State ──────────────────────────────────────────────
    rewritten_query: str
    documents: List[Any]
    context: str
    sources: List[Dict[str, Any]]
    retrieval_evidence: List[Dict[str, Any]]
    retrieval_status: str             # RETRIEVAL_GOOD | RETRIEVAL_WEAK | RETRIEVAL_FAILED
    retrieval_relevance_score: float
    previous_retrieval_score: Optional[float]
    current_retrieval_score: Optional[float]
    last_retrieval_query: Optional[str]
    retrieval_diagnostics: Dict[str, Any]

    # ── Subsystem Independent Retry Budgets ────────────────────────────────────
    retrieval_attempts: int           # Default ceiling: 2
    rewrite_attempts: int             # Default ceiling: 1
    generation_repairs: int           # Default ceiling: 1
    validation_attempts: int          # Default ceiling: 1
    mcp_attempts: int                 # Default ceiling: 1
    last_retry_reason: Optional[str]
    last_failure_type: Optional[str]
    repair_strategy: Optional[str]    # REGENERATE_FROM_MCP | FIX_PRICE | FIX_USSD | RETRIEVE_MISSING

    # ── Generation & Security State ───────────────────────────────────────────
    answer: str
    sanitized_answer: str

    # ── Claim-Level Validation Diagnostics State ──────────────────────────────
    # PASS | REPAIR | REFUSE
    validation_result: str
    validation_details: Dict[str, Any]
    claims: List[Dict[str, Any]]
    claim_verification: List[Dict[str, Any]]
    unsupported_claims: List[str]
    contradictions: List[str]
    missing_evidence: List[str]
    confidence: float

    # ── Final Answer ──────────────────────────────────────────────────────────
    final_answer: str

    # ── Execution Trace & Observability ───────────────────────────────────────
    latency_metrics: Dict[str, float]
    workflow_trace: Annotated[List[Dict[str, Any]], operator.add]
    errors: Annotated[List[Dict[str, Any]], operator.add]

