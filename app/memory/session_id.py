"""
app/memory/session_id.py
-------------------------
Server-signed conversation IDs.

Problem: `conversation_id` used to be accepted verbatim from the client and used
directly as the memory-store lookup key. Any caller who knew or guessed another
session's ID (sequential IDs, a shared link, a log line) could pull that session's
full prior conversation into their own request as trusted context — a real
cross-tenant data leak, since that history is fed straight into the LLM prompt.

Fix: the server mints IDs of the form "<uuid_hex>.<hmac_sig>" using a server-side
secret. A client-supplied ID is only trusted if its signature verifies; otherwise
a fresh ID is minted. A client can still carry a conversation across turns (by
replaying the ID the server gave it in a prior response), but it can no longer
forge or guess its way into someone else's session.
"""
import hashlib
import hmac
import uuid
from typing import Optional

from app.config import settings

_SIG_LEN = 16  # hex chars; 64 bits is plenty to prevent forgery, keeps IDs short


def _sign(raw: str) -> str:
    digest = hmac.new(settings.SESSION_SECRET.encode("utf-8"), raw.encode("utf-8"), hashlib.sha256)
    return digest.hexdigest()[:_SIG_LEN]


def new_conversation_id() -> str:
    """Mint a fresh, server-signed conversation ID."""
    raw = uuid.uuid4().hex
    return f"{raw}.{_sign(raw)}"


def verify_conversation_id(candidate: Optional[str]) -> Optional[str]:
    """Return the candidate unchanged if its signature is valid, else None."""
    if not candidate or "." not in candidate:
        return None
    raw, _, sig = candidate.rpartition(".")
    if not raw or not sig:
        return None
    expected = _sign(raw)
    if hmac.compare_digest(expected, sig):
        return candidate
    return None


def resolve_conversation_id(candidate: Optional[str]) -> str:
    """Verify a client-supplied ID, or mint a new one if it's missing/invalid/forged."""
    verified = verify_conversation_id(candidate)
    return verified if verified is not None else new_conversation_id()
