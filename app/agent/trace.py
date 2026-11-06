"""
Workflow-trace helper shared by every node.

The node ids and step shape here (`node`, `title_en/ar`, `description_en`,
`badge`, `status`, `details`, `latency_ms`) are a small but real API contract:
site/assets/chat.js renders a fixed pipeline diagram keyed on these exact node
ids. Keeping trace construction in one helper (instead of copy-pasted bilingual
dicts inside every node, as before) is what lets that stay a one-line call per
node rather than 30 lines of UI-shaped bookkeeping mixed into business logic.
"""
import time
from typing import Any, Dict, Optional


def now() -> float:
    return time.perf_counter()


def elapsed_ms(start: float) -> int:
    return int((time.perf_counter() - start) * 1000)


def step(
    node: str,
    title_en: str,
    title_ar: str,
    description_en: str = "",
    badge: str = "Done",
    status: str = "completed",
    details: Optional[Dict[str, Any]] = None,
    latency_ms: Optional[int] = None,
) -> Dict[str, Any]:
    return {
        "node": node,
        "title_en": title_en,
        "title_ar": title_ar,
        "description_en": description_en,
        "badge": badge,
        "status": status,
        "details": details or {},
        "latency_ms": latency_ms,
    }


def error(node: str, exc: Exception, latency_ms: int) -> Dict[str, Any]:
    return {
        "node": node,
        "error_type": exc.__class__.__name__,
        "error_message": str(exc)[:300],
        "latency_ms": latency_ms,
    }
