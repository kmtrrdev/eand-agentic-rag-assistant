"""Cached embedding model singleton — loading a sentence-transformers model is
expensive, so every caller shares one instance for the life of the process."""
import functools

from langchain_huggingface import HuggingFaceEmbeddings

from app.config import settings


def _best_device() -> str:
    """Use the GPU when a CUDA-enabled torch build is actually installed;
    fall back to CPU otherwise instead of crashing on a CPU-only build."""
    try:
        import torch

        return "cuda" if torch.cuda.is_available() else "cpu"
    except Exception:
        return "cpu"


@functools.lru_cache(maxsize=1)
def get_embedding_function() -> HuggingFaceEmbeddings:
    device = _best_device()
    try:
        return HuggingFaceEmbeddings(
            model_name=settings.EMBEDDING_MODEL,
            model_kwargs={"device": device, "local_files_only": True},
            encode_kwargs={"normalize_embeddings": True},
        )
    except Exception:
        return HuggingFaceEmbeddings(
            model_name=settings.EMBEDDING_MODEL,
            model_kwargs={"device": device},
            encode_kwargs={"normalize_embeddings": True},
        )
