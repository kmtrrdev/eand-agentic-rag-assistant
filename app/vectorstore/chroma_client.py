"""Persistent Chroma vector store — one shared collection built from the
catalog (see app/ingestion/ingest.py)."""
import functools
from typing import Any, Dict, List, Tuple

from langchain_chroma import Chroma

from app.config import settings
from app.embeddings.embedding_service import get_embedding_function


@functools.lru_cache(maxsize=1)
def get_vectorstore() -> Chroma:
    return Chroma(
        collection_name=settings.COLLECTION_NAME,
        embedding_function=get_embedding_function(),
        persist_directory=settings.CHROMA_PATH,
    )


def rebuild_collection(chunks: List[Tuple[str, Dict[str, Any]]]) -> int:
    """Drop and recreate the collection from scratch, then add every chunk."""
    store = get_vectorstore()
    try:
        store.delete_collection()
    except Exception:
        pass
    get_vectorstore.cache_clear()
    store = get_vectorstore()

    texts = [text for text, _ in chunks]
    metadatas = [meta for _, meta in chunks]
    # chunk_id is set explicitly for any chunk_type that can render more than
    # one chunk per product (e.g. semantically-split terms & conditions);
    # falling back to tier_id/product alone would collide in that case.
    ids: List[str] = []
    seen: Dict[str, int] = {}
    for meta in metadatas:
        base = f"{meta['family']}::{meta.get('chunk_id') or meta.get('tier_id') or meta['product']}"
        seen[base] = seen.get(base, 0) + 1
        ids.append(base if seen[base] == 1 else f"{base}::{seen[base]}")
    store.add_texts(texts=texts, metadatas=metadatas, ids=ids)
    return len(texts)


def dense_search(query: str, k: int) -> List[Tuple[Any, float]]:
    """Returns (Document, distance) pairs — lower distance is more similar."""
    return get_vectorstore().similarity_search_with_score(query, k=k)


def get_all_documents() -> List[Dict[str, Any]]:
    """Fetch every stored chunk (for building the BM25 sparse index)."""
    raw = get_vectorstore().get(include=["documents", "metadatas"])
    return [
        {"id": doc_id, "content": doc, "metadata": meta}
        for doc_id, doc, meta in zip(raw["ids"], raw["documents"], raw["metadatas"])
    ]


def get_documents_by_family(family_id: str, package_tiers_only: bool = True) -> List[Dict[str, Any]]:
    """Fetch chunks tagged with this catalog family id via a metadata filter.
    When package_tiers_only=True, restricts results to core package tiers,
    family overviews, and tier groups, avoiding bloating the prompt with
    glossary definitions and micro-rules.
    """
    if not family_id:
        return []
    raw = get_vectorstore().get(where={"family": family_id}, include=["documents", "metadatas"])
    all_docs = [
        {"content": doc, "metadata": meta}
        for doc, meta in zip(raw["documents"], raw["metadatas"])
    ]
    if package_tiers_only:
        allowed = {"package_tier", "family_overview", "tier_group"}
        filtered = [d for d in all_docs if d.get("metadata", {}).get("chunk_type") in allowed]
        if filtered:
            return filtered
    return all_docs
