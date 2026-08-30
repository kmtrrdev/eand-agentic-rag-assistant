"""
app/agent/nodes/rewrite_query.py
--------------------------------
Rewrites ambiguous or poorly-retrieving queries to improve hybrid search recall.
Enforces entity and constraint preservation.
"""

import logging
from typing import Any, Dict, List, Optional
from langchain_core.prompts import ChatPromptTemplate

from app.llm.client import get_llm
from app.llm.prompts import QUERY_REWRITE_PROMPT

logger = logging.getLogger("etisalat_kb.node.rewrite")


def _build_history_summary(history: Optional[List[Dict[str, str]]]) -> str:
    if not history:
        return "No prior conversation."
    recent = history[-4:]
    parts = [
        f"{'A' if m.get('role') == 'assistant' else 'U'}: {(m.get('content') or '')[:100]}"
        for m in recent if m.get("content")
    ]
    return " | ".join(parts) if parts else "No prior conversation."


def rewrite_query_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    Targeted Query Rewriting Node:
    - Increments rewrite_attempts.
    - Preserves package entities, numeric prices, services, and budget constraints.
    - Detects identical rewrites to prevent repeated dead-end loops.
    """
    question = state.get("question", "")
    category = state.get("category", "general")
    service = state.get("service", "general")
    sub_track = state.get("sub_track") or "null"
    budget_egp = state.get("budget_egp") or "not specified"
    entities = state.get("entities", [])
    history = state.get("history", [])
    rewrite_attempts = state.get("rewrite_attempts", 0) + 1

    history_summary = _build_history_summary(history)

    rewritten = question
    rewrite_error: Optional[str] = None
    try:
        prompt = ChatPromptTemplate.from_template(QUERY_REWRITE_PROMPT)
        chain = prompt | get_llm(timeout=5.0, max_tokens=150)

        response = chain.invoke({
            "question": question,
            "category": category,
            "service": service,
            "sub_track": sub_track,
            "budget_egp": budget_egp,
            "history_summary": history_summary,
        })

        res_text = (response.content or "").strip()
        res_text = res_text.replace('"', '').replace("'", "").strip()
        if res_text:
            rewritten = res_text
            # Safety check: Ensure critical entity names are not lost in rewrite
            for ent in entities:
                if ent.lower() not in rewritten.lower():
                    rewritten = f"{ent} {rewritten}"
    except Exception as exc:
        rewrite_error = f"{type(exc).__name__}: {exc}"
        logger.warning("Query rewrite LLM call failed, falling back to original question: %s", rewrite_error)
        rewritten = question

    # Progress detection: did rewrite change the query?
    is_identical = (rewritten.strip() == question.strip())

    step_info = {
        "node": "rewrite",
        "title_ar": "إعادة صياغة الاستعلام المستهدفة",
        "title_en": "Targeted Query Rewriting",
        "status": "completed" if rewrite_error is None else "degraded",
        "badge": f"🔁 محاولة {rewrite_attempts}",
        "description_ar": f"إعادة صياغة السؤال مع الحفاظ على الكيانات والأرقام (محاولة {rewrite_attempts}).",
        "description_en": f"Targeted query rewrite preserving telecom entities (Attempt {rewrite_attempts}).",
        "details": {
            "original_query": question,
            "rewritten_query": rewritten,
            "service": service,
            "sub_track": sub_track,
            "rewrite_attempts": rewrite_attempts,
            "is_identical": is_identical,
            **({"error": rewrite_error} if rewrite_error else {}),
        },
    }

    return {
        "rewritten_query": rewritten,
        "rewrite_attempts": rewrite_attempts,
        "workflow_trace": [step_info],
    }

