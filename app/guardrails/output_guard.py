"""Output guardrail: strips any leaked secrets or system-prompt fragments from
the final answer before it reaches the customer. Sanitize-only, never blocks —
by the time we're here the answer is already generated and worth salvaging."""
from app.guardrails.patterns import find_leaked_secrets, strip_system_leaks

_REDACTED = "[REDACTED]"


def sanitize_output(text: str) -> str:
    cleaned = strip_system_leaks(text or "")
    for secret in find_leaked_secrets(cleaned):
        cleaned = cleaned.replace(secret, _REDACTED)
    return cleaned.strip()
