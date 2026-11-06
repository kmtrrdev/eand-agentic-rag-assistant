"""
Server-signed conversation IDs so a client can't forge or guess another
session's ID and pull its stored history. Format: "<random-hex>.<hmac>".
"""
import hashlib
import hmac
import secrets
from typing import Optional

from app.config import settings


def _sign(value: str) -> str:
    return hmac.new(settings.SESSION_SECRET.encode(), value.encode(), hashlib.sha256).hexdigest()[:24]


def new_conversation_id() -> str:
    value = secrets.token_hex(12)
    return f"{value}.{_sign(value)}"


def verify_conversation_id(conversation_id: str) -> bool:
    if not conversation_id or "." not in conversation_id:
        return False
    value, _, signature = conversation_id.rpartition(".")
    if not value or not signature:
        return False
    return hmac.compare_digest(_sign(value), signature)


def resolve_conversation_id(conversation_id: Optional[str]) -> str:
    if conversation_id and verify_conversation_id(conversation_id):
        return conversation_id
    return new_conversation_id()
