import json
import logging
import re
from typing import Any, Dict, List, Tuple

from app.agent.lang import pick
from app.agent.state import AgentState
from app.agent.trace import elapsed_ms, now, step
from app.config import settings
from app.llm.client import get_chat_model, local_llm_slot
from app.llm.prompts import AGENTIC_GENERATE_SYSTEM_PROMPT, GENERATE_SYSTEM_PROMPT, LOCAL_GENERATE_SYSTEM_PROMPT

logger = logging.getLogger("app.agent.nodes.generate_node")

_MAX_AGENT_TOOL_ITERATIONS = 3

NO_INFO_AR = "معنديش معلومة مؤكدة عن ده دلوقتي. تقدر تتصل بـ 111 أو تزور أقرب فرع اتصالات، أو توضّح سؤالك أكتر؟"
NO_INFO_EN = (
    "I don't have verified information on that right now. You can call 111 or visit an "
    "e& Egypt store, or could you clarify your question?"
)


def _facts_block(tool_evidence) -> str:
    if not tool_evidence:
        return "(no deterministic tool results)"
    clean_items = []
    for e in tool_evidence:
        if not isinstance(e, dict):
            continue
        # If it's a full family with many tiers, condense it so it doesn't explode prompt tokens
        if "tiers" in e and isinstance(e["tiers"], list):
            e_copy = dict(e)
            tiers = e_copy["tiers"]
            e_copy["tiers"] = [
                {
                    "name": t.get("name_en") or t.get("name_ar"),
                    "price_egp": t.get("price_egp"),
                    "quota": t.get("quota_mb") or t.get("mix_units") or t.get("description_en"),
                    "code": t.get("activation_code"),
                }
                for t in tiers[:3]
            ]
            clean_items.append(json.dumps(e_copy, ensure_ascii=False))
        else:
            clean_items.append(json.dumps(e, ensure_ascii=False))
    return "\n".join(clean_items)


