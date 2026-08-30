import re

# The regex pattern lists and redact_secrets()/sanitize_raw_html() that used to
# live here (SECRET_PATTERNS, PROMPT_INJECTION_PATTERNS, ARABIC_INJECTION_PATTERNS,
# SECRET_REQUEST_PATTERNS, SYSTEM_PROMPT_PATTERNS) were a near-duplicate of
# app/guardrails/garak_guard.py's pattern suites, scanned a second time on every
# request/response for no additional coverage. Removed; the few genuinely distinct
# patterns were merged into garak_guard.py's GARAK_MISC_PATTERNS instead. Only
# is_arabic_text() survives here since it's used broadly outside the guardrails
# module (language detection for greetings, answer generation, etc.), not just as
# a guardrail helper.


def is_arabic_text(text: str) -> bool:
    if not text:
        return False
    arabic_chars = re.findall(r"[؀-ۿݐ-ݿࢠ-ࣿﭐ-﷿ﹰ-﻿]", text)
    latin_chars = re.findall(r"[a-zA-Z]", text)
    return len(arabic_chars) > 0 and len(arabic_chars) >= len(latin_chars) * 0.3
