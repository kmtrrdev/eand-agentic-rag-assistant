"""
Query rewrite: turns the raw customer message into the query retrieve_node
actually searches with — resolving pronouns/references via conversation
history and classify_node's resolved family/package, and bridging Arabic
<-> English vocabulary gaps between how customers ask and how the knowledge
base is written.

Only spends an LLM call where it actually earns its keep. For TOOL_EXACT /
TOOL_CALCULATION / TOOL_ACTIVATION / TOOL_RECOMMENDATION, a deterministic tool
already answers the question precisely and retrieval only adds supplementary
context (see tools_node) — a cheap anchor+question concatenation is enough
there. It's RAG_ONLY and TOOL_PLUS_RAG (family overviews, comparisons, and the
fully open-ended fallback) where retrieval quality *is* the answer quality,
which is exactly where a vague or single-language-biased query does the most
damage (e.g. an Arabic question about roaming coverage missing English-only
country-list content).
"""
import logging
from typing import Any, Dict

from app.agent.schemas import QueryRewriteResult
from app.agent.state import AgentState
from app.agent.trace import elapsed_ms, now, step
from app.llm.client import get_chat_model, local_llm_slot
from app.llm.prompts import QUERY_REWRITE_SYSTEM_PROMPT

logger = logging.getLogger("app.agent.nodes.query_rewrite_node")

_SMART_REWRITE_STRATEGIES = {"RAG_ONLY", "TOOL_PLUS_RAG"}


def _fallback_query(state: AgentState) -> str:
    """The same cheap heuristic used before this node existed: prefix the raw
    question with whatever specific package/family classify_node already
    resolved, so a pronoun-heavy follow-up still searches for the right
    thing even without the LLM rewrite.

    If no anchor is available from the current turn's classification (e.g. a
    follow-up like "طب كودها ايه؟" where classify_node resolved the package
    but strategy is TOOL_ACTIVATION so smart-rewrite is skipped), scan the
    conversation history to recover the last mentioned package name so the
    retrieval query still targets the right chunk.
    """
    question = state.get("question", "")
    category = state.get("category")
    device_type = state.get("device_type")
    anchor = state.get("package_name_raw") or state.get("service") or ""

    if category == "dataline" or (device_type and device_type in ("router", "mifi", "modem", "usb")):
        anchor = "DataLine MiFi Router داتا لاين"
    elif not anchor:
        history = (state.get("history") or [])[-6:]
        if history:
            history_text = "\n".join(
                f"{m.get('role')}: {m.get('content')}" for m in history
            )
            try:
                from app.agent.nodes.classify_node import _resolve_last_package_from_history
                resolved = _resolve_last_package_from_history(history_text)
                if resolved:
                    anchor = resolved.get("package_name_raw", "")
            except Exception:
                pass
    return f"{anchor} {question}".strip()


_BILINGUAL_BRIDGE_MAP = {
    "حكاية": "Hekaya",
    "مكس": "Mix",
    "مكسات": "Mixat",
    "كونكت": "Connect",
    "سوبر كونكت": "Super Connect",
    "أقوى كارت": "Aqwa Card",
    "اقوى كارت": "Aqwa Card",
    "أقوى": "Aqwa",
    "اقوى": "Aqwa",
    "كارت": "Card",
    "إمرالد": "Emerald",
    "ايميرالد": "Emerald",
    "داتا": "DataLine",
    "داتالاين": "DataLine",
    "راوتر": "Router MiFi",
    "ماي فاي": "MiFi",
    "مايفاي": "MiFi",
    "mifi": "MiFi DataLine Router",
    "تجوال": "Roaming",
    "سعر": "Price",
    "أسعار": "Prices",
    "اسعار": "Prices",
    "باقة": "Package Plan",
    "باقات": "Packages Plans",
    "دقايق": "Minutes Calls Voice",
    "دقائق": "Minutes Calls Voice",
    "دقيقة": "Minutes Calls Voice",
    "مكالمات": "Calls Minutes Voice",
    "صوت": "Voice Calls",
    "نت": "Internet Data MB GB",
    "انترنت": "Internet Data",
    "إنترنت": "Internet Data",
    "بيانات": "Data Internet",
    "جيجا": "GB Gigabyte",
    "ميجا": "MB Megabyte",
    "شحن": "Recharge Balance",
    "تجديد": "Renewal Renew",
    "فاتورة": "Postpaid Bill",
    "عائلة": "Family lines",
    "كود": "USSD Code",
    "تفعيل": "Activation Code",
    "ضريبة": "Tax Fee",
    "ريكومند": "Recommendation Best Plan",
    "رشح": "Recommendation Best Plan",
    # Follow-up / "Why not X?" queries — these need budget + recommendation context
    "ليه": "Why not reason budget recommendation comparison postpaid prepaid",
    "ليه مش": "Why not reason budget recommendation comparison postpaid",
    "ليه ما": "Why not reason budget recommendation comparison",
    "اشمعنى": "Why not reason difference budget comparison",
    "اشمعنا": "Why not reason difference budget comparison",
    "مش أحسن": "Why not better reason comparison budget",
    "مش احسن": "Why not better reason comparison budget",
}

