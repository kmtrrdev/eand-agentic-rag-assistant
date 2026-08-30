import threading
import chromadb
from app.config import settings

_thread_local = threading.local()
_chroma_lock = threading.Lock()


def get_chroma_client():
    """Return a thread-local PersistentClient to ensure thread safety across concurrent queries."""
    if not hasattr(_thread_local, "client"):
        with _chroma_lock:
            _thread_local.client = chromadb.PersistentClient(path=settings.CHROMA_PATH)
    return _thread_local.client


def get_collection():
    """Return the e& Egypt knowledge base collection for the current thread."""
    if not hasattr(_thread_local, "collection"):
        client = get_chroma_client()
        with _chroma_lock:
            _thread_local.collection = client.get_or_create_collection(
                name=settings.COLLECTION_NAME,
                metadata={
                    "description": "e& Egypt Agentic Knowledge Base"
                }
            )
    return _thread_local.collection