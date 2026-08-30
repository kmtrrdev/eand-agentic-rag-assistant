import hashlib
from typing import List
from langchain_core.documents import Document

from app.embeddings.embedding_service import EmbeddingService
from app.vectorstore.chroma_client import get_chroma_client, get_collection
from app.config import settings


def generate_deterministic_chunk_id(doc: Document) -> str:
    """
    Generate a stable, deterministic ID for a chunk based on its content and source.

    Deliberately does NOT use metadata["chunk_id"] (TelecomStructureChunker assigns
    that as a running index over the ENTIRE corpus, not per source file) — re-ingesting
    a subset of PDFs, adding a new PDF, or any change in glob() ordering shifts every
    later file's chunk_id, so IDs built from it changed across ingestion runs even when
    the actual chunk content didn't, defeating idempotent upsert (stale duplicate/orphaned
    rows accumulate in Chroma instead of being cleanly replaced). source_file + page +
    content_hash alone is already deterministic and stable regardless of ingestion
    order — two chunks colliding here would mean genuinely identical content on the
    same page, which is correct to treat as one chunk.
    """
    source = doc.metadata.get("source_file", "unknown")
    page = doc.metadata.get("page", 0)
    content_hash = hashlib.sha256(doc.page_content.strip().encode("utf-8")).hexdigest()[:16]
    return f"{source}_p{page}_{content_hash}"


class IndexManager:
    def __init__(self):
        self.embedding_service = EmbeddingService()

    @property
    def collection(self):
        return get_collection()

    def clear_collection(self):
        """Cleanly delete all documents from the collection to allow fresh rebuild."""
        client = get_chroma_client()
        try:
            client.delete_collection(name=settings.COLLECTION_NAME)
        except Exception:
            pass
        # Clear thread local cached collection
        from app.vectorstore.chroma_client import _thread_local
        if hasattr(_thread_local, "collection"):
            delattr(_thread_local, "collection")

    def add_documents(self, documents: List[Document], batch_size: int = 64) -> int:
        """
        Add or upsert documents into ChromaDB idempotently using deterministic IDs.
        Ingesting the same documents multiple times will NOT create duplicate chunks.
        """
        if not documents:
            return 0

        total_added = 0
        for i in range(0, len(documents), batch_size):
            batch = documents[i:i + batch_size]
            texts = [doc.page_content for doc in batch]
            embeddings = self.embedding_service.embed_documents(batch)

            ids = [generate_deterministic_chunk_id(doc) for doc in batch]

            metadatas = []
            for doc in batch:
                meta = dict(doc.metadata)
                # Ensure all metadata values are primitive types supported by Chroma
                clean_meta = {}
                for k, v in meta.items():
                    if isinstance(v, (str, int, float, bool)):
                        clean_meta[k] = v
                    elif v is None:
                        clean_meta[k] = ""
                    else:
                        clean_meta[k] = str(v)
                metadatas.append(clean_meta)

            self.collection.upsert(
                ids=ids,
                documents=texts,
                embeddings=embeddings,
                metadatas=metadatas
            )
            total_added += len(batch)

        print(f"Successfully upserted {total_added} chunks into ChromaDB.")
        return total_added