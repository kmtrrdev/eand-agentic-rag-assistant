import logging
import os
import secrets
from typing import List, Optional

from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger("app.config")


class Settings:
    # ── LLM (cloud) ───────────────────────────────────────────────────────────
    LLM_API_KEY: Optional[str] = (
        os.getenv("LLM_API_KEY") or os.getenv("OPENAI_API_KEY") or os.getenv("HF_TOKEN")
    )
    LLM_BASE_URL: str = os.getenv("LLM_BASE_URL", "https://api.openai.com/v1")
    LLM_MODEL: str = os.getenv("LLM_MODEL", "gpt-4.1-mini")
    LLM_MAX_CONCURRENT_REQUESTS: int = int(os.getenv("LLM_MAX_CONCURRENT_REQUESTS", "4"))
    LLM_TIMEOUT: float = float(os.getenv("LLM_TIMEOUT", "30.0"))

    _raw_local_base_url = os.getenv("LOCAL_LLM_BASE_URL", "http://localhost:11434/v1")
    # Automatically bridge to host when running inside a Docker container
    if os.path.exists("/.dockerenv") and ("localhost" in _raw_local_base_url or "127.0.0.1" in _raw_local_base_url):
        LOCAL_LLM_BASE_URL: str = _raw_local_base_url.replace("localhost", "host.docker.internal").replace("127.0.0.1", "host.docker.internal")
    else:
        LOCAL_LLM_BASE_URL: str = _raw_local_base_url
    LOCAL_LLM_MODEL: str = os.getenv("LOCAL_LLM_MODEL", "deepseek-r1:7b")
    LOCAL_LLM_API_KEY: str = os.getenv("LOCAL_LLM_API_KEY", "ollama")
    LOCAL_LLM_TIMEOUT: float = float(os.getenv("LOCAL_LLM_TIMEOUT", "120.0"))
    # A small local GPU (e.g. 4GB VRAM) can only serve one generation at a time
    # without OOM-crashing or badly degrading latency for every concurrent request.
    LOCAL_LLM_MAX_CONCURRENT: int = int(os.getenv("LOCAL_LLM_MAX_CONCURRENT", "1"))

    # ── Embeddings & Vector Store ─────────────────────────────────────────────
    # Multilingual by default — this assistant answers Arabic and English, and
    # an English-only embedding model would silently degrade Arabic retrieval.
    EMBEDDING_PROVIDER: str = os.getenv("EMBEDDING_PROVIDER", "sentence_transformers")
    EMBEDDING_MODEL: str = os.getenv(
        "EMBEDDING_MODEL", "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
    )
    CHROMA_PATH: str = os.getenv("CHROMA_PATH", "./chroma_db")
    COLLECTION_NAME: str = os.getenv("COLLECTION_NAME", "etisalat_knowledge")

    CHUNK_SIZE: int = int(os.getenv("CHUNK_SIZE", "700"))
    CHUNK_OVERLAP: int = int(os.getenv("CHUNK_OVERLAP", "120"))
    TOP_K: int = int(os.getenv("TOP_K", "15"))
    FINAL_K: int = int(os.getenv("FINAL_K", "6"))

    # Dynamic/Adaptive Retrieval Settings
    DYNAMIC_K_ENABLED: bool = os.getenv("DYNAMIC_K_ENABLED", "true").lower() in ("true", "1", "yes")
    MIN_K: int = int(os.getenv("MIN_K", "2"))
    MAX_K: int = int(os.getenv("MAX_K", "12"))
    # Minimum relative score ratio (w.r.t top chunk) to include a chunk in dynamic mode
    DYNAMIC_SCORE_RATIO_THRESHOLD: float = float(os.getenv("DYNAMIC_SCORE_RATIO_THRESHOLD", "0.60"))
    # Maximum allowed score drop-off between consecutive chunks before cutting off
    DYNAMIC_CLIFF_GAP: float = float(os.getenv("DYNAMIC_CLIFF_GAP", "0.22"))

    CROSS_ENCODER_RERANKER_ENABLED: bool = os.getenv(
        "CROSS_ENCODER_RERANKER_ENABLED", "true"
    ).lower() in ("true", "1", "yes")
    RERANKER_MODEL: str = os.getenv("RERANKER_MODEL", "cross-encoder/ms-marco-MiniLM-L-6-v2")
    RERANKER_TOP_N: int = int(os.getenv("RERANKER_TOP_N", "20"))
    # How much weight the pre-rerank RRF rank keeps vs. the (English-only)
    # cross-encoder's raw score when blending — 0.0 = old behavior (cross-encoder
    # fully overrides RRF order), 1.0 = cross-encoder score ignored entirely.
    # 0.35 was picked by sweeping evaluation/retrieval_eval_dataset.json: it fixes
    # Arabic queries where the cross-encoder was overturning a strong RRF top hit
    # with an unrelated chunk, without regressing any case that 0.0 got right.
    RERANKER_RRF_BLEND_WEIGHT: float = float(os.getenv("RERANKER_RRF_BLEND_WEIGHT", "0.35"))

    # ── Request limits ────────────────────────────────────────────────────────
    MAX_QUERY_LENGTH: int = int(os.getenv("MAX_QUERY_LENGTH", "2000"))
    MAX_HISTORY_MESSAGES: int = int(os.getenv("MAX_HISTORY_MESSAGES", "20"))
    RATE_LIMIT_PER_MINUTE: int = int(os.getenv("RATE_LIMIT_PER_MINUTE", "20"))

    # Default is an explicit, safe local-dev allowlist — NOT "*". The API is served
    # with allow_credentials=True, and browsers reject that combined with a
    # wildcard origin anyway, so operators deploying to a real domain must set
    # CORS_ORIGINS explicitly.
    CORS_ORIGINS: str = os.getenv(
        "CORS_ORIGINS",
        "http://localhost:3000,http://127.0.0.1:3000,http://localhost:8000,http://127.0.0.1:8000",
    )

    # Secret used to sign server-issued conversation IDs (app/memory/session_id.py)
    # so a client can't forge/guess another session's ID and pull its history.
    # Auto-generated per-process if unset — fine for a single dev instance, but any
    # multi-worker or multi-restart deployment MUST set this explicitly in .env.
    SESSION_SECRET: str = os.getenv("SESSION_SECRET", "")

    # ── Persistent conversation memory ────────────────────────────────────────
    PERSISTENT_MEMORY_ENABLED: bool = os.getenv(
        "PERSISTENT_MEMORY_ENABLED", "true"
    ).lower() in ("true", "1", "yes")
    MEMORY_DB_PATH: str = os.getenv("MEMORY_DB_PATH", "./memory.db")
    RESET_MEMORY_ON_STARTUP: bool = os.getenv(
        "RESET_MEMORY_ON_STARTUP", "false"
    ).lower() in ("true", "1", "yes")

    # ── Validation / repair loop ──────────────────────────────────────────────
    MAX_GENERATION_REPAIRS: int = int(os.getenv("MAX_GENERATION_REPAIRS", "1"))

    # ── MCP & Tools Configuration ─────────────────────────────────────────────
    MCP_TOOLS_ENABLED: bool = os.getenv("MCP_TOOLS_ENABLED", "true").lower() in ("true", "1", "yes")
    RAG_ONLY_MODE: bool = os.getenv("RAG_ONLY_MODE", "false").lower() in ("true", "1", "yes")

    @property
    def cors_origin_list(self) -> List[str]:
        if not self.CORS_ORIGINS or self.CORS_ORIGINS.strip() == "*":
            return ["*"]
        return [origin.strip() for origin in self.CORS_ORIGINS.split(",") if origin.strip()]

    @property
    def cors_allow_credentials(self) -> bool:
        return self.cors_origin_list != ["*"]


settings = Settings()

if not settings.SESSION_SECRET:
    settings.SESSION_SECRET = secrets.token_hex(32)
    logger.warning(
        "SESSION_SECRET not set — generated a random one for this process. "
        "Conversation IDs signed now will stop verifying after a restart or on any "
        "other worker process. Set SESSION_SECRET in .env for real deployments."
    )
