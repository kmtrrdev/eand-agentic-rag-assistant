"""
Two-stage hybrid retrieval: dense (Chroma embeddings) + sparse (BM25), fused
with Reciprocal Rank Fusion, then an optional cross-encoder reranking pass
before cutting to the final K chunks returned to the generate node.
"""
import logging
from typing import Any, Dict, List

from app.config import settings
from app.retrieval.bm25_index import sparse_search
from app.retrieval.reranker import rerank
from app.vectorstore.chroma_client import dense_search, get_documents_by_family

logger = logging.getLogger("app.retrieval.hybrid_retriever")

_RRF_K = 60
# Safety ceiling on total chunks returned when a whole family is pinned in —
# keeps a pathologically large family from unboundedly growing the prompt.
_MAX_TOTAL_WITH_PINNED = 25


_BROAD_KEYWORDS = {
    "قارن", "مقارنة", "كل", "جميع", "باقات", "أنظمة", "تفاصيل", "مزايا", "شروط", "تجوال", "أسعار", "عروض",
    "compare", "comparison", "all", "packages", "details", "benefits", "terms", "roaming", "overview", "list", "plans"
}
_FOCUSED_KEYWORDS = {
    "كود", "تفعيل", "اشتراك", "إلغاء", "سعر", "ضريبة", "كام", "بكام", "شحن",
    "code", "ussd", "activate", "cancel", "tax", "price", "recharge", "cost"
}


def _determine_k_bounds(query: str, strategy: str = "", intent: str = "") -> tuple[int, int]:
    """Determine dynamic min_k and max_k based on query complexity, strategy, and intent."""
    q_lower = query.lower()
    is_broad = (
        intent in ("comparison", "package_inquiry")
        or strategy in ("TOOL_PLUS_RAG", "RAG_ONLY")
        or any(k in q_lower for k in _BROAD_KEYWORDS)
    )
    is_focused = (
        intent in ("activation_code", "price_calculation")
        or strategy in ("TOOL_EXACT", "TOOL_ACTIVATION", "TOOL_CALCULATION")
        or (any(k in q_lower for k in _FOCUSED_KEYWORDS) and not any(k in q_lower for k in _BROAD_KEYWORDS))
    )

    if is_broad:
        return max(5, settings.MIN_K), settings.MAX_K
    elif is_focused:
        return settings.MIN_K, min(4, settings.MAX_K)
    return settings.MIN_K, settings.MAX_K


def _filter_by_similarity(
    candidates: List[Dict[str, Any]],
    min_k: int,
    max_k: int,
    ratio_threshold: float = 0.60,
    cliff_gap: float = 0.22,
) -> List[Dict[str, Any]]:
    """Dynamically filter candidates based on normalized similarity score, relative
    cutoff threshold, and cliff/drop-off detection."""
    if not candidates:
        return []
    if len(candidates) <= min_k:
        return candidates

    top_score = candidates[0].get("similarity_score", 1.0)
    cutoff = top_score * ratio_threshold
    selected: List[Dict[str, Any]] = []
    prev_score = top_score

    for c in candidates:
        score = c.get("similarity_score", 0.0)
        if len(selected) < min_k:
            selected.append(c)
            prev_score = score
            continue

        # Cliff detection: sudden drop-off between consecutive candidate chunks
        if (prev_score - score) > (cliff_gap * top_score):
            break

        if score >= cutoff and len(selected) < max_k:
            selected.append(c)
            prev_score = score
        else:
            break

    return selected or candidates[:min_k]


