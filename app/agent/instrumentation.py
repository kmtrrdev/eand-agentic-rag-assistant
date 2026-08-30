"""
app/agent/instrumentation.py
-----------------------------
Wraps every LangGraph node with:
  1. Precise per-node latency measurement (wall-clock, ms).
  2. Crash isolation — a node exception NEVER takes down the whole graph.
     Instead it is captured, logged with full traceback, and surfaced as a
     structured "error" entry in `state.errors` and `state.workflow_trace`
     so the exact node, exception type, message, and elapsed time are visible.
  3. Automatic latency_ms injection into every trace step a node returns,
     so the trace answers "how long did each step take" without every node
     having to do this bookkeeping itself.

This is the single place that makes the workflow trace trustworthy: node
authors focus on producing a `step_info` dict, and this wrapper guarantees
it always carries timing, and that failures are never silently swallowed.
"""
import functools
import logging
import time
import traceback
from typing import Any, Callable, Dict

logger = logging.getLogger("etisalat_kb.agent")


def _safe_fallback_answer(node_name: str, state: Dict[str, Any]) -> str:
    """Best-effort, language-matched apology used only when a node crashes
    hard enough that the graph cannot continue producing a real answer."""
    question = state.get("question", "") or ""
    try:
        from app.guardrails.security_utils import is_arabic_text
        is_ar = is_arabic_text(question)
    except Exception:
        is_ar = any("\u0600" <= ch <= "\u06FF" for ch in question)

    if is_ar:
        return (
            "عذراً، حدث خطأ تقني مؤقت أثناء معالجة طلبك. "
            "برجاء المحاولة مرة أخرى، أو التواصل مع خدمة عملاء اتصالات مصر على 111."
        )
    return (
        "I apologize, a temporary technical issue occurred while processing your request. "
        "Please try again, or contact e& Egypt customer support at 111."
    )


def instrument_node(node_name: str) -> Callable:
    """
    Decorator factory. Usage:

        graph.add_node("retrieve", instrument_node("retrieve")(retrieve_node))

    Guarantees:
      - Every trace step produced by the node gets `details.latency_ms` and
        `node` fields set/overwritten consistently.
      - On exception, returns a structured error trace step + error log entry
        instead of raising, so a single bad node cannot 500 the whole request.
    """

    def decorator(fn: Callable[[Dict[str, Any]], Dict[str, Any]]) -> Callable:
        @functools.wraps(fn)
        def wrapped(state: Dict[str, Any]) -> Dict[str, Any]:
            start = time.perf_counter()
            try:
                result = fn(state) or {}
                elapsed_ms = int((time.perf_counter() - start) * 1000)

                trace_steps = result.get("workflow_trace") or []
                for step in trace_steps:
                    step.setdefault("node", node_name)
                    step.setdefault("details", {})
                    step["details"]["latency_ms"] = elapsed_ms

                logger.info("node=%s status=ok latency_ms=%d", node_name, elapsed_ms)
                return result

            except Exception as exc:  # noqa: BLE001 - intentional catch-all boundary
                elapsed_ms = int((time.perf_counter() - start) * 1000)
                tb = traceback.format_exc()
                logger.error(
                    "node=%s status=error latency_ms=%d error_type=%s error=%s\n%s",
                    node_name, elapsed_ms, type(exc).__name__, exc, tb,
                )

                # Full traceback goes to server-side logs only (above). The
                # error entry attached to state/API responses is intentionally
                # traceback-free to avoid leaking internals to end clients.
                error_entry = {
                    "node": node_name,
                    "error_type": type(exc).__name__,
                    "error_message": str(exc),
                    "latency_ms": elapsed_ms,
                }

                error_step = {
                    "node": node_name,
                    "title_en": f"{node_name} — Unhandled Exception",
                    "title_ar": f"{node_name} — خطأ غير متوقع",
                    "status": "error",
                    "badge": "🔴 Node Error",
                    "description_en": f"{type(exc).__name__}: {exc}",
                    "description_ar": f"حدث خطأ في هذه المرحلة: {type(exc).__name__}: {exc}",
                    "details": {"latency_ms": elapsed_ms, "error_type": type(exc).__name__},
                }

                # Nodes that terminate the flow toward output_guard must always
                # leave a usable `answer` behind, or the API layer has nothing
                # to return. Populate one defensively.
                fallback: Dict[str, Any] = {
                    "workflow_trace": [error_step],
                    "errors": [error_entry],
                }
                if not state.get("answer"):
                    fallback["answer"] = _safe_fallback_answer(node_name, state)
                    fallback["confidence"] = 0.1
                    fallback["validation_result"] = "UNSUPPORTED"
                return fallback

        return wrapped

    return decorator
