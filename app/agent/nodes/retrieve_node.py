from typing import Any, Dict, List

from app.agent.state import AgentState
from app.agent.trace import elapsed_ms, now, step
from app.retrieval.hybrid_retriever import search


def retrieve_node(state: AgentState) -> Dict[str, Any]:
    start = now()
    # query_rewrite_node always runs immediately before this node (see
    # graph.py) and always populates retrieval_query — the plain question
    # fallback here only guards against calling this node in isolation (e.g.
    # a unit test) without going through the graph.
    query = state.get("retrieval_query") or state.get("question", "")
    strategy = state.get("strategy", "")
    intent = state.get("intent", "")
    category = state.get("category", "")

    try:
        results = search(query, strategy=strategy, intent=intent, category=category)
    except Exception:
        results = []

    sources: List[Dict[str, Any]] = []
    context_parts: List[str] = []
    for doc in results:
        meta = doc.get("metadata", {})
        content = doc.get("content", "")
        context_parts.append(content)
        sources.append({
            "source": meta.get("source", "") or "e& Egypt Knowledge Base",
            "page": meta.get("page", ""),
            "category": meta.get("category", ""),
            "product": meta.get("product", ""),
            "snippet": content,  # Full complete chunk text
            "chunk_id": meta.get("chunk_id", ""),
            "similarity_score": float(meta.get("similarity_score") or doc.get("similarity_score")) if (meta.get("similarity_score") or doc.get("similarity_score")) is not None else None,
        })

    raw_top = results[0].get("similarity_score") if results else None
    top_score = float(raw_top) if raw_top is not None else None
    trace_details: Dict[str, Any] = {"selected_count": len(results)}
    if top_score is not None:
        trace_details["top_similarity"] = top_score

    return {
        "context": "\n\n---\n\n".join(context_parts),
        "sources": sources,
        "workflow_trace": [step(
            "retrieve", "6. Hybrid Retrieval", "٦. استرجاع هجين متوازي",
            description_en=f"Retrieved {len(results)} chunks adaptively by similarity (dense + BM25 + RRF).",
            badge="Dynamic", status="completed",
            details=trace_details,
            latency_ms=elapsed_ms(start),
        )],
    }
