"""
LLM client factory: builds a cloud (Azure/OpenAI-compatible) or local (Ollama)
chat model per the frontend's cloud/local toggle (site/index.html model-btn).

Per-request state (which backend the user asked for, which one actually ran)
is held in contextvars rather than plain module globals — this file is
imported once per process, but api.py's /chat handler runs one call per HTTP
request, often concurrently; a plain global would leak one request's model
choice into another's response under load.
"""
import contextvars
import logging
import threading
from typing import Optional

from langchain_openai import ChatOpenAI

from app.config import settings

logger = logging.getLogger("app.llm.client")

_model_choice: contextvars.ContextVar[str] = contextvars.ContextVar("model_choice", default="cloud")
_actual_backend: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar("actual_backend", default=None)

_LOCAL_ALIASES = {
    "local", "ollama", "qwen", "qwen2.5", "qwen2.5:3b", "local-gpu", "gpu",
    "deepseek", "deepseek-r1", "deepseek-r1:7b", "deepseek-r1-7b", "r1"
}
_local_slot = threading.Semaphore(settings.LOCAL_LLM_MAX_CONCURRENT)


def set_current_model_choice(choice: str) -> None:
    _model_choice.set("local" if (choice or "").lower().strip() in _LOCAL_ALIASES else "cloud")


def get_current_model_choice() -> str:
    return _model_choice.get()


def get_actual_backend_used() -> Optional[str]:
    return _actual_backend.get()


def _mark_backend_used(backend: str) -> None:
    _actual_backend.set(backend)


def _build_cloud_client(temperature: float, reasoning_effort: Optional[str] = None) -> ChatOpenAI:
    return ChatOpenAI(
        api_key=settings.LLM_API_KEY,
        base_url=settings.LLM_BASE_URL,
        model=settings.LLM_MODEL,
        temperature=temperature,
        max_tokens=2500,
        timeout=settings.LLM_TIMEOUT,
        reasoning_effort=reasoning_effort,
    )


def _build_local_client(temperature: float) -> ChatOpenAI:
    return ChatOpenAI(
        api_key=settings.LOCAL_LLM_API_KEY,
        base_url=settings.LOCAL_LLM_BASE_URL,
        model=settings.LOCAL_LLM_MODEL,
        temperature=temperature,
        max_tokens=600,
        max_retries=1,
        timeout=120.0,
        extra_body={"options": {"num_ctx": 4096, "num_predict": 600}},
    )


def get_chat_model(temperature: float = 0.2, reasoning_effort: Optional[str] = None) -> ChatOpenAI:
    """Return a chat model for the requested backend, honoring the frontend's
    cloud/local toggle, with a logged downgrade to local if no cloud key is set.

    reasoning_effort only applies to the cloud (gpt-5-family, reasoning) model —
    it's ignored for local models. Pass a real effort ("minimal"/"low"/...),
    not "none": on this Azure deployment "none" does NOT unlock a non-default
    `temperature` the way langchain-openai's client-side check assumes — the
    server still rejects temperature=0.0 with reasoning_effort="none" (HTTP
    400), so `temperature` stays a no-op for gpt-5-family here regardless.
    """
    requested = get_current_model_choice()

    if requested == "cloud" and not settings.LLM_API_KEY:
        logger.warning("Cloud model requested but LLM_API_KEY is not set — falling back to local model.")
        requested = "local"

    _mark_backend_used(requested)
    if requested == "local":
        return _build_local_client(temperature)
    return _build_cloud_client(temperature, reasoning_effort=reasoning_effort)


class local_llm_slot:
    """Context manager serializing calls to the local model so a small GPU
    isn't asked to run more generations at once than it can hold in VRAM.
    No-op for the cloud backend."""

    def __enter__(self):
        if get_current_model_choice() == "local":
            _local_slot.acquire()
        return self

    def __exit__(self, *exc_info):
        if get_current_model_choice() == "local":
            _local_slot.release()
        return False
