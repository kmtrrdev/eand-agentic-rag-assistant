import logging
import re
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import JsonOutputParser

from app.llm.client import get_llm
from app.llm.prompts import QUERY_UNDERSTANDING_PROMPT
from app.retrieval.keyword_retriever import tokenize
from app.tools.get_package_details import PACKAGE_REGISTRY

logger = logging.getLogger("etisalat_kb.node.understand")

# Package/tier names for history-based entity inheritance ("what's its code?" after
# discussing "Emerald 780"), derived from the single product catalog instead of
# hand-typed here. This used to be two separately hand-maintained lists (one here,
# a smaller one in deterministic_fallback_analysis) that had drifted apart and both
# contained tiers that don't actually exist in the registry (e.g. "hekaya mixat 105",
# "hekaya mixat 70", "aqwa card 25") — silent dead entries nobody noticed because a
# non-matching entry just never fires, it doesn't error. Restricted to keys with a
# digit (excludes bare family names like "ahlan", which is also common
# code-switched English-Arabic chat for "hi" and would false-positive on any prior
# greeting, not just a genuine package reference).
_KNOWN_PACKAGE_KEYS = [k for k in PACKAGE_REGISTRY.keys() if any(c.isdigit() for c in k)]


class QueryProfiling(BaseModel):
    category: Optional[str] = Field(
        default="mobile",
        description="Category: mobile, internet, postpaid, prepaid, support, comparison"
    )
    service: Optional[str] = Field(
        default="general",
        description="Service: Hekaya, Emerald, SuperConnect, DataLine, Prepaid, general"
    )
    sub_track: Optional[str] = Field(
        default=None,
        description="Hekaya sub-track: Mixat | Internet | null. Prepaid sub-track: Ahlan | AqwaCard | SuperConnect | null"
    )
    line_type: Optional[str] = Field(
        default="mobile_phone",
        description="Line type: mobile_phone, home_internet, mifi_router"
    )
    data_usage: Optional[str] = Field(
        default="medium",
        description="Data usage: high, medium, low"
    )
    voice_usage: Optional[str] = Field(
        default="medium",
        description="Voice usage: high, medium, low, none"
    )
    budget_egp: Optional[float] = Field(
        default=None,
        description="Extracted numerical budget in EGP (tax-inclusive) if explicitly stated"
    )
    keywords: List[str] = Field(
        default_factory=list,
        description="3-8 Arabic/English search keywords for retrieval"
    )
    entities: List[str] = Field(
        default_factory=list,
        description="Specific package names, tier numbers, or USSD codes mentioned"
    )
    needs_clarification: bool = Field(
        default=False,
        description="True only when query is genuinely ambiguous even after checking history"
    )
    clarification_hint: Optional[str] = Field(
        default=None,
        description="The single most important question to ask if needs_clarification=true"
    )
    analysis_summary: str = Field(
        default="",
        description="Short summary of what the customer wants"
    )


def _extract_history_context(history: Optional[List[Dict[str, str]]]) -> str:
    """
    Build a rich history context string for LLM prompts.
    Includes up to last 6 turns (3 exchanges) with full content.
    Specially flags the last assistant question to enable pending-answer detection.
    """
    if not history:
        return ""

    lines = []
    recent = history[-6:]  # up to 3 full exchanges
    for msg in recent:
        role = msg.get("role", "user")
        content = (msg.get("content") or "").strip()
        if not content:
            continue
        prefix = "Assistant" if role == "assistant" else "Customer"
        lines.append(f"[{prefix}]: {content}")

    if not lines:
        return ""

    ctx = "=== Conversation History (most recent last) ===\n"
    ctx += "\n".join(lines)
    ctx += "\n=== End of History ===\n"

    # Flag if the last assistant message ended with a question
    last_assistant = next(
        (m.get("content", "") for m in reversed(history) if m.get("role") == "assistant"),
        ""
    )
    if last_assistant and ("؟" in last_assistant or "?" in last_assistant):
        ctx += "\n⚠ NOTE: The last assistant message asked a question. The customer's current message may be a direct answer — resolve it accordingly.\n"

    return ctx


