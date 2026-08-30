import re
from typing import List
from rank_bm25 import BM25Okapi
from langchain_core.documents import Document

ARABIC_DIGIT_MAP = str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")


def normalize_arabic(text: str) -> str:
    """
    Carefully normalize Arabic text while preserving digits, USSD codes, and product tokens.
    1. Converts eastern Arabic numerals to standard western digits.
    2. Strips tashkeel / harakat and tatweel.
    3. Unifies alef variants (إ, أ, آ, ٱ -> ا).
    4. Unifies yaa / alef maksura (ى -> ي) and taa marbouta (ة -> ه).
    """
    if not text:
        return ""

    # Convert Eastern Arabic digits
    text = text.translate(ARABIC_DIGIT_MAP)

    # Remove Harakat / Tashkeel
    text = re.sub(r"[\u064B-\u065F\u0670]", "", text)

    # Remove Tatweel
    text = re.sub(r"\u0640", "", text)

    # Normalize Alef variants
    text = re.sub(r"[إأآٱ]", "ا", text)

    # Normalize Yaa and Taa Marbouta
    text = re.sub(r"ى", "ي", text)
    text = re.sub(r"ة", "ه", text)

    return text


SYNONYM_MAP = {
    "بدري": ["المبكر", "مبكر", "تجديد", "*807#"],
    "كاشباك": ["كاش", "باك", "money", "استرداد"],
    "مكساتي": ["مكسات", "وحدات", "مكالمات", "mixat"],
    "اهلي": ["العائله", "عائله", "خطوط", "family"],
    "عيلتي": ["العائله", "عائله", "خطوط", "family"],
    "postpaid": ["مفوتر", "فاتوره", "emerald", "اميرالد", "430", "780"],
    "prepaid": ["شحن", "كارت", "اهلا", "مسبق", "aqwa", "اقوى"],
    "اقوى": ["aqwa", "card", "كارت", "شحن"],
    "aqwa": ["اقوى", "كارت", "كروت", "card"],
    "ميني": ["mini", "اسبوعية", "*200#"],
    "فئات": ["انظمة", "باقات", "categories", "systems", "الخمسة"],
    "الخمسة": ["فئات", "انظمة", "categories", "systems"],
}


def tokenize(text: str) -> List[str]:
    """
    Tokenize bilingual Arabic/English text while strictly preserving:
    - USSD codes (e.g., *319#, *130#, *566#, *807#, *972#)
    - Numbers, package sizes, prices (e.g., 165, 2.5, 430)
    - Arabic words and English keywords
    """
    if not text:
        return []

    normalized = normalize_arabic(text.lower())

    # Match USSD codes first (e.g. *319#, *130*1#, #100#)
    ussd_codes = re.findall(r"\*[\d*#]*\d+#|#[\d*#]*\d+#|\*[\d*#]+\b", normalized)

    # Match words, numbers, and decimals
    general_tokens = re.findall(r"\d+(?:\.\d+)?|[a-z\u0600-\u06ff]+", normalized)

    combined = ussd_codes + [t for t in general_tokens if len(t) > 0]

    # Add synonyms for query expansion
    expanded = list(combined)
    for token in combined:
        if token in SYNONYM_MAP:
            for syn in SYNONYM_MAP[token]:
                syn_norm = normalize_arabic(syn.lower())
                if syn_norm not in expanded:
                    expanded.append(syn_norm)

    return expanded


class KeywordRetriever:
    """BM25 Keyword Retriever for sparse lexical search across Arabic and English."""

    def __init__(self, documents: List[Document]):
        self.documents = documents
        self.corpus_tokens = [
            tokenize(doc.page_content)
            for doc in documents
        ]
        self.bm25 = BM25Okapi(self.corpus_tokens) if self.corpus_tokens else None

    def search(self, query: str, top_k: int = 8, exclude_legacy: bool = True) -> List[Document]:
        """
        BM25 search with optional legacy chunk exclusion.

        Args:
            query: User query string.
            top_k: Max results to return.
            exclude_legacy: When True (default), documents tagged
                plan_status='legacy' are masked to a score of 0 before
                ranking, ensuring they cannot enter the top-k results.
                When False, a soft -20.0 penalty is applied instead,
                so legacy chunks are strongly demoted but not fully hidden
                (useful for explicit legacy-inquiry queries).
        """
        if not self.bm25 or not self.documents:
            return []

        query_tokens = tokenize(query)
        if not query_tokens:
            return []

        scores = list(self.bm25.get_scores(query_tokens))

        # Boost scores for exact plan name occurrences in metadata or text
        q_norm = normalize_arabic(query.lower())
        for idx, doc in enumerate(self.documents):
            content_norm = normalize_arabic(doc.page_content.lower())
            plan_name = doc.metadata.get("plan_name", "")
            if plan_name and normalize_arabic(plan_name.lower()) in q_norm:
                scores[idx] += 15.0
            # Boost exact number mentions
            for token in query_tokens:
                if token.isdigit() and token in content_norm:
                    scores[idx] += 3.0

        # ── Legacy chunk score adjustment ───────────────────────────────────────────
        # When exclude_legacy=True, mask to 0.0 to prevent retired bundle data from
        # surfacing for current-plan queries. When exclude_legacy=False (user explicitly
        # asking about legacy/old systems), boost legacy chunks so they rank at the top.
        for idx, doc in enumerate(self.documents):
            if doc.metadata.get("plan_status") == "legacy":
                if exclude_legacy:
                    scores[idx] = 0.0          # Hard exclusion
                else:
                    scores[idx] += 15.0        # Boost for explicit legacy inquiries

        ranked_indices = sorted(
            range(len(scores)),
            key=lambda i: scores[i],
            reverse=True
        )

        results = []
        for index in ranked_indices[:top_k]:
            if scores[index] <= 0:
                continue
            doc = self.documents[index]
            doc_copy = Document(
                page_content=doc.page_content,
                metadata={**doc.metadata, "keyword_score": round(float(scores[index]), 4)}
            )
            results.append(doc_copy)

        return results