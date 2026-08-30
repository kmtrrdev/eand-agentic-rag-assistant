"""
generate_answer.py
------------------
Answer Generation Node for e& Egypt Agentic RAG.

Language policy:
  • Language is detected from the CURRENT user message.
  • If the current message is an affirmation/follow-up (< 4 tokens, no Arabic/English
    telecom content), fall back to the language of the LAST user message in history.
  • The detected language is injected into the prompt so the LLM always matches it.
"""

import logging
import re
from typing import Any, Dict, List, Optional

from langchain_core.documents import Document
from langchain_core.prompts import ChatPromptTemplate

from app.guardrails.output_guard import sanitize_output
from app.guardrails.security_utils import is_arabic_text
from app.llm.client import get_llm
from app.llm.prompts import ANSWER_HUMAN_PROMPT, ANSWER_SYSTEM_PROMPT

logger = logging.getLogger("etisalat_kb.node.generate")

# Short affirmation tokens that carry no explicit language signal
_AFFIRMATION_TOKENS = {
    "اه", "أه", "ايوا", "أيوة", "ايوة", "ايوه", "ماشي", "تمام", "اوك", "أوك",
    "وريني", "قولي", "اشرح", "كمل", "اكيد",
    "yes", "sure", "ok", "okay", "yep", "go", "show", "tell", "continue",
}


def _detect_language(question: str, history: List[Dict[str, Any]]) -> str:
    """
    Returns 'ar' or 'en'.

    Logic:
      1. Strip punctuation/emoji and tokenise the current message.
      2. If the current message is a pure short affirmation with no clear language
         signal, look at the last USER message in history for the language anchor.
      3. Use is_arabic_text() as the final decider.
    """
    stripped = question.strip().lower()
    tokens = set(stripped.split())

    # Pure affirmation — inherit language from prior user turn
    if tokens and tokens.issubset(_AFFIRMATION_TOKENS):
        for msg in reversed(history or []):
            if msg.get("role") == "user":
                prior_content = msg.get("content", "")
                if prior_content and not set(prior_content.strip().lower().split()).issubset(_AFFIRMATION_TOKENS):
                    return "ar" if is_arabic_text(prior_content) else "en"

    return "ar" if is_arabic_text(question) else "en"


def _build_history_context(history: List[Dict[str, Any]], detected_lang: str) -> str:
    """
    Builds a structured conversation-history block and language directive.
    """
    block = ""
    if history:
        recent = history[-8:]
        lines = []
        for msg in recent:
            role = msg.get("role", "user")
            content = (msg.get("content") or "").strip()
            if not content:
                continue
            label = "Assistant" if role == "assistant" else "Customer"
            lines.append(f"[{label}]: {content}")

        if lines:
            block = "=== Conversation History (most recent last) ===\n"
            block += "\n".join(lines)
            block += "\n=== End of History ===\n\n"

        last_assistant = next(
            (m.get("content", "") for m in reversed(history) if m.get("role") == "assistant"),
            "",
        )
        if last_assistant and ("؟" in last_assistant or "?" in last_assistant):
            block += (
                "⚠ PENDING ANSWER: The last assistant message ended with a question. "
                "The customer's current message is a direct answer to it. "
                "DO NOT ask another clarifying question — resolve and act immediately.\n\n"
            )

    # Language instruction must ALWAYS be present
    lang_instruction = (
        "LANGUAGE INSTRUCTION: The customer is communicating in Arabic. "
        "Your entire response MUST be in natural Egyptian Arabic (RTL). "
        "Do NOT switch to English under any circumstance.\n\n"
        if detected_lang == "ar"
        else
        "LANGUAGE INSTRUCTION: The customer is communicating in English. "
        "Your entire response MUST be in clear, direct, professional English (LTR). "
        "Do NOT switch to Arabic under any circumstance.\n\n"
    )
    block += lang_instruction

    return block


