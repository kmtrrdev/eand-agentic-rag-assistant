from typing import Any, Dict
from app.guardrails.output_guard import sanitize_output


def output_guard_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    Final node in the graph: applies security sanitization, secret redaction,
    and text cleanup on the final generated answer.
    """
    answer = state.get("answer", "")
    sanitized = sanitize_output(answer)

    step_info = {
        "node": "output_guard",
        "title_ar": "حارس المخرجات والتنقيح النهائي",
        "title_en": "Output Guardrail & Sanitization",
        "status": "completed",
        "badge": "🔒 تم الفحص والتنقيح",
        "description_ar": "تم فحص الرد النهائي للتأكد من خلوه من أي وسوم داخلية أو بيانات غير مصرح بها وتنسيقه للمستخدم.",
        "description_en": "Verified final response sanitization, stripped internal tokens, and formatted output.",
        "details": {
            "sanitized": True,
            "output_length": len(sanitized),
        },
    }

    return {
        "answer": sanitized,
        "sanitized_answer": sanitized,
        "final_answer": sanitized,
        "workflow_trace": [step_info],
    }

