import logging
import os
import secrets
from typing import List, Optional
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger("app.config")


class Settings:
    # LLM provider API key (Azure OpenAI, Groq, OpenAI, Hugging Face router, etc.)
    LLM_API_KEY: Optional[str] = (
        os.getenv("LLM_API_KEY")
        or os.getenv("OPENAI_API_KEY")
        or os.getenv("HF_TOKEN")
    )

    LLM_BASE_URL: str = os.getenv(
        "LLM_BASE_URL",
        "https://api.openai.com/v1"
    )

    LLM_MODEL: str = os.getenv(
        "LLM_MODEL",
        "gpt-5-mini"
    )

    # Local LLM (Ollama / RTX 4050) settings
    LOCAL_LLM_BASE_URL: str = os.getenv(
        "LOCAL_LLM_BASE_URL",
        "http://localhost:11434/v1"
    )

    LOCAL_LLM_MODEL: str = os.getenv(
        "LOCAL_LLM_MODEL",
        "qwen2.5:3b"
    )

    LOCAL_LLM_API_KEY: str = os.getenv(
        "LOCAL_LLM_API_KEY",
        "ollama"
    )

    LLM_MAX_CONCURRENT_REQUESTS: int = int(
        os.getenv("LLM_MAX_CONCURRENT_REQUESTS", "1")
    )

    LOCAL_LLM_TIMEOUT: float = float(
        os.getenv("LOCAL_LLM_TIMEOUT", "120.0")
    )

    EMBEDDING_PROVIDER: str = os.getenv(
        "EMBEDDING_PROVIDER",
        "sentence_transformers"
    )

    EMBEDDING_MODEL: str = os.getenv(
        "EMBEDDING_MODEL",
        "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
    )

    CHROMA_PATH: str = os.getenv(
        "CHROMA_PATH",
        "./chroma_db"
    )

    COLLECTION_NAME: str = os.getenv(
        "COLLECTION_NAME",
        "etisalat_knowledge"
    )

    CHUNK_SIZE: int = int(
        os.getenv("CHUNK_SIZE", "700")
    )

    CHUNK_OVERLAP: int = int(
        os.getenv("CHUNK_OVERLAP", "120")
    )

    TOP_K: int = int(
        os.getenv("TOP_K", "15")
    )

    FINAL_K: int = int(
        os.getenv("FINAL_K", "10")
    )

    MAX_RETRIES: int = int(
        os.getenv("MAX_RETRIES", "1")
    )


    MAX_QUERY_LENGTH: int = int(
        os.getenv("MAX_QUERY_LENGTH", "2000")
    )

    MAX_HISTORY_MESSAGES: int = int(
        os.getenv("MAX_HISTORY_MESSAGES", "20")
    )

    # Default is an explicit, safe local-dev allowlist — NOT "*". The API is served
    # with allow_credentials=True (see api.py), and browsers reject that combined
    # with a wildcard origin anyway, so a wildcard default bought no real flexibility
    # while defaulting a customer-facing API wide open. Operators deploying to a real
    # domain must set CORS_ORIGINS explicitly.
    CORS_ORIGINS: str = os.getenv(
        "CORS_ORIGINS",
        "http://localhost:3000,http://127.0.0.1:3000,http://localhost:8000,http://127.0.0.1:8000"
    )

    # Secret used to sign server-issued conversation IDs (app/memory/session_id.py)
    # so a client can't forge/guess another session's ID and pull its history.
    # Auto-generated per-process if unset — fine for a single dev instance, but any
    # multi-worker or multi-restart deployment MUST set this explicitly in .env,
    # otherwise signed IDs minted by one worker won't verify on another.
    SESSION_SECRET: str = os.getenv("SESSION_SECRET", "")

    # Evaluation / LLM-as-a-Judge settings
    EVAL_LLM_API_KEY: Optional[str] = (
        os.getenv("EVAL_LLM_API_KEY")
        or os.getenv("LLM_API_KEY")
        or os.getenv("OPENAI_API_KEY")
    )

    EVAL_LLM_BASE_URL: str = os.getenv(
        "EVAL_LLM_BASE_URL",
        os.getenv("LLM_BASE_URL", "https://api.openai.com/v1")
    )

    EVAL_LLM_MODEL: str = os.getenv(
        "EVAL_LLM_MODEL",
        os.getenv("LLM_MODEL", "gpt-4o-mini")
    )


    # ── Persistent Memory (Phase 2) ───────────────────────────────────────────
    PERSISTENT_MEMORY_ENABLED: bool = os.getenv(
        "PERSISTENT_MEMORY_ENABLED", "true"
    ).lower() in ("true", "1", "yes")

    MEMORY_DB_PATH: str = os.getenv("MEMORY_DB_PATH", "./memory.db")

    # ── Chunking Strategy (Phase 3) ───────────────────────────────────────────
    CHUNKING_STRATEGY: str = os.getenv("CHUNKING_STRATEGY", "smart")

    # ── Cross-Encoder Reranker (Phase 4) ──────────────────────────────────────
    CROSS_ENCODER_RERANKER_ENABLED: bool = os.getenv(
        "CROSS_ENCODER_RERANKER_ENABLED", "true"
    ).lower() in ("true", "1", "yes")

    RERANKER_MODEL: str = os.getenv(
        "RERANKER_MODEL", "cross-encoder/ms-marco-MiniLM-L-6-v2"
    )

    RERANKER_TOP_N: int = int(os.getenv("RERANKER_TOP_N", "20"))

    # ── Structured Telecom Tools (app/tools/) ─────────────────────────────────
    # Toggles the deterministic tool-call layer (exact package lookup, USSD codes,
    # tax calculation, recommendations). When off, the graph falls back to RAG-only
    # for everything (see strategy_router.py). No MCP_HOST/MCP_PORT — these tools
    # are plain in-process function calls, not a client/server protocol.
    MCP_ENABLED: bool = os.getenv(
        "MCP_ENABLED", "true"
    ).lower() in ("true", "1", "yes")

    @property
    def cors_origin_list(self) -> List[str]:
        if not self.CORS_ORIGINS or self.CORS_ORIGINS.strip() == "*":
            return ["*"]
        return [origin.strip() for origin in self.CORS_ORIGINS.split(",") if origin.strip()]

    @property
    def cors_allow_credentials(self) -> bool:
        # Browsers refuse allow_credentials with a wildcard origin anyway; don't
        # request a combination that's both meaningless and looks permissive in logs.
        return self.cors_origin_list != ["*"]


settings = Settings()

if not settings.SESSION_SECRET:
    settings.SESSION_SECRET = secrets.token_hex(32)
    logger.warning(
        "SESSION_SECRET not set — generated a random one for this process. "
        "Conversation IDs signed now will stop verifying after a restart or on any "
        "other worker process. Set SESSION_SECRET in .env for real deployments."
    )