def _rrf_fuse(dense: List[Dict[str, Any]], sparse: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    scores: Dict[str, float] = {}
    by_id: Dict[str, Dict[str, Any]] = {}
    for rank_list in (dense, sparse):
        for rank, doc in enumerate(rank_list):
            doc_id = doc["metadata"].get("chunk_id") or doc["content"][:50]
            scores[doc_id] = scores.get(doc_id, 0.0) + 1.0 / (_RRF_K + rank + 1)
            by_id[doc_id] = doc
    ranked_ids = sorted(scores, key=lambda i: scores[i], reverse=True)
    max_rrf = max(scores.values()) if scores else 1.0
    fused_docs = []
    for doc_id in ranked_ids:
        doc = dict(by_id[doc_id])
        raw_score = scores[doc_id]
        norm_score = raw_score / max_rrf if max_rrf > 0 else raw_score
        doc["rrf_score"] = round(raw_score, 5)
        doc["similarity_score"] = round(norm_score, 4)
        if "metadata" in doc:
            doc["metadata"] = dict(doc["metadata"])
            doc["metadata"]["similarity_score"] = round(norm_score, 4)
        fused_docs.append(doc)
    return fused_docs


def search(query: str, strategy: str = "", intent: str = "", category: str = "") -> List[Dict[str, Any]]:
    """Dynamic hybrid search: retrieves dense + sparse candidates, fuses with RRF,
    and dynamically selects the optimal number of chunks based on query complexity
    and relevance scores.

    When `category` is a resolved catalog family and `strategy` is
    TOOL_PLUS_RAG (strategy_router's "family known, no specific tier named" —
    i.e. a "list every package in X" question), every chunk belonging to that
    family is pinned into the result via a metadata filter rather than left to
    embedding-similarity ranking, which can drop a tier whose blended score
    falls just under the dynamic cutoff even though it's exactly what was
    asked for. Similarity search still runs and fills any remaining budget,
    so cross-family/supplementary chunks (tax rules, a compared family, etc.)
    can still surface alongside the pinned family.
    """
    dense_raw = dense_search(query, settings.TOP_K)
    dense = []
    for doc, dist in dense_raw:
        sim = max(0.0, 1.0 - (dist / 2.0)) if dist <= 2.0 else 1.0 / (1.0 + dist)
        d_item = {"content": doc.page_content, "metadata": dict(doc.metadata)}
        d_item["dense_score"] = round(sim, 4)
        dense.append(d_item)

    try:
        sparse_raw = sparse_search(query, settings.TOP_K)
        sparse = [doc for doc, _ in sparse_raw]
    except Exception as exc:
        logger.warning("BM25 sparse search failed, continuing dense-only: %s", exc)
        sparse = []

    fused = _rrf_fuse(dense, sparse)
    min_k, max_k = _determine_k_bounds(query, strategy=strategy, intent=intent)

    # Skip CPU cross-encoder reranker for deterministic tool strategies
    # (TOOL_EXACT, TOOL_ACTIVATION, TOOL_CALCULATION, TOOL_RECOMMENDATION) where deterministic
    # tools already hold 100% verified facts. RRF fusion (<15ms) is sufficient for supplementary context.
    should_rerank = (
        settings.CROSS_ENCODER_RERANKER_ENABLED
        and fused
        and strategy not in ("TOOL_EXACT", "TOOL_ACTIVATION", "TOOL_CALCULATION", "TOOL_RECOMMENDATION")
    )

    if should_rerank:
        try:
            candidate_pool_size = min(max_k + 4, getattr(settings, "RERANKER_TOP_N", 20))
            fused = rerank(
                query=query,
                candidates=fused[:candidate_pool_size],
                top_n=settings.FINAL_K,
                min_k=min_k,
                max_k=max_k,
                dynamic=settings.DYNAMIC_K_ENABLED,
                score_ratio_threshold=settings.DYNAMIC_SCORE_RATIO_THRESHOLD,
                cliff_gap=settings.DYNAMIC_CLIFF_GAP,
            )
        except Exception as exc:
            logger.warning("Cross-encoder reranking failed, using dynamic RRF slice: %s", exc)
            fused = _filter_by_similarity(
                fused,
                min_k=min_k,
                max_k=max_k,
                ratio_threshold=settings.DYNAMIC_SCORE_RATIO_THRESHOLD,
                cliff_gap=settings.DYNAMIC_CLIFF_GAP,
            ) if settings.DYNAMIC_K_ENABLED else fused[: settings.FINAL_K]
    else:
        # Fast path (deterministic tool strategies): use adaptive similarity filtering on RRF scores
        fused = _filter_by_similarity(
            fused,
            min_k=min_k,
            max_k=max_k,
            ratio_threshold=settings.DYNAMIC_SCORE_RATIO_THRESHOLD,
            cliff_gap=settings.DYNAMIC_CLIFF_GAP,
        ) if settings.DYNAMIC_K_ENABLED else fused[: settings.FINAL_K]

    if category and strategy == "TOOL_PLUS_RAG" and intent != "comparison":
        try:
            pinned = get_documents_by_family(category, package_tiers_only=True)
        except Exception as exc:
            logger.warning("Family-scoped pin fetch failed for %s, using ranked results only: %s", category, exc)
            pinned = []
        if pinned:
            pinned = pinned[:_MAX_TOTAL_WITH_PINNED]
            pinned_ids = {p["metadata"].get("chunk_id") for p in pinned}
            supplement = [d for d in fused if d["metadata"].get("chunk_id") not in pinned_ids]
            budget = max(0, _MAX_TOTAL_WITH_PINNED - len(pinned))
            return pinned + supplement[:budget]

    return fused