_PRONOUN_TRIGGERS = {
    # Demonstratives & Pronouns
    "دي", "ده", "ديه", "دول", "دا", "هذه", "هذا", "هذول", "هؤلاء", "تلك", "ذلك",
    "هو", "هي", "هم", "هما", "هن",
    # Prepositions with attached pronouns
    "بينها", "بينهما", "بينهم", "بينه", "معاها", "معاه", "معاهم", "عنها", "عنه", "عنهم",
    "فيها", "فيه", "فيهم", "لها", "له", "ليهم", "بيها", "بيه", "بيهم", "منها", "منه", "منهم",
    "إياها", "اياها", "نفسها", "نفسه",
    # Relative / Alternatives
    "تانية", "تانيه", "ثانية", "أخرى", "اخرى", "الأولى", "الاولى", "السابقة", "السابق",
    "اللي فاتت", "اللي قبلها", "غيرها", "غيره",
    # Comparisons
    "قارن", "قارنها", "قارنهم", "مقارنة", "مقارنه", "الفرق", "أحسن ولا", "احسن ولا",
    "أفضل ولا", "افضل ولا", "مين أحسن", "مين احسن", "مين أفضل", "مين افضل", "أيهما", "ايهما",
    "أرخص ولا", "ارخص ولا", "أغلى ولا", "اغلى ولا", "ولا دي", "ولا ده",
    # Follow-ups
    "طب", "طيب", "طب هي", "طب هو", "طب سعرها", "طب كودها", "طب والضريبة", "طب والنت",
    "طب والمكالمات", "طب ورصيدها", "طب وباقي", "طب وبالنسبة", "وبالنسبة", "طب و", "كمان",
    # "Why not X?" follow-ups — implicitly reference a previous recommendation turn
    "ليه", "ليه مش", "ليه ما", "اشمعنى", "اشمعنا", "مش أحسن", "مش احسن",
    # English
    "it", "its", "that", "this", "these", "those", "them", "they", "which one",
    "the other", "previous", "earlier", "compare", "comparison", "difference", "vs", "versus",
    "better", "cheaper", "what about", "how about", "instead", "why not", "why isn't",
}


def _build_fast_bridge_query(question: str, state: AgentState) -> str:
    fallback = _fallback_query(state)
    q_lower = question.lower()
    bridge_terms = []
    for ar_term, en_term in _BILINGUAL_BRIDGE_MAP.items():
        if ar_term in q_lower:
            bridge_terms.append(en_term)

    # Contextual additions
    device_type = state.get("device_type")
    category = state.get("category")
    if category == "dataline" or (device_type and device_type in ("router", "mifi", "modem", "usb")):
        if "DataLine" not in bridge_terms:
            bridge_terms.append("DataLine MiFi Router USB Modem Internet Data SIM")
    else:
        usage_focus = state.get("usage_focus")
        if usage_focus == "minutes" and "Hekaya Mixat" not in bridge_terms:
            bridge_terms.append("Hekaya Mixat Voice Calls Minutes")
        elif usage_focus == "data" and "Hekaya Internet" not in bridge_terms:
            bridge_terms.append("Hekaya Internet Data")

    if bridge_terms:
        return f"{fallback} {' '.join(dict.fromkeys(bridge_terms))}".strip()
    return fallback