def _extract_history_summary(history: Optional[List[Dict[str, str]]]) -> str:
    """Compact 1-line summary of the last 2 turns for query rewrite prompt."""
    if not history:
        return "No prior conversation."
    recent = history[-4:]
    parts = [
        f"{'A' if m.get('role') == 'assistant' else 'U'}: {(m.get('content') or '')[:100]}"
        for m in recent if m.get("content")
    ]
    return " | ".join(parts) if parts else "No prior conversation."


def deterministic_fallback_analysis(
    question: str,
    history: Optional[List[Dict[str, str]]] = None
) -> Dict[str, Any]:
    """
    Rule-based fallback when LLM structured output parsing fails.
    Preserves history-inherited service/sub_track.
    """
    combined_text = question
    if history:
        recent_content = " ".join(
            m.get("content", "") for m in history[-4:] if m.get("content")
        )
        combined_text = f"{question} {recent_content}"

    q_lower = combined_text.lower()
    tokens = tokenize(question)

    # Budget extraction
    budget_match = re.search(
        r"(?:بـ|بمبلغ|سعر|حدود|budget|around|about|costs?)\s*(\d+(?:\.\d+)?)"
        r"|(\d+(?:\.\d+)?)\s*(?:جنيه|egp|le|ج\.م)",
        q_lower
    )
    budget_egp = None
    if budget_match:
        try:
            val_str = budget_match.group(1) or budget_match.group(2)
            budget_egp = float(val_str)
        except Exception:
            pass

    # Inherit service and sub_track from history if current message is short/affirmative
    inherited_service = "general"
    inherited_sub_track = None
    inherited_entities = []
    if history:
        for msg in reversed(history):
            content_lower = (msg.get("content") or "").lower()
            # Extract previous entities — derived from the product catalog
            # (_KNOWN_PACKAGE_KEYS, module-level) plus a few Arabic numeral-phrase
            # aliases the catalog's English keys don't capture on their own.
            for pkg_key in _KNOWN_PACKAGE_KEYS:
                if pkg_key in content_lower:
                    pkg_name = PACKAGE_REGISTRY[pkg_key].get("type", pkg_key.title())
                    if pkg_name not in inherited_entities:
                        inherited_entities.append(pkg_name)
            if ("أقوى كارت 5" in content_lower or "أقوى 5" in content_lower) and "Aqwa Card 5" not in inherited_entities:
                inherited_entities.append("Aqwa Card 5")
            if "أقوى كارت 19" in content_lower and "Aqwa Card 19" not in inherited_entities:
                inherited_entities.append("Aqwa Card 19")
            if "حكاية مكسات 52" in content_lower and "Hekaya Mixat 52" not in inherited_entities:
                inherited_entities.append("Hekaya Mixat 52")

            if "مكسات" in content_lower or "mixat" in content_lower:
                inherited_service = "Hekaya"
                inherited_sub_track = "Mixat"
                break
            if "حكاية إنترنت" in content_lower or "حكاية انترنت" in content_lower or "hekaya internet" in content_lower:
                inherited_service = "Hekaya"
                inherited_sub_track = "Internet"
                break
            if "حكاية" in content_lower or "hekaya" in content_lower:
                inherited_service = "Hekaya"
                break
            if "إمرالد" in content_lower or "emerald" in content_lower:
                inherited_service = "Emerald"
                break
            if "أهلا" in content_lower or "أهلاً" in content_lower or "ahlan" in content_lower:
                inherited_service = "Prepaid"
                inherited_sub_track = "Ahlan"
                break
            if "أقوى كارت" in content_lower or "اقوى كارت" in content_lower or "aqwa" in content_lower:
                inherited_service = "Prepaid"
                inherited_sub_track = "AqwaCard"
                break
            if "سوبر كونكت" in content_lower or "super connect" in content_lower:
                inherited_service = "SuperConnect"
                inherited_sub_track = "SuperConnect"
                break
            if "prepaid" in content_lower or "كارت" in content_lower or "شحن" in content_lower:
                inherited_service = "Prepaid"
                break

    # Check for short affirmative or pronoun follow-up
    is_affirmative = q_lower.strip() in ["yes", "نعم", "ايوه", "تمام", "اه", "sure", "ok", "yep", "ايوة"]
    is_pronoun_followup = any(p in q_lower for p in ["first one", "second one", "الاولى", "التانية", "كودها", "سعرها", "its code", "their code"])

    if is_affirmative and inherited_entities:
        return {
            "category": "mobile",
            "service": inherited_service,
            "sub_track": inherited_sub_track,
            "line_type": "mobile_phone",
            "data_usage": "medium",
            "voice_usage": "medium",
            "budget_egp": budget_egp,
            "keywords": [inherited_entities[0], "details"],
            "entities": [inherited_entities[0]],
            "needs_clarification": False,
            "clarification_hint": None,
            "analysis_summary": f"Follow-up confirmation on {inherited_entities[0]}"
        }

    if is_pronoun_followup and inherited_entities:
        target_entity = inherited_entities[0]
        if ("second" in q_lower or "التانية" in q_lower) and len(inherited_entities) > 1:
            target_entity = inherited_entities[1]
        return {
            "category": "mobile",
            "service": inherited_service,
            "sub_track": inherited_sub_track,
            "line_type": "mobile_phone",
            "data_usage": "medium",
            "voice_usage": "medium",
            "budget_egp": budget_egp,
            "keywords": [target_entity, "code", "كود"],
            "entities": [target_entity],
            "needs_clarification": False,
            "clarification_hint": None,
            "analysis_summary": f"Follow-up code inquiry on {target_entity}"
        }

    # Detect from current question (overrides inherited)
    if any(k in q_lower for k in ["mifi", "usb", "modem", "router", "راوتر", "مودم", "dataline", "data line", "ماي فاي"]):
        line_type = "mifi_router"
        service = "DataLine"
        sub_track = None
    elif any(k in q_lower for k in ["adsl", "fiber", "home internet", "انترنت منزلي", "نت منزلي"]):
        line_type = "home_internet"
        service = "general"
        sub_track = None
    elif any(k in q_lower for k in ["super connect", "سوبر كونكت", "سوبركونكت"]):
        line_type = "mobile_phone"
        service = "SuperConnect"
        sub_track = "SuperConnect"
    else:
        line_type = "mobile_phone"
        if "emerald" in q_lower or "إمرالد" in q_lower:
            service = "Emerald"
            sub_track = None
        elif "مكسات" in q_lower or "mixat" in q_lower:
            service = "Hekaya"
            sub_track = "Mixat"
        elif "حكاية إنترنت" in q_lower or "حكاية انترنت" in q_lower or "hekaya internet" in q_lower or ("نت" in q_lower and "حكاية" in q_lower):
            service = "Hekaya"
            sub_track = "Internet"
        elif "حكاية" in q_lower or "hekaya" in q_lower:
            service = "Hekaya"
            sub_track = inherited_sub_track
        elif "ahlan" in q_lower or "أهلا" in q_lower or "أهلاً" in q_lower:
            service = "Prepaid"
            sub_track = "Ahlan"
        elif "aqwa" in q_lower or "أقوى كارت" in q_lower or "اقوى كارت" in q_lower:
            service = "Prepaid"
            sub_track = "AqwaCard"
        elif "كارت" in q_lower or "prepaid" in q_lower:
            service = "Prepaid"
            sub_track = inherited_sub_track
        else:
            service = inherited_service
            sub_track = inherited_sub_track

    # Determine data and voice usage from terms
    has_voice_intent = any(k in q_lower for k in ["دقايق", "دقيقة", "دقائق", "مكالمات", "voice", "calls", "call", "مكالمه"])
    has_data_intent = any(k in q_lower for k in ["نت", "انترنت", "إنترنت", "data", "internet", "ميجابايت", "جيجابايت", "mb", "gb"])

    if has_voice_intent and not has_data_intent:
        voice_usage = "high"
        data_usage = "low"
        if service == "general":
            service = "Hekaya"
            sub_track = "Mixat"
    elif has_data_intent and not has_voice_intent:
        data_usage = "high"
        voice_usage = "low"
        if service == "general":
            service = "Hekaya"
            sub_track = "Internet"
    elif has_voice_intent and has_data_intent:
        voice_usage = "high"
        data_usage = "high"
        if service == "general":
            service = "Hekaya"
            sub_track = "Mixat"
    else:
        data_usage = "medium"
        voice_usage = "medium"

    extracted_keywords = [str(t) for t in tokens[:6]] if tokens else []

    return {
        "category": "mobile",
        "service": service,
        "sub_track": sub_track,
        "line_type": line_type,
        "data_usage": data_usage,
        "voice_usage": voice_usage,
        "budget_egp": budget_egp,
        "keywords": extracted_keywords,
        "entities": [],
        "needs_clarification": False,
        "clarification_hint": None,
        "analysis_summary": "Deterministic rule-based profiling (LLM fallback)"
    }


