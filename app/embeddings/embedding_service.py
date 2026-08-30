from typing import List, Optional
from langchain_core.documents import Document
from langchain_huggingface import HuggingFaceEmbeddings

from app.config import settings

_cached_embedding_model: Optional[HuggingFaceEmbeddings] = None


def get_embedding_model() -> HuggingFaceEmbeddings:
    """
    Get or create the singleton HuggingFace embeddings model.
    Default: sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2
    Provides high performance and accurate semantic similarity across Arabic and English.
    """
    global _cached_embedding_model
    if _cached_embedding_model is None:
        if settings.EMBEDDING_PROVIDER == "sentence_transformers":
            model_name = settings.EMBEDDING_MODEL or "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
            _cached_embedding_model = HuggingFaceEmbeddings(
                model_name=model_name,
                model_kwargs={"device": "cpu"},
                encode_kwargs={"normalize_embeddings": True},
            )
        else:
            raise ValueError(
                f"Unsupported embedding provider: {settings.EMBEDDING_PROVIDER}"
            )
    return _cached_embedding_model


class EmbeddingService:
    def __init__(self):
        self.model = get_embedding_model()

    def embed_text(self, text: str) -> List[float]:
        return self.model.embed_query(text)

    def embed_documents(self, documents: List[Document]) -> List[List[float]]:
        texts = [doc.page_content for doc in documents]
        return self.model.embed_documents(texts)