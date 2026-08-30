import concurrent.futures
from typing import Any, Dict, List, Optional, Tuple
from langchain_core.documents import Document

from app.config import settings
from app.retrieval.keyword_retriever import KeywordRetriever
from app.retrieval.semantic_retriever import SemanticRetriever


class HybridRetriever:
    """
    True Hybrid Retriever combining Dense Vector Search (ChromaDB)
    and Sparse Lexical Search (BM25) via Reciprocal Rank Fusion (RRF)
    with concurrent parallel execution.
    """

    def __init__(self):
        self._semantic: Optional[SemanticRetriever] = None
        self._keyword_retriever: Optional[KeywordRetriever] = None

    @property
    def semantic(self) -> SemanticRetriever:
        if self._semantic is None:
            self._semantic = SemanticRetriever()
        return self._semantic

    def _get_keyword_retriever(self) -> KeywordRetriever:
        if self._keyword_retriever is None:
            # Load indexed corpus chunks once from ChromaDB for BM25 indexing
            collection_data = self.semantic.collection.get()
            all_documents = []

            texts = collection_data.get("documents") or []
            metadatas = collection_data.get("metadatas") or []

            for i, text in enumerate(texts):
                meta = metadatas[i] if i < len(metadatas) and metadatas[i] else {}
                all_documents.append(
                    Document(page_content=text, metadata=dict(meta))
                )

            self._keyword_retriever = KeywordRetriever(all_documents)

        return self._keyword_retriever

    def reload_keyword_index(self):
        """Force reload of BM25 index after new documents are ingested."""
        self._keyword_retriever = None
        self._get_keyword_retriever()

    def search(
        self,
        query: str,
        top_k: Optional[int] = None,
        exclude_legacy: bool = True,
    ) -> List[Document]:
        if not query or not query.strip():
            return []

        limit = top_k or settings.TOP_K

        # Execute Dense Semantic Search and Sparse BM25 Search concurrently
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
            future_semantic = executor.submit(self.semantic.search, query, limit * 2, exclude_legacy)
            future_keyword = executor.submit(self._get_keyword_retriever().search, query, limit * 2, exclude_legacy)

            try:
                semantic_docs = future_semantic.result()
            except Exception:
                semantic_docs = []

            try:
                keyword_docs = future_keyword.result()
            except Exception:
                keyword_docs = []

        # Reciprocal Rank Fusion (RRF)
        # RRF Score = sum( 1 / (60 + rank_i) )
        rrf_scores: Dict[Tuple[str, Any, str], float] = {}
        doc_map: Dict[Tuple[str, Any, str], Document] = {}

        def _doc_key(doc: Document) -> Tuple[str, Any, str]:
            return (
                doc.metadata.get("source_file", "unknown"),
                doc.metadata.get("page", 0),
                doc.page_content[:120].strip()
            )

        # Score dense semantic docs
        for rank, doc in enumerate(semantic_docs):
            key = _doc_key(doc)
            rrf_scores[key] = rrf_scores.get(key, 0.0) + (1.0 / (60 + rank + 1))
            if key not in doc_map:
                doc_map[key] = doc

        # Score sparse keyword docs
        for rank, doc in enumerate(keyword_docs):
            key = _doc_key(doc)
            rrf_scores[key] = rrf_scores.get(key, 0.0) + (1.0 / (60 + rank + 1))
            if key not in doc_map:
                doc_map[key] = doc

        # Sort combined documents by fused RRF score
        sorted_keys = sorted(
            rrf_scores.keys(),
            key=lambda k: rrf_scores[k],
            reverse=True
        )

        fused_documents = []
        for key in sorted_keys[:limit]:
            doc = doc_map[key]
            fused_meta = dict(doc.metadata)
            fused_meta["rrf_score"] = round(rrf_scores[key], 5)
            fused_meta["semantic_candidate"] = any(_doc_key(d) == key for d in semantic_docs)
            fused_meta["keyword_candidate"] = any(_doc_key(d) == key for d in keyword_docs)

            fused_documents.append(
                Document(
                    page_content=doc.page_content,
                    metadata=fused_meta
                )
            )

        return fused_documents