def query_rewrite_node(state: AgentState) -> Dict[str, Any]:
    start = now()
    strategy = state.get("strategy", "")
    question = state.get("question", "")
    effective_question = state.get("lang_switch_user_q") if state.get("is_lang_switch") else question
    history = (state.get("history") or [])[-6:]
    q_lower = effective_question.lower()

    has_pronoun = any(p in q_lower for p in _PRONOUN_TRIGGERS)
    is_comparison = state.get("intent") == "comparison" or any(
        k in q_lower for k in ("قارن", "مقارنة", "مقارنه", "الفرق", "compare", "vs")
    )
    has_history = bool(history)

    # In multi-turn conversations with pronouns, follow-up references, or comparison requests,
    # smart rewrite may run to resolve pronouns and bind context from history.
    needs_smart_rewrite = has_history and (has_pronoun or is_comparison)

    # FAST PATH (< 1ms):
    # 1. For deterministic tool strategies (TOOL_EXACT, TOOL_CALCULATION, TOOL_ACTIVATION, TOOL_RECOMMENDATION),
    #    tools_node is the definitive factual source; retrieval is purely supplementary.
    #    Bilingual term bridge is instantaneous (<1ms) and completely eliminates a 2s LLM bottleneck.
    from app.llm.client import get_current_model_choice
    current_choice = get_current_model_choice()
    if current_choice == "local" or strategy not in _SMART_REWRITE_STRATEGIES or not needs_smart_rewrite:
        fast_query = _build_fast_bridge_query(effective_question, state)
        return {
            "retrieval_query": fast_query,
            "workflow_trace": [step(
                "query_rewrite", "5b. Query Rewrite", "٥ب. إعادة صياغة الاستعلام",
                description_en="Applied fast bilingual term bridge without spending an LLM call.",
                badge="Fast Path", status="completed",
                details={"query": fast_query},
                latency_ms=elapsed_ms(start),
            )],
        }

    history_text = "\n".join(f"{m.get('role')}: {m.get('content')}" for m in history) or ""
    fallback_query = _fallback_query(state)
    entities_str = ", ".join(state.get("entities") or [])

    try:
        with local_llm_slot():
            model = get_chat_model(temperature=0.0, reasoning_effort="minimal")
            structured_model = model.with_structured_output(QueryRewriteResult)
            budget_context = f"\nCustomer's stated budget: {state.get('budget_egp')} EGP" if state.get('budget_egp') is not None else ""
            result: QueryRewriteResult = structured_model.invoke([
                ("system", QUERY_REWRITE_SYSTEM_PROMPT),
                ("human", (
                    f"Recent conversation:\n{history_text or '(none)'}\n\n"
                    f"Already-resolved product family: {state.get('service') or '(none)'}\n"
                    f"Already-resolved package/tier: {state.get('package_name_raw') or '(none)'}\n"
                    f"Identified entities: {entities_str or '(none)'}{budget_context}\n\n"
                    f"Customer's latest message:\n{question}"
                )),
            ])
        standalone = (result.standalone_query or "").strip() or fallback_query
        bridge = " ".join(t.strip() for t in result.bridge_terms if t.strip())
        final_query = f"{standalone} {bridge}".strip()
        badge = "Done"
    except Exception:
        logger.exception("Query rewrite LLM call failed; using fallback anchor+question query.")
        final_query = fallback_query
        badge = "Fallback"

    return {
        "retrieval_query": final_query,
        "workflow_trace": [step(
            "query_rewrite", "5b. Query Rewrite", "٥ب. إعادة صياغة الاستعلام",
            description_en="Rewrote to a standalone, bilingually-bridged search query.",
            badge=badge, status="completed",
            details={"query": final_query},
            latency_ms=elapsed_ms(start),
        )],
    }
