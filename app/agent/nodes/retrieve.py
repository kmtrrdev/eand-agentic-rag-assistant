import concurrent.futures
import logging
import re
from typing import Any, Dict, List, Optional
from langchain_core.documents import Document

from app.config import settings
from app.retrieval.hybrid_retriever import HybridRetriever
from app.retrieval.reranker import CandidateReranker
from app.retrieval.cross_encoder_reranker import CrossEncoderReranker

logger = logging.getLogger("etisalat_kb.node.retrieve")

# ── Legacy Hekaya Mixat chunk detection (module-level, compiled once) ──────
# The old naming system (tiers 35/50/65/100/150/200 EGP) may co-exist in the
# knowledge base alongside current tiers (52/69/92/120/180/270). These
# constants are used at retrieval time to banner-label legacy chunks so the
# LLM does not mistake retired bundle specs for current-plan facts.
_LEGACY_MIXAT_PHRASES = [
    "legacy naming system", "النظام القديم", "الباقات القديمة",
    "weekly consumption", "الاستهلاك الأسبوعي",
    "old system", "older system", "previous system",
]
_LEGACY_TIER_PATTERN = re.compile(
    r"\b(35|50|65|100|150|200)\s*(?:egp|جنيه|ج\.?م\.?|LE)?\b",
    re.IGNORECASE,
)
_CURRENT_MIXAT_TIERS = {"52", "69", "92", "120", "180", "270"}


def _is_legacy_mixat_chunk(content: str, src: str, metadata: Optional[Dict[str, Any]] = None) -> bool:
    """
    Returns True when a chunk describes the old Hekaya Mixat naming system
    (tiers 35/50/65/100/150/200) rather than the current active tiers
    (52/69/92/120/180/270).

    `plan_status` is stamped once, authoritatively, at ingestion time
    (app/ingestion/chunker.py::_tag_legacy_status) using the same signals this
    function used to re-derive independently at every retrieval — two separately
    maintained phrase lists that could (and did) drift apart. Trust that metadata
    field first; only fall back to the regex re-derivation below for chunks
    ingested before plan_status existed, so old indexes don't silently lose the
    legacy warning until they're re-ingested.
    """
    if metadata and "plan_status" in metadata:
        return metadata.get("plan_status") == "legacy"

    if "mixat" not in src.lower() and "هكايا مكسات" not in content and "حكاية مكسات" not in content:
        return False
    c_lower = content.lower()
    # Explicit phrase match — highest confidence signal
    if any(phrase in c_lower for phrase in _LEGACY_MIXAT_PHRASES):
        return True
    # Legacy tier number present AND no current tier number present in the same chunk
    has_legacy_tier = bool(_LEGACY_TIER_PATTERN.search(content))
    has_current_tier = any(
        f" {t} " in f" {content} " or f"\n{t}\n" in f"\n{content}\n"
        for t in _CURRENT_MIXAT_TIERS
    )
    return has_legacy_tier and not has_current_tier


_cached_retriever: Optional[HybridRetriever] = None
_cached_reranker: Optional[CandidateReranker] = None
_cached_cross_encoder: Optional[CrossEncoderReranker] = None


def get_retriever() -> HybridRetriever:
    global _cached_retriever
    if _cached_retriever is None:
        _cached_retriever = HybridRetriever()
    return _cached_retriever


def get_reranker() -> CandidateReranker:
    global _cached_reranker
    if _cached_reranker is None:
        _cached_reranker = CandidateReranker()
    return _cached_reranker


def get_cross_encoder() -> CrossEncoderReranker:
    global _cached_cross_encoder
    if _cached_cross_encoder is None:
        _cached_cross_encoder = CrossEncoderReranker()
    return _cached_cross_encoder