def _extractive_fallback(state: AgentState) -> str:
    """Zero-crash fallback if the LLM call itself fails: answer directly from
    tool facts already on hand, or an honest 'don't know' otherwise."""
    language = state.get("language", "en")
    q_lower = (state.get("question") or "").lower()

    # Comparison intent fallback
    if state.get("intent") == "comparison" or "compare" in q_lower or "قارن" in q_lower:
        if ("mixat" in q_lower or "مكسات" in q_lower) and ("internet" in q_lower or "انترنت" in q_lower or "إنترنت" in q_lower):
            if language == "ar":
                return (
                    "### 📊 مقارنة بين باقات حكاية مكسات وحكاية إنترنت:\n\n"
                    "1. 📱 **حكاية مكسات (Hekaya Mixat):**\n"
                    "- باقات شهرية بنظام **المكسات الموحدة** (تصلح للمكالمات والإنترنت معاً).\n"
                    "- المكس = دقيقة لاتصالات أو 2 ميجابايت لمواقع التواصل الاجتماعي أو 5 مكس لدقيقة للشبكات الأخرى.\n"
                    "- تدعم **مشاركة خطوط العائلة** والأرقام المفضلة.\n"
                    "- الأنسب لمن يبحث عن توازن بين المكالمات والإنترنت.\n\n"
                    "2. 🌐 **حكاية إنترنت (Hekaya Internet):**\n"
                    "- باقات شهرية مخصصة **للإنترنت الضخم** (من 1,250 ميجا حتى 70,000 ميجا).\n"
                    "- تمنح 300 وحدة مكالمات واشتراكات ترفيهية مجانية (شاهد VIP، تويست، ستارزبلاي).\n"
                    "- الميجابايتس المتبقية تتحول لكاش في محفظة e& money.\n"
                    "- الأنسب للمشاهدة والاستخدام الكثيف للداتا."
                )
            else:
                return (
                    "### 📊 Comparison: Hekaya Mixat vs Hekaya Internet\n\n"
                    "1. 📱 **Hekaya Mixat:**\n"
                    "- Monthly bundles using flexible **unified Mix units** for both calls and data.\n"
                    "- 1 Mix = 1 min to e&, 5 Mix = 1 min to other networks, 1 Mix = 2 MB social.\n"
                    "- Includes **family line sharing** and favorite numbers.\n"
                    "- Best for customers who need a balanced mix of voice calls and mobile internet.\n\n"
                    "2. 🌐 **Hekaya Internet:**\n"
                    "- Data-heavy bundles with high allowances (from 1,250 MB up to 70,000 MB).\n"
                    "- Includes 300 call units plus free streaming subscriptions (Shahid VIP, Twist, Starzplay).\n"
                    "- Unused megabytes convert to cash back on e& money.\n"
                    "- Best for heavy internet users and video streaming."
                )

        packages = [e for e in state.get("tool_evidence", []) if e.get("found") and ("description_en" in e or "description_ar" in e)]
        if len(packages) >= 2:
            lines = []
            if language == "ar":
                lines.append("### 📊 مقارنة سريعة:")
                for p in packages:
                    name = p.get("package_name_ar") or p.get("package_name")
                    desc = p.get("description_ar") or p.get("description_en")
                    price = p.get("price_egp")
                    lines.append(f"- **{name}** ({price} جنيه): {desc}")
            else:
                lines.append("### 📊 Quick Comparison:")
                for p in packages:
                    name = p.get("package_name")
                    desc = p.get("description_en") or p.get("description_ar")
                    price = p.get("price_egp")
                    lines.append(f"- **{name}** ({price} EGP): {desc}")
            return "\n".join(lines)

    for evidence in state.get("tool_evidence", []):
        if not evidence.get("found"):
            continue
        if "recommendations" in evidence and evidence.get("recommendations"):
            recs = evidence["recommendations"]
            if language == "ar":
                res = ["### 📊 الباقات المقترحة:\n"]
                for r in recs:
                    name = r.get("name_ar") or r.get("name_en")
                    price = r.get("price_egp")
                    total = r.get("total_egp", price)
                    quota = r.get("quota_label_ar") or r.get("quota_label_en") or ""
                    code = r.get("activation_code") or r.get("ussd_code") or ""
                    res.append(f"- **{name}**: {price} جنيه (شامل الضريبة: {total} جنيه) | السعة: {quota} | كود الاشتراك: `{code}`")
                return "\n".join(res)
            else:
                res = ["### 📊 Recommended Packages:\n"]
                for r in recs:
                    name = r.get("name_en")
                    price = r.get("price_egp")
                    total = r.get("total_egp", price)
                    quota = r.get("quota_label_en") or ""
                    code = r.get("activation_code") or r.get("ussd_code") or ""
                    res.append(f"- **{name}**: {price} EGP (Total with tax: {total} EGP) | Quota: {quota} | Activation: `{code}`")
                return "\n".join(res)
        if "breakdown" in evidence:
            return pick(language, evidence.get("explanation_ar", ""), evidence.get("explanation_en", ""))
        if "description_en" in evidence:
            return pick(language, evidence.get("description_ar", ""), evidence.get("description_en", ""))
        if "instructions" in evidence:
            return f"{evidence.get('activation_code', '')} — {evidence['instructions']}"
        if "tiers" in evidence and evidence.get("tiers"):
            tier_list = evidence["tiers"][:5]
            family_name = evidence.get("family_name_ar") if language == "ar" else evidence.get("family_name_en", "Family")
            if language == "ar":
                res = [f"### 📱 باقات {family_name}:"]
                for t in tier_list:
                    res.append(f"- **{t.get('name_ar', t.get('name_en'))}**: {t.get('price_egp')} جنيه — {t.get('description_ar', t.get('description_en'))}")
                return "\n".join(res)
            else:
                res = [f"### 📱 {family_name} Packages:"]
                for t in tier_list:
                    res.append(f"- **{t.get('name_en')}**: {t.get('price_egp')} EGP — {t.get('description_en')}")
                return "\n".join(res)
    return pick(language, NO_INFO_AR, NO_INFO_EN)


def _build_lang_directive(language: str) -> str:
    if language == "en":
        return (
            "⚠️ CRITICAL LANGUAGE REQUIREMENT:\n"
            "- The customer is currently communicating in ENGLISH.\n"
            "- You MUST write your ENTIRE response in ENGLISH (all headings, bullet labels, table headers, descriptions, and tips).\n"
            "- Even if earlier conversation turns or retrieved snippets are in Arabic, do NOT respond in Arabic. Translate or present all information strictly in English."
        )
    return (
        "⚠️ تعليمات اللغة:\n"
        "- استفسار العميل باللغة العربية.\n"
        "- يجب أن تكون إجابتك بالكامل باللغة العربية (باللهجة المصرية المعتادة لخدمة العملاء).\n"
        "- جميع العناوين، الجداول، والنقاط تكون باللغة العربية."
    )


