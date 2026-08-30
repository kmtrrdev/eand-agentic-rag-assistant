"""
app/agent/text_signals.py
--------------------------
Shared deterministic text-classification helpers (greeting/thanks detection,
out-of-scope and unsupported-service term lists) used by understand_query_node.

These used to live in app/agent/nodes/intent_node.py, a graph node that was
registered but never wired into any edge — it had zero routing paths in or out
of it, so its LLM-classification machinery was dead code. understand_query_node
already re-implements greeting/scope classification as its own fast path and was
the only real consumer of these specific helpers, so they were extracted here and
the orphaned node was deleted.
"""
import re
from typing import Optional

GREETING_PATTERNS = [
    # English greetings & wellbeing inquiries (hi, hello, how are you, how are u, etc.)
    r"^(?:hi|hello|hey|hola|welcome|good\s+morning|good\s+evening|good\s+afternoon|howdy|sup|what'?s\s+up|whats\s+up)(?:\s+there)?[\s!.,?]*$",
    r"^(?:how\s+(?:are\s+you|are\s+u|r\s+u|are\s+things|are\s+ya|is\s+it\s+going|is\s+everything|do\s+you\s+do|have\s+you\s+been))(?:\s+doing)?(?:\s+today)?[\s!.,?]*$",
    r"^(?:أهلاً|اهلا|أهلا|مرحبا|مرحباً|هاي|هلا|هلو|سلام|السلام\s+عليكم|سلام\s+عليكم|صباح\s+الخير|مساء\s+الخير)[\s!.,؟]*$",
    r"^(?:ازيك|إزيك|عامل\s+ايه|عاملين\s+ايه|ازي\s+الحال|ازاي\s+الحال|اخبارك|إخبارك|أخبارك|شخبارك|ازيك\s+يا\s+بوت|كيفك|كيف\s+الحال|كيف\s+حالك)[\s!.,؟]*$",
    r"^(?:شكرا|شكراً|تسلم|ألف\s+شكر|مشكور)[\s!.,؟]*$",
    r"^(?:السلام\s+عليكم\s+ورحمة\s+الله(?:\s+وبركاته)?)[\s!.,؟]*$",
    r"^(?:وعليكم\s+السلام(?:\s+ورحمة\s+الله(?:\s+وبركاته)?)?)[\s!.,؟]*$",
    r"^(?:صباح\s+(?:النور|الفل|الورد|الخير|الجمال)|صباحو)(?:\s+يا\s+(?:فندم|باشا|غالي|سيدي))?[\s!.,؟]*$",
    r"^(?:مساء\s+(?:النور|الفل|الورد|الخير|الفل\s+والياسمين))(?:\s+يا\s+(?:فندم|باشا|غالي|سيدي))?[\s!.,؟]*$",
    r"^(?:ازيك\s+عامل\s+ايه|اخبارك\s+ايه|ازاي\s+حضرتك|ازي\s+حضرتك|ازيك\s+يا\s+غالي)[\s!.,؟]*$",
    r"^(?:شكرا\s+جزيلا|شكراً\s+جزيلاً|تسلم\s+ايدك)[\s!.,؟]*$",
    r"^(?:thanks\s+a\s+lot|thank\s+you\s+so\s+much)[\s!.,?]*$",
    r"^(?:مع\s+السلامة|باي|goodbye|have\s+a\s+nice\s+day)[\s!.,?]*$",
    r"^(?:أهلاً\s+وسهلاً\s+بك|اهلا\s+وسهلا\s+بك)[\s!.,؟]*$",
]

THANKS_PATTERNS = [
    # Pure thanks only — NOT ok/okay (those are continuations)
    r"^(?:thanks|thank\s+you|thx|ty)[\s!.,?]*$",
    r"^(?:شكرا|شكراً|تسلم|ألف\s+شكر|مشكور|شكرا\s+جزيلا|شكراً\s+جزيلاً|تسلم\s+ايدك)[\s!.,؟]*$",
    r"^(?:thanks\s+a\s+lot|thank\s+you\s+so\s+much)[\s!.,?]*$",
]

OUT_OF_SCOPE_TERMS = [
    "messi", "ronaldo", "football", "world cup", "weather", "cooking", "recipe",
    "python code", "tic-tac-toe", "javascript", "game", "ميسي", "رونالدو", "كورة",
    "مباراة", "مكرونة", "بشاميل", "طبخ", "كود بايثون", "برمجة", "لعبة", "طقس", "عاصمة"
]

UNSUPPORTED_SERVICE_TERMS = [
    "corporate", "enterprise", "شركات", "خط شركة", "خطوط شركات", "نقل ملكية",
    "sim swap", "بدل فاقد", "بدل تالف", "استبدال شريحة", "تغيير شريحة",
    "نزاع فواتير", "dispute", "فاتورة الشركات", "تحويل من شركات"
]

_EMOJI_STRIP_RE = re.compile(r"[\U00010000-\U0010ffff]|[🌀-🧿]|[🨀-🫿]|[👋🌹❤️✨👍🙏]")


def is_greeting(text: Optional[str]) -> bool:
    if not text:
        return False
    clean = _EMOJI_STRIP_RE.sub("", text).strip().lower()
    return any(re.search(pat, clean, re.IGNORECASE) for pat in GREETING_PATTERNS)


def is_pure_thanks(text: Optional[str]) -> bool:
    if not text:
        return False
    clean = text.strip().lower()
    return any(re.search(pat, clean, re.IGNORECASE) for pat in THANKS_PATTERNS)
