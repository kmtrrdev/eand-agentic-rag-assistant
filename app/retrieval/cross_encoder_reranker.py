"""
app/retrieval/cross_encoder_reranker.py
---------------------------------------
Cross-Encoder semantic reranker for post-RRF document scoring.

Architecture:
    Dense + BM25 -> RRF -> CandidatePool
        -> Heuristic CandidateReranker (device/service/budget filter)
        -> [if CROSS_ENCODER_RERANKER_ENABLED] CrossEncoder -> Final Top-K
        -> [else] heuristic top-K directly

The CrossEncoder is a singleton loaded once at startup. If the model
is unavailable or the feature flag is off, the pipeline gracefully falls
back to the heuristic reranker output.

Model: cross-encoder/ms-marco-MiniLM-L-6-v2 (default)
  - Fast, effective for passage ranking
  - ~80MB download, CPU-compatible
  - Returns relevance score in (-inf, +inf); higher = more relevant
"""
import logging
from typing import List, Optional

from langchain_core.documents import Document

from app.config import settings

logger = logging.getLogger("retrieval.cross_encoder")

_cross_encoder = None
_cross_encoder_loaded = False


def _get_cross_encoder():
    """Lazy singleton loader for the CrossEncoder model."""
    global _cross_encoder, _cross_encoder_loaded
    if _cross_encoder_loaded:
        return _cross_encoder
    _cross_encoder_loaded = True

    if not settings.CROSS_ENCODER_RERANKER_ENABLED:
        logger.info("Cross-encoder reranker disabled (CROSS_ENCODER_RERANKER_ENABLED=false)")
        return None

    try:
        from sentence_transformers import CrossEncoder
        model_name = settings.RERANKER_MODEL
        logger.info(f"Loading cross-encoder model: {model_name}")
        _cross_encoder = CrossEncoder(model_name, max_length=512)
        logger.info(f"Cross-encoder ready: {model_name}")
    except ImportError:
        logger.warning("sentence-transformers not available; cross-encoder disabled.")
    except Exception as exc:
        logger.warning(f"Cross-encoder load failed ({exc}); falling back to heuristic.")

    return _cross_encoder


class CrossEncoderReranker:
    """
    Two-stage reranker:
      Stage 1: Heuristic CandidateReranker (telecom business signals).
      Stage 2: CrossEncoder semantic scoring (if enabled & model loaded).

    Usage:
        reranker = CrossEncoderReranker()
        docs = reranker.rerank(candidates, query=q, final_k=5)
    """

    def __init__(self) -> None:
        # Set on every rerank() call so callers can tell whether this pass actually
        # used the cross-encoder model or silently degraded to heuristic order —
        # previously that distinction only reached a log line, invisible to the
        # response/eval harness (a production deployment where sentence-transformers
        # fails to install, or the ~80MB model download fails at cold-start, would
        # silently run heuristic-only reranking with no observable signal anywhere
        # downstream of the log file).
        self.last_call_used_model: bool = False

    def rerank(
        self,
        documents: List[Document],
        query: str,
        final_k: int = 5,
    ) -> List[Document]:
        """
        Rerank documents using cross-encoder semantic scoring.

        Falls back gracefully to the input document order (already heuristic-ranked)
        if cross-encoder is unavailable. Check `self.last_call_used_model` after
        calling this to know whether the fallback actually fired.

        Args:
            documents: Candidate documents (already heuristic-ranked, deduplicated).
            query: The search query to score against.
            final_k: Number of documents to return.

        Returns:
            Top final_k documents sorted by cross-encoder score descending.
        """
        self.last_call_used_model = False
        if not documents:
            return []

        encoder = _get_cross_encoder()

        if encoder is None:
            # Graceful fallback: return top final_k from heuristic order
            return documents[:final_k]

        try:
            pairs = [(query, doc.page_content[:512]) for doc in documents]
            scores = encoder.predict(pairs)
            self.last_call_used_model = True

            # Boost cross-encoder score if document contains exact query entities
            from app.retrieval.reranker import _extract_query_entities
            query_entities = _extract_query_entities(query)

            scored_docs = []
            for score, doc in zip(scores, documents):
                final_score = float(score)
                doc_content = doc.page_content.lower()
                doc_plan = str(doc.metadata.get("plan_name", "")).lower()
                if query_entities:
                    for entity in query_entities:
                        e_low = entity.lower()
                        if e_low in doc_plan or e_low in doc_content:
                            final_score += 10.0
                scored_docs.append((final_score, doc))

            scored = sorted(
                scored_docs,
                key=lambda x: float(x[0]),
                reverse=True,
            )

            is_comparison = any(k in query.lower() for k in ["قارن", "مقارنة", "compare", "vs", "versus", "difference", "فرق"])

            # Symmetrical Dual-Entity Slotting for Comparisons
            if is_comparison and len(query_entities) >= 2:
                selected = []
                entity_docs = {e: [] for e in query_entities}
                for score, doc in scored:
                    c_low = doc.page_content.lower()
                    p_low = str(doc.metadata.get("plan_name", "")).lower()
                    for e in query_entities:
                        if e.lower() in p_low or e.lower() in c_low:
                            entity_docs[e].append(doc)
                for e in query_entities:
                    if entity_docs[e]:
                        selected.append(entity_docs[e][0])
                for score, doc in scored:
                    if doc not in selected and len(selected) < final_k:
                        selected.append(doc)
                return selected

            # Annotate metadata with cross-encoder score for observability
            result = []
            for score, doc in scored[:final_k]:
                doc.metadata["cross_encoder_score"] = round(float(score), 4)
                result.append(doc)

            return result

        except Exception as exc:
            logger.warning(f"Cross-encoder inference failed ({exc}); returning heuristic order.")
            return documents[:final_k]
