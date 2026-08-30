from dataclasses import dataclass
from enum import Enum
from typing import Optional


class GuardrailCategory(str, Enum):
    SAFE = "SAFE"
    PROMPT_INJECTION = "PROMPT_INJECTION"
    SECRET_REQUEST = "SECRET_REQUEST"
    SYSTEM_PROMPT_REQUEST = "SYSTEM_PROMPT_REQUEST"
    OUT_OF_SCOPE = "OUT_OF_SCOPE"
    UNSUPPORTED_SERVICE = "UNSUPPORTED_SERVICE"
    MALICIOUS_INPUT = "MALICIOUS_INPUT"
    INVALID_INPUT = "INVALID_INPUT"


@dataclass
class GuardrailResult:
    allowed: bool
    category: GuardrailCategory
    reason: str
    safe_message: Optional[str] = None

    def to_dict(self):
        return {
            "allowed": self.allowed,
            "category": self.category.value,
            "reason": self.reason,
            "safe_message": self.safe_message,
        }