def retrieve_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    Hybrid Retrieval Node with Parallel Multi-Query Execution:
    Searches the primary question, expanded rewritten query, and keywords concurrently,
    with smart context inheritance from conversation history for follow-ups.
    """
    question = state["question"]
    history = state.get("history", [])
    rewritten = state.get("rewritten_query")
    keywords = state.get("keywords", [])
    intent = state.get("intent", "package_inquiry")
    service = state.get("service", "general")
    line_type = state.get("line_type", "mobile_phone")
    data_usage = state.get("data_usage", "medium")
    voice_usage = state.get("voice_usage", "medium")
    budget_egp = state.get("budget_egp")

    is_affirmative = question.strip().lower() in ["yes", "نعم", "ايوه", "تمام", "اه", "sure", "ok", "yep", "ايوة"]

    # On a retry (rewritten_query present from rewrite_query_node), search with the
    # rewritten query as the PRIMARY term — it exists specifically to fix whatever
    # made the first attempt weak/failed. The original question is still searched
    # too (kept as a secondary term below) so a bad rewrite can't lose ground, but
    # it no longer crowds out the rewrite by going first in every sub-query fan-out.
    primary_query = rewritten.strip() if (rewritten and rewritten.strip()) else question
    queries_to_search = [] if is_affirmative else [primary_query]
    if primary_query != question and not is_affirmative and question not in queries_to_search:
        queries_to_search.append(question)

    # Context inheritance for follow-ups (e.g. "yes", "ماشي", "تمام", "مكسات", "النت", "الخطط الاعلى", "الباقات الأكبر")
    follow_up_terms = ["اعلي", "أعلى", "اعلى", "أعلي", "اكبر", "أكبر", "باقي", "كلهم", "الكل", "تانية", "تانيين", "تاني", "higher", "more", "rest", "all", "first", "second", "code"]
    is_follow_up = history and (len(question.strip()) < 50 or is_affirmative or any(t in question.lower() for t in follow_up_terms))

    if is_follow_up:
        last_context_str = ""
        last_user_msg = next((m.get("content", "") for m in reversed(history) if m.get("role") == "user"), "")
        if is_affirmative and last_user_msg:
            queries_to_search.append(last_user_msg)

        for msg in history[-4:]:
            content = msg.get("content", "")
            last_context_str += " " + content
            # Extract prominent product names from previous turns
            for prod in ["حكاية مكسات", "حكاية ميكسات", "حكاية إنترنت", "حكاية انترنت", "إمرالد", "امرالد", "سوبر كونكت", "أقوى كارت", "اقوى كارت", "داتا لاين", "Hekaya", "Emerald", "Prepaid", "Aqwa Card 5", "Aqwa Card 19", "Hekaya Internet 105", "Hekaya Internet 132"]:
                if prod.lower() in content.lower() and prod not in queries_to_search:
                    queries_to_search.append(prod)
            # If asking for higher plans specifically
            if any(t in question.lower() for t in ["اعلي", "أعلى", "اعلى", "أعلي", "اكبر", "أكبر", "higher"]):
                if "حكاية إنترنت" in content or "hekaya internet" in content.lower():
                    queries_to_search.append("حكاية إنترنت 270 345 415 480 600")
                elif "حكاية مكسات" in content or "hekaya mixat" in content.lower():
                    queries_to_search.append("حكاية مكسات 120 180 270")

        # If question is asking for code/price/renewal of a referred entity from history
        if any(t in question.lower() for t in ["كود", "تجديد", "اشتراك", "سعر", "تفاصيل", "code", "renew", "price"]):
            # Extract numeric tiers (e.g. 150, 92, 52, 60, etc.) from history
            tiers = re.findall(r"\b(35|40|52|60|65|70|80|92|100|105|120|130|132|150|180|200|270|345|415|430|480|600|775|1200)\b", last_context_str)
            for tier in tiers[-2:]:
                queries_to_search.append(f"حكاية {tier} كود تجديد الاشتراك")
                queries_to_search.append(f"Hekaya {tier} code")

    if rewritten and rewritten.strip():
        for line in rewritten.split("\n"):
            clean_line = line.strip().lstrip("0123456789.-•* ").strip()
            if clean_line and clean_line != question.strip() and clean_line not in queries_to_search:
                queries_to_search.append(clean_line)

    if keywords and isinstance(keywords, list):
        kw_str = " ".join([str(k) for k in keywords[:6] if k])
        if kw_str and kw_str not in queries_to_search:
            queries_to_search.append(kw_str)

    # Domain-specific query expansion for complete enumerations & product overviews
    q_low = question.lower()
    if any(k in q_low for k in ["aqwa card", "aqwa", "kart", "card", "cards", "أقوى كارت", "اقوى كارت", "اقوي كارت", "أقوي كارت", "كروت الشحن", "كارت شحن", "كارت", "كروت"]):
        queries_to_search.append("Aqwa Card recharges 3.5 5 7 10 12.5 15 17.5 19 21.5 29 35 42 50 75 Mixes video minutes code *811# Prepaid Systems")
        queries_to_search.append("كروت شحن أقوى كارت اتصالات مصر كود الاشتراك *811# وحدات ميكس")
        queries_to_search.append("What is Aqwa Card e& Egypt prepaid recharge portfolio")
    if any(k in q_low for k in ["super connect", "سوبر كونكت", "سوبركونكت"]):
        queries_to_search.append("باقات سوبر كونكت الحصرية لحكاية 9 20 32 50 80 105 165 260 390 520")
    if any(k in q_low for k in ["data line", "dataline", "داتا لاين", "داتالاين"]):
        queries_to_search.append("باقات داتا لاين الأساسية 1.8 2.5 3.5 8 14 25 45 72 GB")
    if any(k in q_low for k in ["emerald", "إمرالد", "امرالد"]):
        queries_to_search.append("باقات إمرالد الشهرية 430 780 1120 1725 3450 خطوط العائلة")
    if any(k in q_low for k in ["simple prepaid", "أنظمة الكارت", "انظمة الكارت", "كارت المدفوع", "أهلاً", "اهلاً", "اهلا"]):
        queries_to_search.append("أنظمة الكارت المدفوع مقدماً أقوى كارت أهلاً باقات يومية منيو الجنيه")

    # ── T&C / Exceptions retrieval boost ──────────────────────────────────────
    # Queries about hotline billing, piasters, exception numbers, or 16XXX must
    # explicitly retrieve the terms & conditions chunk (HekayaMixat.pdf page 13)
    _tc_triggers = [
        "hotline", "short number", "16xxx", "15xxx", "19xxx",
        "piaster", "piastre", "قرش", "بياستر",
        "exception", "استثناء", "ما عدا", "except",
        "16399", "16528", "16000", "رسوم المكالمات", "billing",
        "أرقام ساخنة", "short code", "special number",
    ]
    if any(t in q_low for t in _tc_triggers):
        queries_to_search.append(
            "calls hotline numbers 16XXX 19XXX 15XXX billed 30 piasters exception 16399 16528 hekaya mixat terms"
        )
        queries_to_search.append(
            "Calls to short/hotline numbers 16XXX 19XXX 15XXX billed 30 piasters/min exception 16399 standard 16528 10 piasters"
        )

    # ── Cross-document seed queries for broad enumeration (list all categories) ──
    _enum_triggers = [
        "list all", "all categories", "all plans", "all packages",
        "كل الباقات", "جميع الباقات", "كل الأنظمة", "كل الفئات",
        "categories", "overview", "نظرة عامة",
    ]
    if any(t in q_low for t in _enum_triggers):
        # Force a seed query per source document to guarantee multi-doc retrieval
        for seed in [
            "حكاية مكسات 52 69 92 120 180 270 وحدات مكس كود اشتراك",
            "حكاية إنترنت 46 58 80 105 132 165 205 270 345 480 600 ميجا سعة",
            "أنظمة الكارت المدفوع أقوى كارت أهلاً باقات يومية منيو الجنيه",
            "إمرالد 430 780 1120 1725 3450 بوست بيد شهري",
            "داتا لاين 1.8 2.5 3.5 8 14 25 45 72 جيجا راوتر مودم",
        ]:
            if seed not in queries_to_search:
                queries_to_search.append(seed)

    retriever = get_retriever()
    reranker = get_reranker()

    is_legacy_query = any(k in question.lower() for k in ["قديم", "قديمة", "القديم", "القديمة", "legacy", "previous", "old system", "older system"])
    exclude_legacy = not is_legacy_query

    if is_legacy_query:
        queries_to_search.append("Hekaya Mixat legacy naming system 35 50 65 100 150 200 weekly consumption minutes mixes")
        queries_to_search.append("نظام التسمية القديم لحكاية مكسات 150 الاستهلاك الأسبوعي")

    # Parallel search across multiple query formulations
    all_candidate_documents: List[Document] = []
    seen = set()
    query_errors: List[str] = []

    with concurrent.futures.ThreadPoolExecutor(max_workers=min(len(queries_to_search), 4)) as executor:
        future_to_query = {
            executor.submit(retriever.search, q, settings.TOP_K, exclude_legacy): q
            for q in queries_to_search
        }
        for future in concurrent.futures.as_completed(future_to_query):
            q = future_to_query[future]
            try:
                docs = future.result()
                for doc in docs:
                    key = (
                        doc.metadata.get("source_file", ""),
                        doc.metadata.get("page", 0),
                        doc.page_content[:100].strip()
                    )
                    if key not in seen:
                        seen.add(key)
                        all_candidate_documents.append(doc)
            except Exception as exc:
                logger.warning("Sub-query search failed for %r: %s: %s", q, type(exc).__name__, exc)
                query_errors.append(f"{q!r}: {type(exc).__name__}: {exc}")

    # Stage 1: Heuristic reranking (device/service/budget business signals)
    heuristic_top = reranker.rerank(
        documents=all_candidate_documents,
        query=question,
        intent=intent,
        service=service,
        line_type=line_type,
        data_usage=data_usage,
        voice_usage=voice_usage,
        budget_egp=budget_egp,
        # RERANKER_TOP_N is the intended, documented control for Stage-1 pool size
        # feeding Stage-2 cross-encoder reranking. It used to be shadowed by
        # `max(FINAL_K * 3, RERANKER_TOP_N)` — with the default FINAL_K=10, FINAL_K*3
        # (30) always won over RERANKER_TOP_N (20), so the setting was configurable
        # but had zero actual effect. `max(..., FINAL_K)` here is just a safety floor
        # so the pool can never end up smaller than what Stage 2 needs to select from.
        final_k=max(settings.RERANKER_TOP_N, settings.FINAL_K),
    )

    # Stage 2: Cross-encoder semantic reranking (if enabled)
    if settings.CROSS_ENCODER_RERANKER_ENABLED and heuristic_top:
        cross_encoder = get_cross_encoder()
        is_enumeration = (
            state.get("intent") == "enumeration"
            or any(k in question.lower() for k in [
                "all", "every", "list all", "categories", "كل", "جميع", "فئات", "أنظمة",
                "انظمة", "باقات", "تفاصيل", "نظام", "أنظمه", "details", "packages", "plans",
                "emerald", "إمرالد", "امرالد", "اقوي كارت", "أقوى كارت", "حكاية"
            ])
        )
        selected_documents = cross_encoder.rerank(
            documents=heuristic_top,
            query=question,
            final_k=12 if is_enumeration else settings.FINAL_K,
        )
        cross_encoder_active = cross_encoder.last_call_used_model
    else:
        selected_documents = heuristic_top[:settings.FINAL_K]
        cross_encoder_active = False

    context_parts = []
    sources = []

    for doc in selected_documents:
        src_name = doc.metadata.get("source_file", "unknown")
        pg = doc.metadata.get("page", "")
        content = doc.page_content

        # Stamp legacy chunks with an unambiguous warning banner
        if _is_legacy_mixat_chunk(content, src_name, doc.metadata):
            chunk_header = (
                f"--- ⛔ LEGACY CHUNK — DO NOT USE FOR CURRENT PLANS ⛔ ---\n"
                f"--- Document: {src_name} (Page {pg}) [LEGACY NAMING SYSTEM] ---\n"
                f"WARNING: This chunk describes the OLD Hekaya Mixat naming system "
                f"(retired tiers: 35/50/65/100/150/200 EGP). "
                f"Its Mixes counts, weekly caps, and codes are UNRELATED to the current "
                f"6-tier system (52/69/92/120/180/270 EGP). "
                f"DO NOT cite any number from this chunk to answer a question about a current-tier plan.\n"
                f"-----------------------------------------------------------"
            )
            context_parts.append(f"{chunk_header}\n{content}")
            logger.debug(
                "Legacy Hekaya Mixat chunk detected and labelled: source=%s page=%s",
                src_name, pg,
            )
        else:
            context_parts.append(
                f"--- Document: {src_name} (Page {pg}) ---\n{content}"
            )

        sources.append({
            "source": src_name,
            "page": pg,
            "category": doc.metadata.get("category"),
            "product": doc.metadata.get("product"),
            "snippet": content.strip(),
        })

    # ── Cross-document contamination guard ─────────────────────────────────
    # When chunks from multiple distinct source documents are present, prepend
    # an explicit warning so the LLM does not blend facts across plan types.
    unique_sources = list(dict.fromkeys(s["source"] for s in sources if s["source"]))
    if len(unique_sources) > 1:
        src_list = ", ".join(unique_sources)
        multi_source_warning = (
            "⚠ MULTI-SOURCE CONTEXT WARNING ⚠\n"
            f"The following context contains chunks from {len(unique_sources)} DIFFERENT source documents: {src_list}.\n"
            "CRITICAL RULE: Each fact, number, quota, or benefit MUST be attributed ONLY to the document it came from.\n"
            "DO NOT transfer, blend, or generalise any detail (e.g. minutes, Mixes, GB, EGP, %, USSD codes) from one document's chunks to answer a question about a different plan/document.\n"
            "If the question is about a specific plan (e.g. Hekaya Mixat 270), use ONLY the chunks from that plan's source document.\n"
            "Treat each document section as a fully isolated source — cross-document fact borrowing is strictly forbidden.\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        )
        context = multi_source_warning + "\n\n".join(context_parts)
    else:
        context = "\n\n".join(context_parts)

    # ── Preserve verified MCP ground-truth context ──────────────────────────
    existing_context = state.get("context") or ""
    header_marker = "=== VERIFIED MCP GROUND TRUTH"
    end_marker = "=== END MCP GROUND TRUTH ==="
    if header_marker in existing_context:
        header_start = existing_context.index(header_marker)
        if end_marker in existing_context:
            end_idx = existing_context.index(end_marker) + len(end_marker)
            mcp_block = existing_context[header_start:end_idx].strip()
        else:
            mcp_block = existing_context[header_start:].strip()
        context = f"{mcp_block}\n\n{context}" if context else mcp_block

    step_info = {
        "node": "retrieve",
        "title_ar": "الاسترجاع الهجين المتوازي وإعادة الترتيب",
        "title_en": "Parallel Hybrid Retrieval & Reranking",
        "status": "completed",
        "badge": f"🔍 {len(selected_documents)} وثائق معتمدة",
        "description_ar": f"تم البحث المتوازي في قاعدة المعرفة واسترجاع {len(all_candidate_documents)} وثيقة مرشحة ثم اختيار أفضل {len(selected_documents)} وثيقة مطابقة.",
        "description_en": f"Concurrently queried KB across {len(queries_to_search)} formulations, retrieved {len(all_candidate_documents)} chunks, and reranked top {len(selected_documents)}.",
        "details": {
            "candidate_count": len(all_candidate_documents),
            "selected_count": len(selected_documents),
            "sources": [s["source"] for s in sources],
            "queries_searched": queries_to_search,
            "cross_encoder_active": cross_encoder_active,
            # Per-chunk traceability for debugging retrieval vs hallucination origin
            "retrieved_chunks": [
                {
                    "source": s["source"],
                    "page": s["page"],
                    "snippet": s["snippet"][:200],
                }
                for s in sources
            ],
            **({"query_errors": query_errors} if query_errors else {}),
        },
    }

    retrieval_attempts = state.get("retrieval_attempts", 0) + 1

    retrieval_evidence = [
        {
            "source_type": "kb",
            "authority": "official_kb",
            "source_file": s.get("source"),
            "page": s.get("page"),
            "snippet": s.get("snippet", "")[:300],
        }
        for s in sources
    ]

    return {
        "documents": selected_documents,
        "context": context,
        "sources": sources,
        "retrieval_evidence": retrieval_evidence,
        "retrieval_attempts": retrieval_attempts,
        "last_retrieval_query": question,
        "workflow_trace": [step_info],
    }