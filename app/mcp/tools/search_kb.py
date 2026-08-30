"""
app/mcp/tools/search_kb.py
--------------------------
MCP tool: search_knowledge_base
Performs two-stage hybrid retrieval & reranking against the e& Egypt KB.
"""
from typing import Any, Dict, List, Optional

from app.config import settings


def search_knowledge_base_tool(
    query: str,
    service: Optional[str] = None,
    category: Optional[str] = None,
    top_k: int = 5,
) -> Dict[str, Any]:
    """
    Retrieve relevant KB passages for a query using hybrid retrieval and two-stage reranking.

    Args:
        query: Search query (Arabic or English).
        service: Optional service filter (Hekaya, Emerald, Prepaid, DataLine).
        category: Optional category filter.
        top_k: Number of results to return.

    Returns:
        Dict with "results" list of {text, score, source, package_name, category, service, chunk_id, metadata} dicts.
    """
    try:
        from app.retrieval.hybrid_retriever import HybridRetriever
        from app.retrieval.reranker import CandidateReranker
        from app.retrieval.cross_encoder_reranker import CrossEncoderReranker

        retriever = HybridRetriever()
        candidate_reranker = CandidateReranker()
        cross_reranker = CrossEncoderReranker()

        # Step 1: Hybrid retrieval
        fetch_k = max(top_k * 2, settings.TOP_K)
        docs = retriever.search(query, top_k=fetch_k)

        # Step 2: Heuristic business-rule candidate reranking
        docs = candidate_reranker.rerank(
            documents=docs,
            query=query,
            service=service,
            category=category,
            final_k=fetch_k,
        )

        # Step 3: Cross-encoder semantic reranking (if enabled)
        if settings.CROSS_ENCODER_RERANKER_ENABLED:
            docs = cross_reranker.rerank(
                documents=docs,
                query=query,
                final_k=top_k,
            )
        else:
            docs = docs[:top_k]

        results = []
        for doc in docs:
            score = doc.metadata.get("cross_encoder_score")
            if score is None:
                score = doc.metadata.get("rerank_score", doc.metadata.get("rrf_score", 0.0))

            results.append({
                "text": doc.page_content[:1000],
                "score": float(score) if score is not None else 0.0,
                "source": doc.metadata.get("source_file", "unknown"),
                "package_name": doc.metadata.get("package_name") or doc.metadata.get("product", ""),
                "category": doc.metadata.get("category", ""),
                "service": doc.metadata.get("service", ""),
                "chunk_id": doc.metadata.get("chunk_id", ""),
                "metadata": {
                    k: v for k, v in doc.metadata.items()
                    if k not in ("text", "page_content")
                },
            })

        return {
            "query": query,
            "count": len(results),
            "service_filter": service,
            "results": results,
        }

    except Exception as exc:
        return {"error": str(exc), "query": query, "results": []}
