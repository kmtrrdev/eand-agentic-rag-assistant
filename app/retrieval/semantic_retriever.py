from typing import List, Optional
from langchain_core.documents import Document

from app.config import settings
from app.embeddings.embedding_service import EmbeddingService
from app.vectorstore.chroma_client import get_collection

import logging
logger = logging.getLogger("etisalat_kb.retrieval.semantic")


class SemanticRetriever:
    """Dense Vector Retriever using ChromaDB and Multilingual Embeddings."""

    def __init__(self):
        self.embedding_service = EmbeddingService()

    @property
    def collection(self):
        return get_collection()

    def search(
        self,
        query: str,
        top_k: Optional[int] = None,
        exclude_legacy: bool = True,
    ) -> List[Document]:
        """
        Perform dense vector search.

        Args:
            query: User query string.
            top_k: Number of results to return.
            exclude_legacy: When True (default), applies a ChromaDB metadata
                filter to exclude chunks tagged plan_status='legacy'. This
                prevents retired Hekaya Mixat naming-system chunks from entering
                the candidate pool for current-plan queries.
                Set to False only when the user explicitly asks about
                historical/deprecated plans.
        """
        if not query or not query.strip():
            return []

        limit = top_k or settings.TOP_K

        try:
            query_embedding = self.embedding_service.embed_text(query.strip())

            query_kwargs = {
                "query_embeddings": [query_embedding],
                "n_results": limit,
            }

            # Apply metadata filter to exclude legacy chunks from candidate pool.
            # Graceful degradation: if the collection predates the plan_status field
            # (i.e. --rebuild hasn't been run yet), ChromaDB may raise an error on
            # the $ne operator — fall back to an unfiltered query in that case.
            if exclude_legacy:
                query_kwargs["where"] = {"plan_status": {"$ne": "legacy"}}

            try:
                results = self.collection.query(**query_kwargs)
            except Exception as filter_exc:
                # ChromaDB raises if no documents match the where filter OR if
                # the metadata field doesn't exist yet (pre-rebuild collection).
                logger.warning(
                    "[SemanticRetriever] where-filter query failed (%s: %s); "
                    "retrying without legacy filter (run --rebuild to fix permanently).",
                    type(filter_exc).__name__, filter_exc,
                )
                query_kwargs.pop("where", None)
                results = self.collection.query(**query_kwargs)

        except Exception as exc:
            logger.error("[SemanticRetriever] Query error: %s", exc)
            return []

        documents = []
        if not results or not results.get("documents") or not results["documents"][0]:
            return documents

        for i, text in enumerate(results["documents"][0]):
            metadata = {}
            if results.get("metadatas") and results["metadatas"][0]:
                metadata = dict(results["metadatas"][0][i] or {})

            if results.get("distances") and results["distances"][0]:
                # In ChromaDB cosine distance: similarity = 1.0 - distance
                dist = float(results["distances"][0][i])
                metadata["distance"] = dist
                metadata["semantic_similarity"] = round(max(0.0, 1.0 - dist), 4)

            documents.append(
                Document(
                    page_content=text,
                    metadata=metadata
                )
            )

        return documents