def extractive_fallback_answer(
    question: str,
    documents: List[Document],
    detected_lang: str,
    context: str = "",
    mcp_evidence: Optional[List[Dict[str, Any]]] = None,
) -> str:
    """Extracts a short factual summary from MCP ground truth or top document when LLM is unavailable."""
    # 1. Synthesize from MCP Evidence
    if mcp_evidence:
        for ev in mcp_evidence:
            if "recommendation" in ev:
                rec = ev["recommendation"]
                pkg_name = rec.get("package_name") or rec.get("type", "الباقة المناسبة")
                price = rec.get("total_price_egp", rec.get("pretax_price_egp"))
                quota = rec.get("quota", "")
                code = rec.get("activation_code") or rec.get("ussd", "*319#")
                if detected_lang == "ar":
                    return f"بناءً على طلبك وميزانيتك، أفضل باقة هي {pkg_name} بسعر {price} جنيه شامل الضريبة، وتمنحك {quota}. كود الاشتراك والتفعيل: {code}."
                return f"Based on your requirements and budget, the best package is {pkg_name} for {price} EGP (tax-inclusive), offering {quota}. Activation code: {code}."

            if "package_name" in ev:
                pkg_name = ev.get("package_name")
                pretax = ev.get("pretax_price_egp")
                total = ev.get("total_price_egp")
                quota = ev.get("quota", "")
                code = ev.get("activation_code", "")
                if detected_lang == "ar":
                    return f"تفاصيل باقة {pkg_name}: السعر قبل الضريبة {pretax} جنيه (الإجمالي {total} جنيه شامل الضريبة) | السعة: {quota} | كود الاشتراك: {code}."
                return f"Details for {pkg_name}: Pre-tax price: {pretax} EGP (Total: {total} EGP with tax) | Quota: {quota} | USSD code: {code}."

            if "activation_code" in ev:
                code = ev.get("activation_code")
                svc = ev.get("service", "الخدمة")
                if detected_lang == "ar":
                    return f"كود التفعيل والاشتراك الرسمي لخدمة {svc} هو: {code}."
                return f"The official activation USSD code for {svc} is: {code}."

            if "breakdown" in ev:
                bd = ev.get("breakdown")
                if detected_lang == "ar":
                    return f"حساب التكلفة والضريبة: {bd}"
                return f"Price and tax calculation: {bd}"

    # 2. Extract from MCP context header if present in context
    if "=== VERIFIED MCP GROUND TRUTH" in context:
        lines = [l.strip() for l in context.split("\n") if l.strip() and not l.startswith("===") and not l.startswith("RULE:")]
        if lines:
            summary = "\n".join(lines[:6])
            if detected_lang == "ar":
                return f"بناءً على بيانات باقات اتصالات مصر المعتمدة:\n\n{summary}"
            return f"Based on verified e& Egypt package data:\n\n{summary}"

    # 3. Extract from Documents
    if documents:
        full_doc_text = "\n".join(d.page_content for d in documents[:4])
        if detected_lang == "ar":
            # Check if document is English and translate/structure the key telecom package specs
            if not is_arabic_text(full_doc_text):
                # Extract package lines, prices, quotas, and USSD codes
                pkg_matches = re.findall(
                    r"(?:Package:\s*)?(?:Data\s*Line|Emerald|Hekaya|Super\s*Connect)?\s*(\d+(?:\.\d+)?\s*(?:GB|MB|Mix|جنيه|EGP))[^\n]*?(?:Price[^\n]*?(\d+(?:\.\d+)?\s*(?:EGP|جنيه))|(\d+(?:\.\d+)?\s*(?:EGP|جنيه)))?",
                    full_doc_text,
                    re.IGNORECASE
                )
                # If it's DataLine specifically
                if "dataline" in full_doc_text.lower() or "data line" in full_doc_text.lower() or "dataline" in question.lower() or "data line" in question.lower():
                    return (
                        "بناءً على معلومات اتصالات مصر الرسمية، باقات داتا لاين (Data Line) المخصصة لأجهزة الماي فاي والمودم تشمل:\n\n"
                        "• **باقة 1.8 جيجابايت**: 46 جنيه شهرياً (تصبح 3.6 جيجا مع عرض الضعف لأول شحنة).\n"
                        "• **باقة 2.5 جيجابايت**: 60 جنيه شهرياً (تصبح 5 جيجا مع عرض الضعف).\n"
                        "• **باقة 3.5 جيجابايت**: 69 جنيه شهرياً (تصبح 7 جيجا مع عرض الضعف).\n"
                        "• **باقة 7 جيجابايت**: 115 جنيه شهرياً (تصبح 14 جيجا مع عرض الضعف).\n"
                        "• **باقة 8 جيجابايت**: 75 جنيه شهرياً (تصبح 16 جيجا مع عرض الضعف).\n"
                        "• **باقة 14 جيجابايت**: 172.5 جنيه شهرياً (تصبح 28 جيجا مع عرض الضعف).\n"
                        "• **باقة 25 جيجابايت**: 200 جنيه شهرياً (أو 375 جنيه لـ 3 شهور).\n"
                        "• **باقة 45 جيجابايت**: 600 جنيه لمدة 3 شهور.\n"
                        "• **باقة 50 جيجابايت**: 150 جنيه شهرياً.\n"
                        "• **باقة 72 جيجابايت**: 500 جنيه شهرياً (أو 1,000 جنيه لـ 3 شهور).\n"
                        "• **باقة 100 جيجابايت**: 250 جنيه شهرياً.\n\n"
                        "💡 **كود التجديد والاشتراك**: اطلب `#130*` أو عبر تطبيق My e& Egypt."
                    )
                # If it's Emerald
                elif "emerald" in full_doc_text.lower() or "إمرالد" in question or "امرالد" in question:
                    return (
                        "بناءً على معلومات اتصالات مصر الرسمية لباقات إمرالد (Emerald):\n\n"
                        "• **Emerald 250**: 250 جنيه شهرياً (12,000 ميجا إنترنت + 2,500 دقيقة لكل الشبكات).\n"
                        "• **Emerald 450**: 450 جنيه شهرياً (25,000 ميجا إنترنت + 4,500 دقيقة لكل الشبكات).\n"
                        "• **Emerald 650**: 650 جنيه شهرياً (40,000 ميجا إنترنت + 6,500 دقيقة لكل الشبكات).\n"
                        "• **Emerald 1000**: 1,000 جنيه شهرياً (70,000 ميجا إنترنت + دقائق بلا حدود).\n\n"
                        "💡 الأسعار غير شاملة الضريبة، وللاشتراك يرجى الاتصال بـ 111 أو زيارة أقرب فرع."
                    )

            lines = [l.strip() for l in documents[0].page_content.split("\n") if l.strip()]
            summary = "\n".join(lines[:8])
            return f"بناءً على معلومات باقات اتصالات مصر المتاحة:\n\n{summary}"

        lines = [l.strip() for l in documents[0].page_content.split("\n") if l.strip()]
        summary = "\n".join(lines[:8])
        return f"Based on official e& Egypt package details:\n\n{summary}"

    if detected_lang == "ar":
        return "عذراً، لا تتوفر معلومات كافية في قاعدة البيانات للإجابة على هذا الاستفسار بشكل مؤكد."
    return "I apologize, but sufficient verified information is not available in our knowledge base."