from app.agent.text_signals import (
    is_greeting,
    is_pure_thanks,
    OUT_OF_SCOPE_TERMS,
    UNSUPPORTED_SERVICE_TERMS,
)


def _build_understand_output(state: Dict[str, Any], data: Dict[str, Any]) -> Dict[str, Any]:
    question = state.get("question", "").lower()
    intent = data.get("intent") or state.get("intent", "package_inquiry")
    category = data.get("category", "mobile")
    service = data.get("service", "general")
    sub_track = data.get("sub_track")
    line_type = data.get("line_type", "mobile_phone")
    budget = data.get("budget_egp")
    keywords = data.get("keywords", [])
    entities = data.get("entities", [])
    needs_clarification = data.get("needs_clarification", False)
    clarification_hint = data.get("clarification_hint")
    is_out_of_scope = data.get("is_out_of_scope", False)
    is_unsupported = data.get("is_unsupported_service", False)

    # Entity inheritance from history if current message asks follow-up on previous entity
    history = state.get("history", [])
    if not entities and history:
        for msg in reversed(history):
            content_lower = (msg.get("content") or "").lower()
            for pkg_key in _KNOWN_PACKAGE_KEYS:
                if pkg_key in content_lower:
                    entities = [PACKAGE_REGISTRY[pkg_key].get("type", pkg_key.title())]
                    data["entities"] = entities
                    break
            if entities:
                break

    # Guard against LLM over-clarification on explicit queries:
    has_explicit_target = (
        bool(entities)
        or any(c.isdigit() for c in question)
        or any(k in question for k in [
            "aqwa", "أقوى", "اقوى", "كارت", "card", "hekaya", "حكاية", "مكسات", "mixat",
            "emerald", "إمرالد", "امرالد", "dataline", "داتا", "سوبر", "super",
            "code", "كود", "تفعيل", "تفاصيل", "details", "compare", "قارن", "vs",
            "5", "five", "categories", "فئات", "أنظمة", "انظمة", "سعر", "price",
            "double", "offer", "عرض", "family", "عائلة", "عيلة", "add-on", "اضافية",
            "إضافية", "redeem", "home internet", "انترنت منزلي", "options", "coins",
            "master", "ماستر", "lines", "باقات", "packages"
        ])
    )
    if has_explicit_target:
        needs_clarification = False
        clarification_hint = None
        data["needs_clarification"] = False
        data["clarification_hint"] = None

    question_orig = state.get("question", "")
    budget = data.get("budget_egp")
    budget_str = f" | ميزانية: {budget} ج.م" if budget else ""
    from app.tools.recommendation_engine import extract_recommendation_constraints
    rec_constraints = extract_recommendation_constraints(question_orig, history)

    # If the user asks for a recommendation but leaves service_type unknown and has no active track in history
    is_rec_intent = any(k in question_orig.lower() for k in ["رشحلي", "أنصحني", "انصحني", "اختارلي", "recommend", "which package"])
    if is_rec_intent and rec_constraints.get("service_type") == "UNKNOWN" and not rec_constraints.get("package_category") and not history:
        needs_clarification = True
        is_ar = any('\u0600' <= c <= '\u06FF' for c in question_orig)
        clarification_hint = (
            "تحب أرشحلك باقة دقايق ومكسات (مكالمات وإنترنت) ولا باقة إنترنت موبايل فقط؟"
            if is_ar
            else "Would you prefer a mixed calls & data package (Hekaya Mixat) or a mobile internet-only bundle?"
        )

    sub_str = f" ({sub_track})" if sub_track else ""
    desc_ar = f"النية: {intent} | القسم: {category} | الخدمة: {service}{sub_str}{budget_str}"
    desc_en = f"Intent: {intent} | Category: {category} | Service: {service}{sub_str}"

    step_info = {
        "node": "understand",
        "title_ar": "تحليل وتوصيف الاستفسار",
        "title_en": "Query Profiling & Constraints",
        "status": "completed",
        "badge": f"🎯 {intent}",
        "description_ar": desc_ar,
        "description_en": desc_en,
        "details": {
            "intent": intent,
            "category": category,
            "service": service,
            "sub_track": sub_track,
            "line_type": line_type,
            "budget_egp": budget,
            "recommendation_constraints": rec_constraints,
            "keywords": keywords,
            "entities": entities,
            "needs_clarification": needs_clarification,
            "clarification_hint": clarification_hint,
            "analysis_summary": data.get("analysis_summary", ""),
        },
    }

    result = dict(data)
    result["intent"] = intent
    result["is_out_of_scope"] = is_out_of_scope
    result["is_unsupported_service"] = is_unsupported
    result["recommendation_constraints"] = rec_constraints
    result["needs_clarification"] = needs_clarification
    result["clarification_hint"] = clarification_hint
    result["workflow_trace"] = [step_info]
    return result


