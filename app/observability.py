"""Structured per-request logging."""
import logging
from typing import Optional

logger = logging.getLogger("etisalat_kb.api")


def get_request_logger(request_id: str, conversation_id: str) -> logging.LoggerAdapter:
    return logging.LoggerAdapter(logger, {"request_id": request_id, "conversation_id": conversation_id})


def log_request_summary(
    logger: logging.LoggerAdapter,
    question: str,
    intent: Optional[str],
    latency_ms: int,
    validation_result: Optional[str],
    confidence: Optional[float],
    num_sources: int,
    conversation_id: str,
) -> None:
    logger.info(
        "request_id=%s conversation_id=%s | intent=%s validation=%s confidence=%s "
        "sources=%s latency_ms=%s q=%r",
        logger.extra.get("request_id"), conversation_id, intent, validation_result,
        confidence, num_sources, latency_ms, question[:120],
    )