def _agentic_generate(state: AgentState) -> Tuple[str, List[Dict[str, Any]], int]:
    """For the genuinely open-ended case (no exact tool/family match) — instead
    of one fixed retrieval pass, give the model a search_knowledge_base tool
    and let it decide whether the context it already has is enough, or it
    needs to search again with a different query, ReAct-style (bounded).

    This is the same search function app/mcp/server.py exposes over MCP for
    external clients; called directly in-process here to avoid a subprocess
    round trip on every customer request.
    """
    from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage
    from langchain_core.tools import tool

    from app.retrieval.hybrid_retriever import search as hybrid_search

    collected_sources: List[Dict[str, Any]] = []

    @tool
    def search_knowledge_base(query: str) -> str:
        """Search the e& Egypt package catalog. Use a focused query naming the
        specific package, family, or topic you need."""
        docs = hybrid_search(query)
        for doc in docs:
            m = dict(doc.get("metadata", {}))
            m["snippet"] = doc.get("content", "")
            # Ensure 'source' is always present so the frontend can display a real name
            if not m.get("source"):
                m["source"] = "e& Egypt Knowledge Base"
            collected_sources.append(m)
        return "\n\n---\n\n".join(d["content"] for d in docs) or "No results found for that query."

    language = state.get("language", "en")
    lang_directive = _build_lang_directive(language)
    seed = (
        f"{lang_directive}\n\n"
        f"Already retrieved context:\n{state.get('context') or '(none)'}\n\n"
        f"Customer question: {state.get('question', '')}\n\n"
        f"{lang_directive}"
    )
    messages: List[Any] = [SystemMessage(AGENTIC_GENERATE_SYSTEM_PROMPT), HumanMessage(seed)]

    with local_llm_slot():
        model = get_chat_model(temperature=0.1).bind_tools([search_knowledge_base])
        iterations = 0
        for iterations in range(1, _MAX_AGENT_TOOL_ITERATIONS + 1):
            response = model.invoke(messages)
            messages.append(response)
            tool_calls = getattr(response, "tool_calls", None) or []
            if not tool_calls:
                return response.content, collected_sources, iterations
            for call in tool_calls:
                result = search_knowledge_base.invoke(call["args"])
                messages.append(ToolMessage(content=result, tool_call_id=call["id"]))
        # Iteration budget spent — force a final answer without offering the tool again.
        final = get_chat_model(temperature=0.1).invoke(messages)
        final_text = final.content if hasattr(final, "content") else str(final)
        if "<think>" in final_text:
            final_text = re.sub(r"<think>[\s\S]*?</think>", "", final_text).strip()
            if "<think>" in final_text:
                final_text = re.sub(r"<think>[\s\S]*", "", final_text).strip()
        return final_text, collected_sources, iterations


