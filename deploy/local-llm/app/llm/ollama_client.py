"""
app/llm/ollama_client.py
------------------------
Local LLM client for e& Egypt Agentic KB.
Optimized for Lenovo Legion Slim 5i (RTX 4050 4GB VRAM / 16GB RAM).

Features:
- Concurrency Semaphore: strictly serializes calls to local Ollama (1 concurrent request max).
- Configurable via .env: model, context length, max tokens, temperature, keep_alive.
- Dual interface: provides both native ChatOllama and OpenAI-compatible ChatOpenAI.
"""
import asyncio
import logging
import os
import threading
import time
from typing import Any, List, Optional

import requests
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger("local_llm.ollama_client")

# ── Config from .env ─────────────────────────────────────────
_OLLAMA_BASE_URL: str = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
_OLLAMA_MODEL: str = os.getenv("OLLAMA_MODEL", "qwen2.5:3b")
_LLM_CONTEXT_LENGTH: int = int(os.getenv("LLM_CONTEXT_LENGTH", "4096"))
_LLM_MAX_TOKENS: int = int(os.getenv("LLM_MAX_TOKENS", "512"))
_LLM_TEMPERATURE: float = float(os.getenv("LLM_TEMPERATURE", "0.2"))
_OLLAMA_KEEP_ALIVE: str = os.getenv("OLLAMA_KEEP_ALIVE", "5m")
_LLM_MAX_CONCURRENT: int = int(os.getenv("LLM_MAX_CONCURRENT_REQUESTS", "1"))

# ── Concurrency Protection ───────────────────────────────────
_local_thread_sem = threading.Semaphore(max(1, _LLM_MAX_CONCURRENT))
_local_async_sems: dict[asyncio.AbstractEventLoop, asyncio.Semaphore] = {}
_sem_lock = threading.Lock()


def _get_async_sem() -> asyncio.Semaphore:
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
    with _sem_lock:
        if loop not in _local_async_sems:
            _local_async_sems[loop] = asyncio.Semaphore(max(1, _LLM_MAX_CONCURRENT))
        return _local_async_sems[loop]


# ── Health Check ─────────────────────────────────────────────

def check_ollama_health(timeout: float = 3.0) -> bool:
    """Return True if Ollama server is reachable, False otherwise."""
    try:
        response = requests.get(f"{_OLLAMA_BASE_URL}/api/tags", timeout=timeout)
        return response.status_code == 200
    except Exception:
        return False


def wait_for_ollama(max_wait_seconds: int = 30, poll_interval: float = 1.0) -> bool:
    """
    Poll Ollama until it responds or max_wait_seconds is reached.
    Returns True if Ollama came up, False if it timed out.
    """
    start = time.time()
    while (time.time() - start) < max_wait_seconds:
        if check_ollama_health():
            return True
        time.sleep(poll_interval)
    return False


def get_available_models() -> List[str]:
    """Return list of model names currently available in Ollama."""
    try:
        resp = requests.get(f"{_OLLAMA_BASE_URL}/api/tags", timeout=5)
        if resp.status_code == 200:
            data = resp.json()
            return [m["name"] for m in data.get("models", [])]
    except Exception:
        pass
    return []


def unload_model_from_vram(model_name: Optional[str] = None) -> bool:
    """
    Gracefully unload model from VRAM by setting keep_alive to 0.
    Does NOT delete the model weights from disk.
    """
    target = model_name or _OLLAMA_MODEL
    try:
        resp = requests.post(
            f"{_OLLAMA_BASE_URL}/api/generate",
            json={"model": target, "keep_alive": 0},
            timeout=10,
        )
        return resp.status_code == 200
    except Exception as exc:
        logger.warning("Failed to unload model %s from VRAM: %s", target, exc)
        return False


# ── Native ChatOllama Wrapper with Concurrency Guard ─────────

def get_llm(
    timeout: float = 120.0,
    max_tokens: Optional[int] = None,
    temperature: float = _LLM_TEMPERATURE,
    model: Optional[str] = None,
    check_health: bool = True,
):
    """
    Get a configured ChatOllama client wrapped with concurrency guard.
    """
    from langchain_ollama import ChatOllama

    if check_health and not check_ollama_health():
        raise RuntimeError(
            f"Ollama is not running at {_OLLAMA_BASE_URL}.\n"
            "Please start it with: scripts\\start_local_ai.bat\n"
            "Or manually: ollama serve"
        )

    target_model = model or _OLLAMA_MODEL
    num_predict = max_tokens if max_tokens is not None else _LLM_MAX_TOKENS

    class ConcurrencyGuardedChatOllama(ChatOllama):
        def invoke(self, *args: Any, **kwargs: Any) -> Any:
            with _local_thread_sem:
                return super().invoke(*args, **kwargs)

        async def ainvoke(self, *args: Any, **kwargs: Any) -> Any:
            sem = _get_async_sem()
            async with sem:
                return await super().ainvoke(*args, **kwargs)

    llm = ConcurrencyGuardedChatOllama(
        model=target_model,
        base_url=_OLLAMA_BASE_URL,
        temperature=temperature,
        num_predict=num_predict,
        num_ctx=_LLM_CONTEXT_LENGTH,
        timeout=timeout,
        keep_alive=_OLLAMA_KEEP_ALIVE,
    )

    logger.info(
        "ChatOllama ready | model=%s | ctx=%s | max_tokens=%s | temp=%s",
        target_model, _LLM_CONTEXT_LENGTH, num_predict, temperature
    )
    return llm


# ── OpenAI-Compatible Client ──────────────────────────────────

def get_openai_compatible_llm(
    timeout: float = 120.0,
    max_tokens: Optional[int] = None,
    temperature: float = _LLM_TEMPERATURE,
    model: Optional[str] = None,
):
    """
    Get a ChatOpenAI client pointed at Ollama's /v1 endpoint with concurrency protection.
    """
    from langchain_openai import ChatOpenAI

    if not check_ollama_health():
        raise RuntimeError(
            f"Ollama is not running at {_OLLAMA_BASE_URL}.\n"
            "Please start it with: scripts\\start_local_ai.bat"
        )

    target_model = model or _OLLAMA_MODEL
    num_predict = max_tokens if max_tokens is not None else _LLM_MAX_TOKENS

    class ConcurrencyGuardedChatOpenAI(ChatOpenAI):
        def invoke(self, *args: Any, **kwargs: Any) -> Any:
            with _local_thread_sem:
                return super().invoke(*args, **kwargs)

        async def ainvoke(self, *args: Any, **kwargs: Any) -> Any:
            sem = _get_async_sem()
            async with sem:
                return await super().ainvoke(*args, **kwargs)

    return ConcurrencyGuardedChatOpenAI(
        model=target_model,
        temperature=temperature,
        api_key="ollama",
        base_url=f"{_OLLAMA_BASE_URL}/v1",
        timeout=timeout,
        max_retries=1,
        max_tokens=num_predict,
    )
