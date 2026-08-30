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
from app.guardrails.output_guard import sanitize_output
from app.observability import get_request_logger, log_request_summary

# Configure safe structured logger
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("api")


app = FastAPI(
    title="e& Egypt Agentic KB API",
    description="Agentic RAG API for e& Egypt telecom packages and services",
    version="1.0.0",
    docs_url="/docs",
    redoc_url=None,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
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
    """Catch-all exception handler to avoid leaking stack traces or internals to clients."""
    logger.error(f"Unhandled error processing request {request.url.path}: {exc.__class__.__name__}")
    return JSONResponse(
        status_code=500,
        content={"detail": "An internal server error occurred. Please try again later."}
    )


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
        default=None,
        description="Persistent conversation ID. If provided, history is loaded from memory store."
    )
    model: Optional[str] = Field(
        default="cloud",
        description="Selected LLM provider: 'cloud' (GPT-4o mini) or 'local' (Local GPU RTX 4050 / Qwen 2.5 3B)"
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
    model_used: Optional[str] = Field(
        default=None,
        description="Display name of the model that generated this answer (e.g. 'Local GPU (Qwen 2.5 3B)' or 'Cloud (GPT-4o mini)')"
    )
    sources: List[Dict[str, Any]] = Field(default_factory=list)
    workflow: List[Dict[str, Any]] = Field(default_factory=list)
    query_analysis: Optional[Dict[str, Any]] = None
    conversation_id: Optional[str] = None
    request_id: Optional[str] = None
    latency_ms: Optional[int] = None
    errors: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="Any node-level exceptions captured during this request "
                     "(node name, exception type/message, latency at failure). "
                     "Empty on a fully healthy run.",
    )


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest):
    request_id = str(uuid.uuid4())[:8]
    conversation_id = req.conversation_id or str(uuid.uuid4())
    req_logger = get_request_logger(request_id=request_id, conversation_id=conversation_id)

    from app.llm.client import set_current_model_choice
    selected_choice = (req.model or "cloud").lower().strip()
    set_current_model_choice(selected_choice)

    question = req.question.strip()
    t_start = time.perf_counter()

    # ── Load history: merge persistent memory + request-provided history ──────
    clean_history: List[Dict[str, str]] = []

    if settings.PERSISTENT_MEMORY_ENABLED:
        try:
            from app.memory.sqlite_store import get_memory_store
            store = get_memory_store()
            if store and req.conversation_id:
                stored = store.get_history(conversation_id, max_turns=settings.MAX_HISTORY_MESSAGES // 2)
                if stored:
                    clean_history = stored
                else:
                    clean_history = [
                        {"role": msg.role, "content": msg.content}
                        for msg in req.history[-settings.MAX_HISTORY_MESSAGES:]
                        if msg.content
                    ]
            else:
                clean_history = [
                    {"role": msg.role, "content": msg.content}
                    for msg in req.history[-settings.MAX_HISTORY_MESSAGES:]
                    if msg.content
                ]
        except Exception as exc:
            req_logger.warning(f"Memory load failed: {exc}")
            clean_history = [
                {"role": msg.role, "content": msg.content}
                for msg in req.history[-settings.MAX_HISTORY_MESSAGES:]
                if msg.content
            ]
    else:
        clean_history = [
            {"role": msg.role, "content": msg.content}
            for msg in req.history[-settings.MAX_HISTORY_MESSAGES:]
            if msg.content
        ]

    # ── Invoke agent ──────────────────────────────────────────────────────────
    try:
        agent = get_agent()
        result = agent.invoke({
            "question": question,
            "history": clean_history,
            "retry_count": 0,
            "conversation_id": conversation_id,
        })
    except Exception as exc:
        req_logger.error(f"Agent invocation failed: {exc.__class__.__name__}")
        raise HTTPException(
            status_code=500,
            detail="An error occurred while processing your request. Please try again."
        )

    latency_ms = int((time.perf_counter() - t_start) * 1000)

    raw_answer = result.get(
        "answer",
        "I could not answer that question. Could you please rephrase it?"
    )
    final_answer = sanitize_output(raw_answer)

    # ── Persist conversation turn ─────────────────────────────────────────────
    if settings.PERSISTENT_MEMORY_ENABLED:
        try:
            from app.memory.sqlite_store import get_memory_store
            store = get_memory_store()
            if store:
                store.save_turn(conversation_id, question, final_answer)
        except Exception as exc:
            req_logger.warning(f"Memory save failed: {exc}")

    # ── Build response ────────────────────────────────────────────────────────
    analysis_data = {
        "intent": result.get("intent"),
        "strategy": result.get("strategy"),
        "category": result.get("category"),
        "service": result.get("service"),
        "line_type": result.get("line_type"),
        "budget_egp": result.get("budget_egp"),
        "keywords": result.get("keywords", []),
        "entities": result.get("entities", []),
        "retrieval_status": result.get("retrieval_status"),
        "validation_result": result.get("validation_result"),
        "is_out_of_scope": result.get("is_out_of_scope", False),
        "is_unsupported_service": result.get("is_unsupported_service", False),
        "mcp_tools_called": result.get("mcp_tools_called", []),
    }

    # ── Structured log ────────────────────────────────────────────────────────
    log_request_summary(
        logger=req_logger,
        question=question,
        intent=result.get("intent"),
        latency_ms=latency_ms,
        validation_result=result.get("validation_result"),
        confidence=result.get("confidence"),
        num_sources=len(result.get("sources", []) or []),
        conversation_id=conversation_id,
    )

    node_errors = result.get("errors", []) or []
    if node_errors:
        for err in node_errors:
            req_logger.error(
                "node_failure node=%s type=%s message=%s latency_ms=%s",
                err.get("node"), err.get("error_type"), err.get("error_message"), err.get("latency_ms"),
            )

    model_display = (
        f"Local GPU ({settings.LOCAL_LLM_MODEL})"
        if selected_choice in ("local", "ollama", "qwen", "qwen2.5", "qwen2.5:3b", "local-gpu", "gpu")
        else f"Cloud ({settings.LLM_MODEL})"
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



# Locate static site folder
possible_site_dirs = [
    Path(__file__).resolve().parent.parent / "site",
    Path(__file__).resolve().parent.parent.parent / "site",
    Path("site").resolve(),
    Path("../site").resolve(),
    Path("/app/site").resolve(),
]

site_dir = next(
    (
        candidate
        for candidate in possible_site_dirs
        if candidate.exists() and (candidate / "index.html").exists()
    ),
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
