from typing import Any, Dict
from app.guardrails.input_guard import validate_input


def input_guard_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    First line of defense: validates user question against security policies
    (prompt injection, secret extraction, system prompt requests, oversized input).
    """
    question = state.get("question", "")
    result = validate_input(question)

    step_info = {
        "node": "input_guard",
        "title_ar": "حارس المدخلات والأمان",
        "title_en": "Input Guardrail",
        "status": "passed" if result.allowed else "blocked",
        "badge": "✅ آمن" if result.allowed else "🚫 محظور",
        "description_ar": "فحص السؤال والتأكد من خلوه من محاولات حقن الأوامر أو استخراج التعليمات السرية."
        if result.allowed
        else "تم رصد محاولة غير مصرح بها وحظر الطلب طبقاً لسياسات الأمان.",
        "description_en": "Validated query against prompt injection and security policies."
        if result.allowed
        else "Blocked request due to security policy violation.",
        "details": {
            "allowed": result.allowed,
            "category": getattr(result, "category", "safe"),
            "risk_level": "low" if result.allowed else "high",
        },
    }

    if not result.allowed:
        return {
            "guardrail_result": result.to_dict(),
            "answer": result.safe_message or "عذراً، لا يمكن معالجة هذا الطلب لأسباب أمنية.",
            "confidence": 1.0,
            "sources": [],
            "workflow_trace": [step_info],
        }

    return {
        "guardrail_result": result.to_dict(),
        "workflow_trace": [step_info],
    }

