import logging
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator

from app.agent.graph import get_agent
from app.config import settings
from app.memory.session_id import resolve_conversation_id
from app.observability import get_request_logger, log_request_summary
from app.rate_limit import is_rate_limited

from contextlib import asynccontextmanager

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("api")

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Reset conversation memory database on startup if configured
    if getattr(settings, "RESET_MEMORY_ON_STARTUP", True):
        try:
            from app.memory.sqlite_store import reset_memory_database
            reset_memory_database()
            logger.info("Conversation memory reset successfully on server startup.")
        except Exception as exc:
            logger.warning(f"Memory reset on startup encountered non-critical error: {exc}")

    # Ensure vector store is populated if running with a blank mounted volume
    try:
        from app.vectorstore.chroma_client import get_vectorstore
        store = get_vectorstore()
        if store._collection.count() == 0:
            logger.info("ChromaDB collection is empty on startup. Auto-ingesting catalog...")
            from app.ingestion.ingest import ingest_catalog
            ingest_catalog()
    except Exception as exc:
        logger.warning(f"Vectorstore auto-population check encountered non-critical error: {exc}")

    # Pre-warm models in memory on server startup
    logger.info("Pre-warming agent, vectorstore embeddings, and reranker...")
    try:
        from app.vectorstore.chroma_client import dense_search
        from app.retrieval.reranker import rerank
        get_agent()
        dense_search("warmup", 1)
        if getattr(settings, "CROSS_ENCODER_RERANKER_ENABLED", True):
            rerank("warmup", [{"content": "warmup", "metadata": {}}], top_n=1)
        logger.info("Pre-warming completed successfully.")
    except Exception as exc:
        logger.warning(f"Pre-warming encountered non-critical error: {exc}")
    yield

app = FastAPI(
    title="e& Egypt Agentic KB API",
    description="Agentic RAG API for e& Egypt telecom packages and services",
    version="2.0.0",
    docs_url="/docs",
    redoc_url=None,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=settings.cors_allow_credentials,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def add_no_cache_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response


@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception):
    logger.error(f"Unhandled error processing request {request.url.path}: {exc.__class__.__name__}")
    return JSONResponse(status_code=500, content={"detail": "An internal server error occurred. Please try again later."})


class ChatMessage(BaseModel):
    role: str
    content: str

    @field_validator("content")
    @classmethod
    def sanitize_content(cls, v: str) -> str:
        return (v or "").strip()[:1000]


class ChatRequest(BaseModel):
    question: str = Field(..., description="Customer question")
    history: List[ChatMessage] = Field(default_factory=list, description="Recent conversation turns")
    conversation_id: Optional[str] = Field(
        default=None, description="Persistent conversation ID. If provided, history is loaded from memory store."
    )
    model: Optional[str] = Field(
        default="cloud", description="Selected LLM provider: 'cloud' or 'local' (Ollama)."
    )

    @field_validator("question")
    @classmethod
    def validate_question(cls, v: str) -> str:
        q = (v or "").strip()
        if not q:
            raise ValueError("Question cannot be empty.")
        if len(q) > settings.MAX_QUERY_LENGTH:
            raise ValueError(f"Question exceeds maximum length of {settings.MAX_QUERY_LENGTH} characters.")
        return q


class ChatResponse(BaseModel):
    answer: str
    confidence: Optional[float] = None
    model_used: Optional[str] = None
    sources: List[Dict[str, Any]] = Field(default_factory=list)
    workflow: List[Dict[str, Any]] = Field(default_factory=list)
    query_analysis: Optional[Dict[str, Any]] = None
    conversation_id: Optional[str] = None
    request_id: Optional[str] = None
    latency_ms: Optional[int] = None
    errors: List[Dict[str, Any]] = Field(default_factory=list)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/api/packages")