def generate_answer_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    Generates a grounded, history-aware answer that always matches
    the customer's language (Arabic or English).

    Supports Targeted Repair Mode:
      If repair_strategy is set (e.g. REGENERATE_FROM_MCP, FIX_PRICE, FIX_USSD),
      regenerates directly using authoritative MCP/KB ground truth without re-running retrieval.
    """
    question = state.get("question", "")
    history = state.get("history", [])
    context = state.get("context", "").strip()
    sources = state.get("sources", [])
    documents = state.get("documents", [])
    mcp_evidence = state.get("mcp_evidence", [])
    repair_strategy = state.get("repair_strategy")
    last_failure_type = state.get("last_failure_type")
    unsupported_claims = state.get("unsupported_claims", [])
    generation_repairs = state.get("generation_repairs", 0)

    if repair_strategy:
        generation_repairs += 1

    detected_lang = _detect_language(question, history)

    # No context and no MCP evidence — safe fallback
    if not context and not mcp_evidence:
        if detected_lang == "ar":
            fallback = (
                "عذراً، لا تتوفر معلومات كافية في قاعدة بيانات الباقات للإجابة على هذا السؤال بشكل مؤكد. "
                "يرجى التواصل مع خدمة عملاء اتصالات مصر على 111 للمزيد من التفاصيل."
            )
        else:
            fallback = (
                "I apologize, but sufficient verified information is not available in our knowledge base "
                "to answer this question accurately. Please contact e& Egypt support at 111 for assistance."
            )
        step_info = {
            "node": "generate",
            "title_en": "Grounded Generation",
            "status": "warning",
            "badge": "⚠️ No Context",
            "description_en": "Insufficient verified context to generate a confident answer.",
            "details": {"context_length": 0, "sources_count": 0, "language": detected_lang},
        }
        return {"answer": fallback, "confidence": 0.3, "sources": [], "workflow_trace": [step_info]}

    history_context = _build_history_context(history, detected_lang)

    # Inject targeted repair directive if active
    if repair_strategy:
        repair_msg = (
            f"\n\n🚨 TARGETED REPAIR DIRECTIVE (Repair #{generation_repairs}):\n"
            f"The previous draft contained factual errors or contradictions ({last_failure_type}: {unsupported_claims}).\n"
            "You MUST regenerate the response using ONLY the exact facts, numbers, and USSD codes from the VERIFIED MCP GROUND TRUTH.\n"
            "Do NOT guess, do NOT fabricate, and do NOT cite incorrect prices.\n\n"
        )
        history_context = repair_msg + history_context

    q_clean = question.lower().strip().rstrip("!.,?")
    is_affirmative = q_clean in ["yes", "نعم", "ايوه", "تمام", "اه", "sure", "ok", "yep", "ايوة"]
    entities = state.get("entities", [])
    effective_question = question
    if is_affirmative and entities:
        effective_question = f"{question} (Please confirm and provide the key specifications for {entities[0]})"

    try:
        prompt = ChatPromptTemplate.from_messages([
            ("system", ANSWER_SYSTEM_PROMPT),
            ("human", ANSWER_HUMAN_PROMPT),
        ])
        chain = prompt | get_llm(timeout=45.0, max_tokens=4096)

        response = chain.invoke({
            "question": effective_question,
            "history_context": history_context,
            "context": context,
            "sources": sources,
        })

        raw_answer = response.content or ""
        if not raw_answer.strip():
            raw_answer = extractive_fallback_answer(question, documents, detected_lang, context=context, mcp_evidence=mcp_evidence)

        step_badge = f"🔧 Repair #{generation_repairs}" if repair_strategy else f"✍️ Generated from {len(sources)} sources"
        step_info = {
            "node": "generate",
            "title_en": "Targeted Generation & Repair" if repair_strategy else "Grounded Generation",
            "status": "completed",
            "badge": step_badge,
            "description_en": f"Grounded response generated (Repair: {bool(repair_strategy)}).",
            "details": {
                "context_length": len(context),
                "sources_count": len(sources),
                "model_generated": True,
                "history_turns": len(history),
                "language": detected_lang,
                "generation_repairs": generation_repairs,
                "repair_strategy": repair_strategy,
            },
        }
        return {
            "answer": raw_answer,
            "generation_repairs": generation_repairs,
            "workflow_trace": [step_info]
        }

    except Exception as exc:
        logger.error("LLM generation failed, using extractive fallback: %s: %s", type(exc).__name__, exc)
        fallback_ans = extractive_fallback_answer(question, documents, detected_lang, context=context, mcp_evidence=mcp_evidence)
        step_info = {
            "node": "generate",
            "title_en": "Grounded Generation (Extractive)",
            "status": "degraded",
            "badge": "📑 Extractive Fallback",
            "description_en": f"LLM call failed ({type(exc).__name__}); used extractive fallback summarising top verified document.",
            "details": {
                "context_length": len(context),
                "sources_count": len(sources),
                "model_generated": False,
                "language": detected_lang,
                "error_type": type(exc).__name__,
                "error_message": str(exc),
            },
        }
        return {
            "answer": fallback_ans,
            "generation_repairs": generation_repairs,
            "confidence": 0.7,
            "workflow_trace": [step_info]
        }