def understand_query_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    Unified Query Understanding Node:
    - Fast greeting, out-of-scope, and unsupported service identification.
    - Full conversation history awareness and reference resolution.
    - Extracts entity names, budget, negations, and device compatibility.
    """
    question = state.get("question", "")
    history = state.get("history", [])

    q_clean = question.lower().strip().rstrip("!.,?")

    # 1. Fast Greeting Check
    if is_greeting(question) or is_pure_thanks(question):
        return {
            "intent": "greeting",
            "category": "support",
            "service": "general",
            "needs_clarification": False,
            "is_out_of_scope": False,
            "is_unsupported_service": False,
            "workflow_trace": [{
                "node": "understand",
                "title_en": "Query Profiling",
                "badge": "👋 Greeting",
                "status": "completed",
                "description_en": "Conversational greeting detected",
                "details": {"intent": "greeting"},
            }],
        }

    # 2. Fast Out-of-Scope Check
    if any(t in q_clean for t in OUT_OF_SCOPE_TERMS):
        return {
            "intent": "out_of_scope",
            "is_out_of_scope": True,
            "needs_clarification": False,
            "is_unsupported_service": False,
            "workflow_trace": [{
                "node": "understand",
                "title_en": "Query Profiling",
                "badge": "🛑 Out of Scope",
                "status": "completed",
                "description_en": "Out-of-scope query detected",
                "details": {"intent": "out_of_scope"},
            }],
        }

    # 3. Fast Unsupported Service Check
    if any(t in q_clean for t in UNSUPPORTED_SERVICE_TERMS):
        return {
            "intent": "unsupported_service",
            "is_unsupported_service": True,
            "needs_clarification": False,
            "is_out_of_scope": False,
            "workflow_trace": [{
                "node": "understand",
                "title_en": "Query Profiling",
                "badge": "🏢 Unsupported Service",
                "status": "completed",
                "description_en": "Unsupported enterprise/SIM swap query detected",
                "details": {"intent": "unsupported_service"},
            }],
        }

    is_affirmative = q_clean in ["yes", "نعم", "ايوه", "تمام", "اه", "sure", "ok", "yep", "ايوة"]
    is_pronoun_followup = any(p in q_clean for p in ["first one", "second one", "الاولى", "التانية", "كودها", "سعرها", "its code", "their code"])

    if (is_affirmative or is_pronoun_followup) and history:
        result_data = deterministic_fallback_analysis(question, history)
        return _build_understand_output(state, result_data)

    history_context = _extract_history_context(history)
    user_input = f"Customer Query:\n{question}\n\n{history_context}".strip()

    try:
        llm = get_llm(timeout=15.0, max_tokens=300).with_structured_output(QueryProfiling)
        prompt = ChatPromptTemplate.from_messages([
            ("system", QUERY_UNDERSTANDING_PROMPT),
            ("human", "{user_input}")
        ])
        result = (prompt | llm).invoke({"user_input": user_input})

        return _build_understand_output(state, {
            "category": getattr(result, "category", None) or "mobile",
            "service": getattr(result, "service", None) or "general",
            "sub_track": getattr(result, "sub_track", None),
            "line_type": getattr(result, "line_type", None) or "mobile_phone",
            "data_usage": getattr(result, "data_usage", None) or "medium",
            "voice_usage": getattr(result, "voice_usage", None) or "medium",
            "budget_egp": getattr(result, "budget_egp", None),
            "keywords": getattr(result, "keywords", []) or tokenize(question)[:6],
            "entities": getattr(result, "entities", []) or [],
            "needs_clarification": getattr(result, "needs_clarification", False),
            "clarification_hint": getattr(result, "clarification_hint", None),
            "analysis_summary": getattr(result, "analysis_summary", "")
        })

    except Exception as exc:
        logger.warning("Structured query profiling failed, trying JSON fallback: %s", exc)
        # Fallback: JSON parser
        try:
            parser = JsonOutputParser(pydantic_object=QueryProfiling)
            prompt = ChatPromptTemplate.from_messages([
                ("system", QUERY_UNDERSTANDING_PROMPT + "\n\nOutput ONLY valid JSON:\n{format_instructions}"),
                ("human", "{user_input}")
            ])
            response = (prompt | get_llm(timeout=15.0, max_tokens=300)).invoke({
                "user_input": user_input,
                "format_instructions": parser.get_format_instructions()
            })
            raw_text = (response.content or "").strip()
            if "<think>" in raw_text:
                raw_text = re.sub(r"<think>.*?</think>", "", raw_text, flags=re.DOTALL).strip()

            res_dict = parser.parse(raw_text)
            if res_dict and isinstance(res_dict, dict):
                return _build_understand_output(state, {
                    "category": res_dict.get("category") or "mobile",
                    "service": res_dict.get("service") or "general",
                    "sub_track": res_dict.get("sub_track"),
                    "line_type": res_dict.get("line_type") or "mobile_phone",
                    "data_usage": res_dict.get("data_usage") or "medium",
                    "voice_usage": res_dict.get("voice_usage") or "medium",
                    "budget_egp": res_dict.get("budget_egp"),
                    "keywords": res_dict.get("keywords") or tokenize(question)[:6],
                    "entities": res_dict.get("entities") or [],
                    "needs_clarification": res_dict.get("needs_clarification", False),
                    "clarification_hint": res_dict.get("clarification_hint"),
                    "analysis_summary": res_dict.get("analysis_summary", "")
                })
        except Exception as exc2:
            logger.error("JSON fallback query profiling also failed, using deterministic rules: %s", exc2)

    result_data = deterministic_fallback_analysis(question, history)
    result_data["analysis_summary"] = (
        "Deterministic rule-based profiling (both LLM structured output and JSON fallback failed)"
    )
    return _build_understand_output(state, result_data)
