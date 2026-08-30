"""
app/observability.py
--------------------
Structured logging and observability utilities for the e& Egypt Agentic KB.

Features:
- Structured log records with request_id, conversation_id, latency
- Request/response timing context manager
- Per-node timing instrumentation helpers
- Safe formatting (no secrets, no PII in log output)

Usage in api.py:
    from app.observability import get_request_logger, log_request_summary

Usage in nodes:
    from app.observability import log_node_timing
"""
import logging
import time
import uuid
from contextlib import contextmanager
from typing import Any, Dict, Generator, Optional


# ── Base logger setup ─────────────────────────────────────────────────────────
def _setup_root_logger():
    fmt = "%(asctime)s [%(levelname)s] %(name)s request_id=%(request_id)s | %(message)s"
    handler = logging.StreamHandler()
    handler.setFormatter(_StructuredFormatter(fmt))
    root = logging.getLogger("etisalat_kb")
    if not root.handlers:
        root.addHandler(handler)
    root.setLevel(logging.INFO)
    return root


class _StructuredFormatter(logging.Formatter):
    """Formatter that injects request_id from LogRecord extra fields."""

    def format(self, record: logging.LogRecord) -> str:
        if not hasattr(record, "request_id"):
            record.request_id = "-"
        if not hasattr(record, "conversation_id"):
            record.conversation_id = "-"
        return super().format(record)


_root_logger = _setup_root_logger()


# ── Request-scoped logger factory ────────────────────────────────────────────

def get_request_logger(
    request_id: Optional[str] = None,
    conversation_id: Optional[str] = None,
) -> logging.LoggerAdapter:
    """
    Return a LoggerAdapter pre-populated with request_id and conversation_id.

    Args:
        request_id: Unique per-HTTP-request UUID (auto-generated if not provided).
        conversation_id: Optional persistent conversation ID.
    """
    rid = request_id or str(uuid.uuid4())[:8]
    extra = {
        "request_id": rid,
        "conversation_id": conversation_id or "-",
    }
    logger = logging.getLogger("etisalat_kb.api")
    return logging.LoggerAdapter(logger, extra)


# ── Request timing context manager ───────────────────────────────────────────

@contextmanager
def timed_request(
    logger: logging.LoggerAdapter,
    label: str = "request",
) -> Generator[Dict[str, Any], None, None]:
    """
    Context manager that measures wall-clock time and logs it on exit.

    Usage:
        with timed_request(log, "chat") as timing:
            result = agent.invoke(...)
        # timing["latency_ms"] is populated after the block
    """
    timing: Dict[str, Any] = {"label": label, "latency_ms": 0}
    start = time.perf_counter()
    try:
        yield timing
    finally:
        elapsed_ms = int((time.perf_counter() - start) * 1000)
        timing["latency_ms"] = elapsed_ms
        logger.info(f"{label} completed in {elapsed_ms}ms")


def log_request_summary(
    logger: logging.LoggerAdapter,
    question: str,
    intent: Optional[str],
    latency_ms: int,
    validation_result: Optional[str],
    confidence: Optional[float],
    num_sources: int,
    conversation_id: Optional[str] = None,
) -> None:
    """Log a structured summary line for every /chat request."""
    # Truncate question to 80 chars for log safety
    q_preview = (question or "")[:80].replace("\n", " ")
    logger.info(
        f"intent={intent or '-'} "
        f"validation={validation_result or '-'} "
        f"confidence={confidence or 0:.2f} "
        f"sources={num_sources} "
        f"latency_ms={latency_ms} "
        f"q={q_preview!r}"
    )


def log_node_timing(node_name: str, latency_ms: int) -> None:
    """Log per-node execution time (used inside LangGraph nodes)."""
    logging.getLogger(f"etisalat_kb.node.{node_name}").debug(
        f"node={node_name} latency_ms={latency_ms}"
    )
