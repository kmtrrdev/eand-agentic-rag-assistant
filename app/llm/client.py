import asyncio
import contextvars
import logging
import threading
from typing import Any, Optional
from langchain_openai import ChatOpenAI

from app.config import settings

logger = logging.getLogger("app.llm.client")

# ── Context Var for Request-level Model Selection ────────────
_current_model_choice: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    "current_model_choice", default=None
)

# ── Context Var tracking what backend actually served the last get_llm() call in
# this request. Needed because a request that asked for "cloud" can be silently
# downgraded to local (missing/placeholder API key) — callers (api.py) must be able
# to report the model that truly answered, not just echo back what was requested.
_actual_backend_used: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    "actual_backend_used", default=None
)

_warned_missing_key = False


def get_actual_backend_used() -> Optional[str]:
    """'cloud', 'local', or None if get_llm() hasn't been called yet this request."""
    return _actual_backend_used.get()

# ── Concurrency & Resource Protection for 4GB VRAM ───────────
# Strictly serialize concurrent threads executing on the local Ollama instance with re-entrant lock
_local_thread_lock = threading.RLock()
_local_async_semaphores: dict[asyncio.AbstractEventLoop, asyncio.Semaphore] = {}
_sem_lock = threading.Lock()


def _get_async_semaphore() -> asyncio.Semaphore:
    """Get or create an asyncio semaphore for the current event loop."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
    with _sem_lock:
        if loop not in _local_async_semaphores:
            _local_async_semaphores[loop] = asyncio.Semaphore(max(1, settings.LLM_MAX_CONCURRENT_REQUESTS))
        return _local_async_semaphores[loop]


class LocalConcurrencyGuardedChatOpenAI(ChatOpenAI):
    """
    ChatOpenAI wrapper that enforces thread synchronization
    when executing local Ollama inference on RTX 4050 (4GB VRAM).
    """
    is_local_endpoint: bool = False

    def invoke(self, *args: Any, **kwargs: Any) -> Any:
        if self.is_local_endpoint:
            with _local_thread_lock:
                return super().invoke(*args, **kwargs)
        return super().invoke(*args, **kwargs)

    async def ainvoke(self, *args: Any, **kwargs: Any) -> Any:
        if self.is_local_endpoint:
            sem = _get_async_semaphore()
            async with sem:
                return await super().ainvoke(*args, **kwargs)
        return await super().ainvoke(*args, **kwargs)


def set_current_model_choice(model_choice: Optional[str]) -> None:
    """Set model choice for the current async/request context ('cloud' or 'local')."""
    _current_model_choice.set(model_choice)


def get_current_model_choice() -> Optional[str]:
    """Get active model choice from context."""
    return _current_model_choice.get()


def get_llm(
    timeout: float = 45.0,
    max_tokens: Optional[int] = None,
    temperature: float = 0.0,
    model_choice: Optional[str] = None,
) -> ChatOpenAI:
    """
    Get configured ChatOpenAI client.
    Supports dynamically selecting between Cloud LLM (OpenAI / Azure) and Local LLM (Ollama / RTX 4050).
    Enforces hardware protection and single-concurrency queueing for local inference.
    """
    choice = (model_choice or get_current_model_choice() or "cloud").lower().strip()

    if choice in ("local", "ollama", "qwen", "qwen2.5", "qwen2.5:3b", "local-gpu", "gpu"):
        # Local Ollama endpoint — explicitly requested, not a fallback.
        _actual_backend_used.set("local")
        effective_timeout = max(timeout, settings.LOCAL_LLM_TIMEOUT)
        effective_tokens = min(max_tokens, 768) if max_tokens is not None else 512
        kwargs = {
            "model": settings.LOCAL_LLM_MODEL,
            "temperature": temperature,
            "api_key": settings.LOCAL_LLM_API_KEY,
            "base_url": settings.LOCAL_LLM_BASE_URL,
            "timeout": effective_timeout,
            "max_retries": settings.MAX_RETRIES,
            "max_tokens": effective_tokens,
            "is_local_endpoint": True,
        }
        return LocalConcurrencyGuardedChatOpenAI(**kwargs)

    # Cloud LLM endpoint
    api_key = settings.LLM_API_KEY
    if not api_key or "your_api_key_here" in api_key.lower() or "placeholder" in api_key.lower():
        # Fallback to local if cloud key is not set — this is a real behavior change
        # (a materially weaker model answers) so it must be loud, not a log line the
        # caller can miss. get_actual_backend_used() lets api.py report the truth.
        global _warned_missing_key
        if not _warned_missing_key:
            logger.warning(
                "LLM_API_KEY is missing/placeholder — cloud model requests are being "
                "silently served by the local model (%s) instead of %s. Set a real "
                "LLM_API_KEY to restore cloud responses.",
                settings.LOCAL_LLM_MODEL, settings.LLM_MODEL,
            )
            _warned_missing_key = True
        _actual_backend_used.set("local")
        kwargs = {
            "model": settings.LOCAL_LLM_MODEL,
            "temperature": temperature,
            "api_key": settings.LOCAL_LLM_API_KEY,
            "base_url": settings.LOCAL_LLM_BASE_URL,
            "timeout": max(timeout, settings.LOCAL_LLM_TIMEOUT),
            "max_retries": settings.MAX_RETRIES,
            "max_tokens": min(max_tokens, 768) if max_tokens is not None else 512,
            "is_local_endpoint": True,
        }
        return LocalConcurrencyGuardedChatOpenAI(**kwargs)

    _actual_backend_used.set("cloud")
    kwargs = {
        "model": settings.LLM_MODEL,
        "temperature": temperature,
        "api_key": api_key,
        "base_url": settings.LLM_BASE_URL,
        "timeout": timeout,
        "max_retries": settings.MAX_RETRIES,
        "is_local_endpoint": False,
    }
    # For reasoning models (e.g. gpt-5-mini, o-series), reasoning tokens consume part of max_tokens.
    # Ensure minimum token headroom so reasoning does not exhaust the token budget before output generation.
    is_reasoning_model = any(m in settings.LLM_MODEL.lower() for m in ["gpt-5", "o1", "o3", "o4", "reasoning"])
    if max_tokens is not None:
        if is_reasoning_model:
            kwargs["max_tokens"] = max(max_tokens, 4096)
        else:
            kwargs["max_tokens"] = max_tokens
    elif is_reasoning_model:
        kwargs["max_tokens"] = 4096

    return LocalConcurrencyGuardedChatOpenAI(**kwargs)
