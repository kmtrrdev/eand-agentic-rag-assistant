import html
import re


LIST_ITEM_RE = re.compile(r"<\s*li\b[^>]*>", re.IGNORECASE)
TAG_RE = re.compile(r"</?\s*[a-zA-Z][^>]*>")


def normalize_escaped_html(text: str) -> str:
    cleaned = str(text)

    for _ in range(3):
        previous = cleaned
        cleaned = html.unescape(cleaned)
        cleaned = re.sub(r"\\+([<>])", r"\1", cleaned)
        cleaned = re.sub(r"<\\+/", "</", cleaned)

        if cleaned == previous:
            break

    return cleaned


def clean_customer_text(text: str) -> str:
    """Return safe, customer-facing plain text without raw HTML tags."""
    if not text:
        return ""

    cleaned = normalize_escaped_html(text)
    cleaned = re.sub(r"<\s*br\s*/?\s*>", "\n", cleaned, flags=re.IGNORECASE)
    cleaned = LIST_ITEM_RE.sub("\n- ", cleaned)
    cleaned = re.sub(r"</\s*li\s*>", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"</?\s*(ul|ol)\b[^>]*>", "\n", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"</\s*(p|div|section|article|tr)\s*>", "\n", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"<\s*(p|div|section|article|tr)\b[^>]*>", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(
        r"</?\s*(strong|b|em|i|span|code|table|thead|tbody|th|td)\b[^>]*>",
        "",
        cleaned,
        flags=re.IGNORECASE,
    )
    cleaned = TAG_RE.sub("", cleaned)
    cleaned = re.sub(r"[ \t]+\n", "\n", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    cleaned = re.sub(r"[ \t]{2,}", " ", cleaned)

    return cleaned.strip()