def generate_node(state: AgentState) -> Dict[str, Any]:
    start = now()
    language = state.get("language", "en")
    lang_directive = _build_lang_directive(language)
    from app.llm.client import get_current_model_choice
    current_choice = get_current_model_choice()

    # Agentic iterative search only when context is genuinely missing for open-ended queries
    if (
        current_choice != "local"
        and state.get("strategy") == "RAG_ONLY"
        and not state.get("context")
        and not state.get("tool_evidence")
        and state.get("validation_result") != "REPAIR"
        and getattr(settings, "MCP_TOOLS_ENABLED", True)
        and not getattr(settings, "RAG_ONLY_MODE", False)
    ):
        try:
            answer, extra_sources, iterations = _agentic_generate(state)
            extra_context = [m.get("snippet", "") for m in extra_sources]
            merged_sources = list(state.get("sources") or [])
            merged_sources.extend({
                "source": m.get("source", ""), "category": m.get("category", ""),
                "product": m.get("product", ""), "snippet": m.get("snippet", ""),
            } for m in extra_sources)
            return {
                "answer": answer,
                "sources": merged_sources,
                "context": (state.get("context") or "") + ("\n\n---\n\n" + "\n\n---\n\n".join(extra_context) if extra_context else ""),
                "workflow_trace": [step(
                    "generate", "8. Grounded Generation", "٨. توليد الإجابة الصارمة",
                    description_en=f"Agentic: model made {iterations} decision pass(es), calling search_knowledge_base as needed.",
                    badge="Agentic", status="completed",
                    latency_ms=elapsed_ms(start),
                )],
            }
        except Exception:
            logger.exception("Agentic generation failed; falling through to standard fixed-context path.")

    raw_history = state.get("history") or []
    if current_choice == "local":
        history = raw_history[-2:]
        messages = [("system", LOCAL_GENERATE_SYSTEM_PROMPT)]
    else:
        history = raw_history[-settings.MAX_HISTORY_MESSAGES:]
        messages = [("system", GENERATE_SYSTEM_PROMPT)]
    for msg in history:
        role = "assistant" if msg.get("role") == "assistant" else "human"
        if msg.get("content"):
            messages.append((role, msg["content"]))

    is_lang_switch = state.get("is_lang_switch", False)
    lang_switch_user_q = state.get("lang_switch_user_q", "")
    target_lang = state.get("language", "en")
    target_lang_name = "ENGLISH" if target_lang == "en" else "ARABIC (Egyptian customer service dialect)"

    lang_switch_block = ""
    if is_lang_switch and lang_switch_user_q:
        lang_switch_block = (
            f"\n\n🚨 CUSTOMER REQUESTED LANGUAGE SWITCH:\n"
            f"- The customer asked to switch the language to {target_lang_name} (their message: '{state.get('question', '')}').\n"
            f"- You MUST provide the full, comprehensive answer to their preceding inquiry: '{lang_switch_user_q}' entirely in {target_lang_name}.\n"
            f"- Translate and re-explain the response (including reasons, comparisons, numbers, prices, quotas, codes, and taxes) based on the VERIFIED FACTS and RETRIEVED CONTEXT above.\n"
            f"- Maintain full fidelity to the previous discussion: DO NOT switch to unrelated packages or invent new products."
        )

    context_str = state.get("context") or ""
    if context_str:
        parts = [p.strip() for p in context_str.split("\n\n---\n\n") if p.strip()]
        if current_choice == "local":
            context_str = "\n\n---\n\n".join(parts[:2])
        elif state.get("strategy") in ("TOOL_EXACT", "TOOL_ACTIVATION", "TOOL_CALCULATION"):
            context_str = "\n\n---\n\n".join(parts[:4])

    # Include the customer's stated budget in every prompt turn so the model
    # can explain budget-based decisions (e.g. "why not Emerald?") without
    # needing to infer it from deep history context.
    budget_egp = state.get("budget_egp")
    budget_str = f"\nCustomer's stated budget: {budget_egp} EGP" if budget_egp is not None else ""
    evidence_items = state.get("tool_evidence", [])
    if current_choice == "local":
        if len(evidence_items) > 3:
            evidence_items = evidence_items[:3]
        if len(context_str) > 2500:
            context_str = context_str[:2500]

    user_block = (
        f"{lang_directive}\n\n"
        f"VERIFIED FACTS (from deterministic tools):\n{_facts_block(evidence_items)}\n\n"
        f"RETRIEVED CONTEXT (from knowledge base):\n{context_str or '(none)'}\n\n"
        f"Customer question: {state.get('question', '')}{budget_str}{lang_switch_block}\n\n"
        f"{lang_directive}"
    )

    if state.get("validation_result") == "REPAIR":
        details = state.get("validation_details", {})
        user_block += (
            "\n\nYour previous answer contained numbers not present in the facts above "
            f"(unsupported: {details}). Regenerate using ONLY the numbers in VERIFIED FACTS "
            "and RETRIEVED CONTEXT — if you're unsure of a number, say so instead of guessing."
        )

    messages.append(("human", user_block))

    try:
        with local_llm_slot():
            model = get_chat_model(temperature=0.1, reasoning_effort="minimal")
            response = model.invoke(messages)
        answer = response.content if hasattr(response, "content") else str(response)
        if "<think>" in answer:
            answer = re.sub(r"<think>[\s\S]*?</think>", "", answer).strip()
            if "<think>" in answer:
                answer = re.sub(r"<think>[\s\S]*", "", answer).strip()
        badge = "Done"
    except Exception:
        logger.exception("Primary generate LLM call failed; using extractive fallback.")
        answer = _extractive_fallback(state)
        badge = "Fallback"

    return {
        "answer": answer,
        "workflow_trace": [step(
            "generate", "8. Grounded Generation", "٨. توليد الإجابة الصارمة",
            description_en="Composed the final answer from verified facts and retrieved context.",
            badge=badge, status="completed",
            latency_ms=elapsed_ms(start),
        )],
    }
