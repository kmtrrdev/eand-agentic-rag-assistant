"""Optional cross-encoder reranking stage — a stronger but slower relevance
model that re-scores the RRF-fused candidates before the final cut."""
import functools
import re
from typing import Any, Dict, List, Optional, Tuple

from app.config import settings


@functools.lru_cache(maxsize=1)
def _get_model():
    from sentence_transformers import CrossEncoder

    from app.embeddings.embedding_service import _best_device

    device = _best_device()
    try:
        return CrossEncoder(settings.RERANKER_MODEL, local_files_only=True, device=device)
    except Exception:
        return CrossEncoder(settings.RERANKER_MODEL, device=device)


def warmup_reranker():
    """Warm up the cross-encoder model so first user query has zero weight-loading lag."""
    try:
        model = _get_model()
        model.predict([("warmup", "etisalat knowledge base")])
    except Exception:
        pass


def rerank(
    query: str,
    candidates: List[Dict[str, Any]],
    top_n: int = 5,
    min_k: int = 2,
    max_k: int = 10,
    dynamic: bool = True,
    score_ratio_threshold: float = 0.60,
    cliff_gap: Optional[float] = None,
) -> List[Dict[str, Any]]:
    """Re-score RRF-fused candidates with the cross-encoder, blend its score
    with the incoming RRF rank, and dynamically select high-relevance chunks.

    If dynamic=True, chunks with blended scores meeting the relative threshold
    (w.r.t top candidate) and not severed by a sharp similarity cliff are kept
    up to max_k (bounded below by min_k).
    """
    if not candidates:
        return candidates
    model = _get_model()
    pairs: List[Tuple[str, str]] = [(query, c["content"]) for c in candidates]
    scores = list(model.predict(pairs))

    lo, hi = min(scores), max(scores)
    spread = (hi - lo) or 1.0

    # If query is mostly Arabic, ms-marco (English cross-encoder) is less reliable;
    # give stronger weight to the multilingual dense + BM25 RRF ranking.
    has_arabic = bool(re.search(r"[\u0600-\u06FF]", query))
    w = max(0.60, settings.RERANKER_RRF_BLEND_WEIGHT) if has_arabic else settings.RERANKER_RRF_BLEND_WEIGHT

    blended: List[Tuple[Dict[str, Any], float]] = []
    for rrf_rank, (candidate, score) in enumerate(zip(candidates, scores)):
        ce_norm = (score - lo) / spread
        rrf_component = 1.0 / (rrf_rank + 1)
        blended_score = (1 - w) * ce_norm + w * rrf_component
        blended.append((candidate, blended_score))

    ranked = sorted(blended, key=lambda pair: pair[1], reverse=True)

    if not dynamic or not getattr(settings, "DYNAMIC_K_ENABLED", True):
        res = []
        for c, score in ranked[:top_n]:
            c_copy = dict(c)
            s_val = float(round(score, 4))
            c_copy["similarity_score"] = s_val
            if "metadata" in c_copy:
                c_copy["metadata"] = dict(c_copy["metadata"])
                c_copy["metadata"]["similarity_score"] = s_val
            res.append(c_copy)
        return res

    top_score = float(ranked[0][1]) if ranked else 1.0
    # Use an adaptive cutoff: lower threshold if Arabic to preserve top candidates
    effective_threshold = score_ratio_threshold * 0.85 if has_arabic else score_ratio_threshold
    cutoff = top_score * effective_threshold
    effective_cliff_gap = float(cliff_gap if cliff_gap is not None else getattr(settings, "DYNAMIC_CLIFF_GAP", 0.22))

    selected: List[Dict[str, Any]] = []
    prev_score = top_score
    for c, score in ranked:
        s_float = float(score)
        c_copy = dict(c)
        s_val = float(round(s_float, 4))
        c_copy["similarity_score"] = s_val
        if "metadata" in c_copy:
            c_copy["metadata"] = dict(c_copy["metadata"])
            c_copy["metadata"]["similarity_score"] = s_val

        if len(selected) < min_k:
            selected.append(c_copy)
            prev_score = s_float
            continue

        # Cliff detection: sudden drop-off between consecutive candidate chunks
        if (prev_score - s_float) > (effective_cliff_gap * top_score):
            break

        if s_float >= cutoff and len(selected) < max_k:
            selected.append(c_copy)
            prev_score = s_float
        else:
            break

    return selected or [c for c, _ in ranked[:min_k]]