def list_packages():
    """Full package catalog for the frontend's Packages page — reads the same
    app/data/catalog/*.yaml the chatbot and deterministic tools use, so the
    page can never drift from what the assistant actually answers with. Tax
    math reuses calculate_price_tool (tax_rules.yaml) rather than
    recomputing it in JavaScript."""
    from app.data.catalog import get_catalog
    from app.tools.calculate_price import calculate_price_tool

    catalog = get_catalog()
    families = []
    for family in catalog.families_list():
        tax_type = family.get("tax_type", "prepaid")
        tiers = []
        for tier in family["tiers"]:
            tier_tax_type = tier.get("tax_type") or tax_type
            price = calculate_price_tool(base_price=tier["price_egp"], tax_type=tier_tax_type)
            tiers.append({
                "id": tier["id"],
                "name_en": tier.get("name_en"),
                "name_ar": tier.get("name_ar"),
                "price_egp": tier.get("price_egp"),
                "total_egp": price.get("total_egp"),
                "tax_type": tier_tax_type,
                "ussd_code": tier.get("ussd_code"),
                "quota_label_en": tier.get("quota_label_en"),
                "quota_label_ar": tier.get("quota_label_ar"),
                "validity_days": tier.get("validity_days"),
                "description_en": tier.get("description_en"),
                "description_ar": tier.get("description_ar"),
                "perks_en": tier.get("perks_en"),
                "perks_ar": tier.get("perks_ar"),
            })
        families.append({
            "id": family["family"],
            "name_en": family.get("family_name_en"),
            "name_ar": family.get("family_name_ar"),
            "category": family.get("category"),
            "tax_type": tax_type,
            "default_ussd": family.get("default_ussd"),
            "description_en": family.get("family_description_en"),
            "description_ar": family.get("family_description_ar"),
            "tier_count": len(tiers),
            "tiers": tiers,
        })

    return {"families": families, "total_packages": sum(f["tier_count"] for f in families)}


