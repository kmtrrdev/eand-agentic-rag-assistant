"""Sparse lexical retrieval (BM25) over the same chunks stored in Chroma, with
advanced Arabic normalization, morphological prefix/suffix stripping, and
telecom domain synonym canonicalization.
"""
import functools
import re
from typing import Any, Dict, List, Set, Tuple

from rank_bm25 import BM25Okapi

from app.vectorstore.chroma_client import get_all_documents

_ARABIC_DIACRITICS = re.compile(r"[ؗ-ًؚ-ْٰۖ-ۭـ]")

# Conversational stop words that shouldn't distort lexical scoring
_QUERY_STOPWORDS: Set[str] = {
    "اعملي", "اعمل", "عايز", "عايزه", "عايزة", "عاوز", "عاوزه", "عاوزة",
    "بستخدم", "استخدم", "باستخدام", "اكتر", "أكتر", "اكبر", "أكبر", "اقل", "أقل",
    "احسن", "أحسن", "افضل", "أفضل", "ممكن", "لو", "سمحت", "قولي", "عرفني",
    "يعني", "عشان", "علشان", "انا", "أنا", "انت", "إنت", "هو", "هي", "ف", "في", "من", "على", "علي"
}

_SYNONYM_MAP: Dict[str, List[str]] = {
    "دقايق": ["دقيق", "مكالم", "وحدات", "دقايق", "مكالمات", "calls", "minutes"],
    "دقائق": ["دقيق", "مكالم", "وحدات", "دقايق", "مكالمات", "calls", "minutes"],
    "دقيقه": ["دقيق", "مكالم", "وحدات", "دقايق", "مكالمات", "calls", "minutes"],
    "مكالمات": ["مكالم", "دقيق", "وحدات", "دقايق", "مكالمات", "calls", "minutes"],
    "مكالمه": ["مكالم", "دقيق", "وحدات", "دقايق", "مكالمات", "calls", "minutes"],
    "مكس": ["مكس", "وحدات", "مكالم", "نت", "mix", "mixat"],
    "مكسات": ["مكس", "وحدات", "مكالم", "نت", "mix", "mixat"],
    "نت": ["نت", "انترنت", "بيانات", "ميجا", "جيجا", "data", "internet"],
    "انترنت": ["نت", "انترنت", "بيانات", "ميجا", "جيجا", "data", "internet"],
    "بيانات": ["نت", "انترنت", "بيانات", "data", "internet"],
    "باقه": ["باق", "باقه", "باقات", "plan", "package"],
    "باقات": ["باق", "باقه", "باقات", "plan", "package"],
    "جيجا": ["جيجا", "gb", "gigabyte"],
    "ميجا": ["ميجا", "mb", "megabyte"],
}


def _normalize_arabic(text: str) -> str:
    text = _ARABIC_DIACRITICS.sub("", text)
    text = re.sub(r"[إأآا]", "ا", text)
    text = text.replace("ى", "ي").replace("ة", "ه")
    return text


def _strip_affixes(token: str) -> str:
    """Strip Arabic prefixes (proclitics) and suffixes so words like 'لباقه',
    'بالمكالمات', 'للمكالمات' reduce to their base noun."""
    if len(token) <= 3:
        return token

    # Strip compound prefixes
    for pfx in ("وال", "فال", "بال", "كال", "لل"):
        if token.startswith(pfx) and len(token) > len(pfx) + 2:
            token = token[len(pfx):]
            break

    # Strip definite article
    if token.startswith("ال") and len(token) > 4:
        token = token[2:]

    # Strip single-letter proclitics: ب, ل, و, ف, ك
    elif token[0] in ("ب", "ل", "و", "ف", "ك") and len(token) > 4:
        token = token[1:]

    # Strip common suffixes
    for sfx in ("ات", "ين", "ون", "ها", "هم", "كم", "نا", "ية", "يه"):
        if token.endswith(sfx) and len(token) > len(sfx) + 2:
            token = token[:-len(sfx)]
            break

    return token


def tokenize(text: str, is_query: bool = False) -> List[str]:
    text = _normalize_arabic((text or "").lower())
    raw_tokens = re.findall(r"[\w\*#]+", text)
    tokens: List[str] = []

    for t in raw_tokens:
        if is_query and t in _QUERY_STOPWORDS and len(raw_tokens) > 2:
            continue
        tokens.append(t)
        base = _strip_affixes(t)
        if base != t:
            tokens.append(base)

        # Synonym expansion
        if t in _SYNONYM_MAP:
            tokens.extend(_SYNONYM_MAP[t])
        elif base in _SYNONYM_MAP:
            tokens.extend(_SYNONYM_MAP[base])

    return tokens


@functools.lru_cache(maxsize=1)
def _bm25_state() -> Tuple[BM25Okapi, List[Dict[str, Any]]]:
    docs = get_all_documents()
    tokenized = [tokenize(d["content"], is_query=False) for d in docs]
    return BM25Okapi(tokenized), docs


def clear_cache() -> None:
    _bm25_state.cache_clear()


def sparse_search(query: str, k: int) -> List[Tuple[Dict[str, Any], float]]:
    bm25, docs = _bm25_state()
    if not docs:
        return []
    query_tokens = tokenize(query, is_query=True)
    if not query_tokens:
        query_tokens = tokenize(query, is_query=False)
    scores = bm25.get_scores(query_tokens)
    ranked = sorted(zip(docs, scores), key=lambda pair: pair[1], reverse=True)
    return [(doc, score) for doc, score in ranked[:k] if score > 0]

