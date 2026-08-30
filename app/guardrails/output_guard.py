import re
from app.guardrails.garak_guard import GarakOutputGuard
from app.guardrails.security_utils import redact_secrets, sanitize_raw_html
from app.text_cleanup import clean_customer_text


THINKING_MARKERS = [
    "here's a thinking process",
    "thinking process:",
    "analyze user input",
    "draft construction",
    "draft structure",
    "draft response",
]


def sanitize_output(text: str) -> str:
    """
    Final security filter on assistant output using Garak output detectors.
    1. Garak System Prompt Echo detector (redacts leaked internal protocols).
    2. Garak Secret & API key detector (redacts high-entropy keys/tokens).
    3. Garak DAN / Jailbreak compliance scrubber.
    4. Removes hidden thinking/reasoning XML tokens.
    5. Strips raw HTML and script tags to prevent XSS.
    6. Applies clean plain-text customer formatting.
    """
    if not text:
        return ""

    # 1. Apply Garak Output Guardrail (System Prompt Echo, API Keys, Jailbreak Persona)
    cleaned = GarakOutputGuard.sanitize(str(text))

    # 2. Check for intermediate thought markers
    has_thinking = "<think>" in cleaned or any(marker in cleaned.lower() for marker in THINKING_MARKERS)
    if has_thinking:
        cleaned = re.sub(r"^<think>", "", cleaned).strip()
        matches = list(
            re.finditer(
                r"(?:\d+\.\s*)?\*{0,2}(?:Draft(?:\s+\w+)*|Final Response|Response|Here is the (?:recommended package|response))\b[^\n:]*:\*{0,2}\s*\n+",
                cleaned,
                flags=re.IGNORECASE,
            )
        )
        if matches:
            body = cleaned[matches[-1].end():]
        else:
            alt = re.search(
                r"\n+(?=(?:Based on your|According to your|For your usage|Hello|Hi\b|Thank you|بناءً على|وفقاً لـ|أهلاً|مرحباً))",
                cleaned,
                flags=re.IGNORECASE,
            )
            body = cleaned[alt.end():] if alt else cleaned

        end_marker = re.search(
            r"\n+(?:\d+\.\s*)?\*{0,2}(?:Check against|Final check|Verification|Output Generation|Self-Correction)[^\n:]*:\*{0,2}",
            body,
            flags=re.IGNORECASE,
        )
        cleaned = body[:end_marker.start()].strip() if end_marker else body.strip()

    cleaned = cleaned.replace("<think>", "").replace("</think>", "").strip()

    # 3. Secondary secret & HTML scrub
    cleaned = redact_secrets(cleaned)
    cleaned = sanitize_raw_html(cleaned)

    # 4. Clean customer text formatting
    cleaned = clean_customer_text(cleaned)

    return cleaned

