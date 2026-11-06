"""
Genuine embedding-based semantic chunking: groups a list of short, independent
text units by consecutive cosine similarity, splitting where the topic
actually shifts — not by a fixed bullet-count or character-count cutoff.

Used only for catalog content that IS a flat list of loosely related,
independent points (Emerald's terms & conditions, written as independent
retrievable facts). A single-fact catalog entry (one package tier, one named
benefit) is already one coherent unit and is kept whole elsewhere in
catalog_renderer.py — splitting it further would fragment a complete answer
across chunks for no benefit, which is the opposite of what chunking here is
supposed to achieve.
"""
from typing import Callable, List, Sequence, TypeVar

import numpy as np

from app.embeddings.embedding_service import get_embedding_function

T = TypeVar("T")


def _cosine(a: List[float], b: List[float]) -> float:
    va, vb = np.array(a), np.array(b)
    denom = (np.linalg.norm(va) * np.linalg.norm(vb)) or 1e-9
    return float(np.dot(va, vb) / denom)


def semantic_group(
    items: Sequence[T], text_fn: Callable[[T], str], similarity_threshold: float = 0.55
) -> List[List[T]]:
    """Greedily group consecutive items into the same chunk while their
    embedding similarity stays >= similarity_threshold; start a new chunk
    as soon as similarity drops (a topic shift)."""
    if not items:
        return []
    embedder = get_embedding_function()
    vectors = embedder.embed_documents([text_fn(item) for item in items])

    groups: List[List[T]] = [[items[0]]]
    for i in range(1, len(items)):
        if _cosine(vectors[i - 1], vectors[i]) >= similarity_threshold:
            groups[-1].append(items[i])
        else:
            groups.append([items[i]])
    return groups