@app.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest, request: Request):
    client_key = request.client.host if request.client else "unknown"
    if is_rate_limited(client_key):
        raise HTTPException(status_code=429, detail="Too many requests. Please slow down and try again shortly.")

    request_id = str(uuid.uuid4())[:8]
    # Client-supplied conversation_id is only trusted if it verifies against the
    # server's signature — an unsigned/forged/guessed ID gets a fresh session
    # instead of silently loading whatever history happens to sit under that key.
    conversation_id = resolve_conversation_id(req.conversation_id)
    req_logger = get_request_logger(request_id=request_id, conversation_id=conversation_id)

    from app.llm.client import set_current_model_choice
    set_current_model_choice(req.model or "cloud")

    question = req.question.strip()
    t_start = time.perf_counter()

    clean_history: List[Dict[str, str]] = []
    if settings.PERSISTENT_MEMORY_ENABLED:
        try:
            from app.memory.sqlite_store import get_memory_store
            store = get_memory_store()
            stored = store.get_history(conversation_id, max_turns=settings.MAX_HISTORY_MESSAGES // 2)
            clean_history = stored or [
                {"role": msg.role, "content": msg.content}
                for msg in req.history[-settings.MAX_HISTORY_MESSAGES:] if msg.content
            ]
        except Exception as exc:
            req_logger.warning(f"Memory load failed: {exc}")
            clean_history = [
                {"role": msg.role, "content": msg.content}
                for msg in req.history[-settings.MAX_HISTORY_MESSAGES:] if msg.content
            ]
    else:
        clean_history = [
            {"role": msg.role, "content": msg.content}
            for msg in req.history[-settings.MAX_HISTORY_MESSAGES:] if msg.content
        ]

    try:
        agent = get_agent()
        result = agent.invoke({
            "question": question,
            "history": clean_history,
            "conversation_id": conversation_id,
        })
    except Exception as exc:
        req_logger.error(f"Agent invocation failed: {exc}", exc_info=True)
        raise HTTPException(status_code=500, detail="An error occurred while processing your request. Please try again.")

    latency_ms = int((time.perf_counter() - t_start) * 1000)
    final_answer = result.get("answer", "I could not answer that question. Could you please rephrase it?")

    if settings.PERSISTENT_MEMORY_ENABLED:
        try:
            from app.memory.sqlite_store import get_memory_store
            get_memory_store().save_turn(conversation_id, question, final_answer)
        except Exception as exc:
            req_logger.warning(f"Memory save failed: {exc}")

    analysis_data = {
        "intent": result.get("intent"),
        "strategy": result.get("strategy"),
        "category": result.get("category"),
        "service": result.get("service"),
        "line_type": result.get("line_type"),
        "budget_egp": result.get("budget_egp"),
        "keywords": result.get("keywords", []),
        "entities": result.get("entities", []),
        "validation_result": result.get("validation_result"),
        "is_out_of_scope": result.get("is_out_of_scope", False),
        "is_unsupported_service": result.get("is_unsupported_service", False),
        "mcp_tools_called": result.get("mcp_tools_called", []),
    }

    log_request_summary(
        logger=req_logger, question=question, intent=result.get("intent"), latency_ms=latency_ms,
        validation_result=result.get("validation_result"), confidence=result.get("confidence"),
        num_sources=len(result.get("sources", []) or []), conversation_id=conversation_id,
    )

    node_errors = result.get("errors", []) or []
    for err in node_errors:
        req_logger.error(
            "node_failure node=%s type=%s message=%s latency_ms=%s",
            err.get("node"), err.get("error_type"), err.get("error_message"), err.get("latency_ms"),
        )

    from app.llm.client import get_actual_backend_used, _LOCAL_ALIASES
    actual_backend = get_actual_backend_used() or (
        "local" if (req.model or "").lower() in _LOCAL_ALIASES else "cloud"
    )
    model_display = (
        f"Local GPU ({settings.LOCAL_LLM_MODEL})" if actual_backend == "local" else f"Cloud ({settings.LLM_MODEL})"
    )

    return ChatResponse(
        answer=final_answer,
        confidence=result.get("confidence"),
        model_used=model_display,
        sources=result.get("sources", []) or [],
        workflow=result.get("workflow_trace", []) or [],
        query_analysis=analysis_data,
        conversation_id=conversation_id,
        request_id=request_id,
        latency_ms=latency_ms,
        errors=node_errors,
    )


@app.api_route("/chat/reset", methods=["GET", "POST"])
async def reset_chat_session(request: Request):
    """Resets memory for a specific conversation_id or clears all stored turns."""
    conv_id = None
    if request.method == "POST":
        content_type = request.headers.get("content-type", "")
        try:
            if "application/json" in content_type:
                data = await request.json()
                if isinstance(data, dict):
                    conv_id = data.get("conversation_id")
            else:
                body_bytes = await request.body()
                if body_bytes:
                    raw_text = body_bytes.decode("utf-8", errors="ignore").strip()
                    try:
                        import json
                        data = json.loads(raw_text)
                        if isinstance(data, dict):
                            conv_id = data.get("conversation_id")
                    except Exception:
                        conv_id = raw_text.strip('"\'')
        except Exception as exc:
            logger.warning(f"Error parsing reset request payload: {exc}")

    if not conv_id:
        conv_id = request.query_params.get("conversation_id")

    from app.memory.sqlite_store import get_memory_store
    store = get_memory_store()
    if conv_id:
        store.clear_conversation(conv_id)
        logger.info(f"Cleared memory for conversation_id={conv_id}")
        return {"status": "ok", "message": f"Conversation {conv_id} cleared"}
    store.clear_all()
    logger.info("Cleared all conversation memory via reset endpoint.")
    return {"status": "ok", "message": "All session memory reset"}


possible_site_dirs = [
    Path(__file__).resolve().parent.parent / "site",
    Path(__file__).resolve().parent.parent.parent / "site",
    Path("site").resolve(),
    Path("../site").resolve(),
    Path("/app/site").resolve(),
]

site_dir = next(
    (candidate for candidate in possible_site_dirs if candidate.exists() and (candidate / "index.html").exists()),
    None,
)

if site_dir:
    app.mount("/", StaticFiles(directory=str(site_dir), html=True), name="site")
else:
    @app.get("/")
    def root():
        return {
            "status": "ok",
            "message": "e& Egypt Agentic KB API is running.",
            "docs": "/docs",
            "health": "/health",
            "chat_endpoint": "POST /chat",
        }
