import re
from typing import Any, Dict, List, Optional
from langchain_core.documents import Document

# Strict regex patterns for prices: only match numbers followed/preceded by currency or pricing terms
PRICE_PATTERNS = [
    re.compile(r"(?:سعر|بـ|بمبلغ|قيمة|مبلغ|price(?:\s+is)?|costs?)\s*:?\s*(\d+(?:\.\d+)?)\s*(?:جنيه|egp|le|ج\.م)", re.IGNORECASE),
    re.compile(r"(\d+(?:\.\d+)?)\s*(?:جنيه|egp|le|ج\.م)\s*(?:شهريا|before tax|قبل الضريبة|شامل الضريبة|incl\.?\s*tax)?", re.IGNORECASE),
    re.compile(r"(?:باقة|bundle|package)\s*(?:حكاية|إمرالد|emerald|hekaya)?\s*(\d+)", re.IGNORECASE),
]


def extract_conservative_prices(text: str) -> List[float]:
    """Extract verified monetary prices from chunk text with strict context checking."""
    if not text:
        return []
    prices = set()
    for pat in PRICE_PATTERNS:
        for match in pat.finditer(text):
            try:
                val = float(match.group(1))
                if 1.0 <= val <= 10000.0:
                    prices.add(val)
            except Exception:
                continue
    return list(prices)


def _extract_query_entities(query: str) -> List[str]:
    """Extract explicit telecom entities / tiers from user query."""
    q = query.lower()
    entities = []

    # Aqwa Card matches
    for m in re.finditer(r"(?:أقوى\s*كارت|اقوى\s*كارت|aqwa\s*card)\s*(\d+(?:\.\d+)?)", q):
        entities.append(f"Aqwa Card {m.group(1)}")
    # Hekaya Mixat matches
    for m in re.finditer(r"(?:حكاية\s*مكسات|حكاية\s*ميكسات|hekaya\s*mixat)\s*(\d+)", q):
        entities.append(f"Hekaya Mixat {m.group(1)}")
    # Hekaya Internet matches
    for m in re.finditer(r"(?:حكاية\s*إنترنت|حكاية\s*انترنت|hekaya\s*internet)\s*(\d+)", q):
        entities.append(f"Hekaya Internet {m.group(1)}")
    # Emerald matches
    for m in re.finditer(r"(?:إمرالد|امرالد|emerald)\s*(\d+)", q):
        entities.append(f"Emerald {m.group(1)}")

    # Standalone numbers if specific context
    if not entities:
        if "كارت" in q or "aqwa" in q:
            for num in re.findall(r"\b(5|15|19|22\.5|30|45|50|75|100)\b", q):
                entities.append(f"Aqwa Card {num}")
        elif "مكسات" in q or "mixat" in q:
            for num in re.findall(r"\b(52|69|92|120|180|270)\b", q):
                entities.append(f"Hekaya Mixat {num}")
        elif "نت" in q or "internet" in q:
            for num in re.findall(r"\b(46|58|80|105|132|165|205|270|345|415|480|600)\b", q):
                entities.append(f"Hekaya Internet {num}")

    return entities


class CandidateReranker:
    """
    Reranks candidate documents prioritizing exact entity matches,
    symmetrical comparison representation, and device compatibility.
    """

    def rerank(
        self,
        documents: List[Document],
        query: str,
        intent: str = "recommendation",
        service: str = "general",
        line_type: str = "mobile_phone",
        data_usage: str = "medium",
        voice_usage: str = "medium",
        budget_egp: Optional[float] = None,
        final_k: int = 5,
    ) -> List[Document]:
        if not documents:
            return []

        q_lower = (query or "").lower()
        is_mifi_query = any(
            term in q_lower
            for term in ["mifi", "usb", "modem", "router", "راوتر", "ماي فاي", "مايفاي", "مودم", "dataline", "data line"]
        )
        is_category_query = any(
            term in q_lower
            for term in ["الخمسة", "فئات", "انظمة", "أنظمة", "categories", "systems", "كل الأنظمة"]
        )

        query_entities = _extract_query_entities(query)
        is_comparison = len(query_entities) >= 2 or "قارن" in q_lower or " vs " in q_lower or "مقارنة" in q_lower

        def score_doc(doc: Document) -> float:
            content = doc.page_content.lower()
            src = doc.metadata.get("source_file", "").lower()
            product = str(doc.metadata.get("product", "")).lower()
            plan_name = str(doc.metadata.get("plan_name", "")).lower()
            score = 0.0

            # 1. Base score from RRF or dense similarity
            rrf_score = float(doc.metadata.get("rrf_score", 0.0))
            score += rrf_score * 100.0

            if "keyword_score" in doc.metadata:
                score += min(float(doc.metadata["keyword_score"]), 15.0)

            # 2. EXACT ENTITY MATCH BOOST (Highest Priority)
            if query_entities:
                matched_any = False
                for entity in query_entities:
                    e_lower = entity.lower()
                    if (e_lower in plan_name or e_lower in content or
                        (e_lower.replace(" ", "") in content.replace(" ", ""))):
                        score += 150.0
                        matched_any = True
                # Penalize non-matching documents if not comparison
                if not is_comparison and not matched_any:
                    score -= 60.0

            # 3. Category / Overview Boost for Enumeration Queries
            if is_category_query:
                if "overview" in content or "reference guide" in content or "فئات" in content:
                    score += 50.0

            # 4. Device Compatibility Guard
            is_dataline_doc = "dataline" in src or "data_line" in product
            if is_mifi_query or line_type == "mifi_router":
                if is_dataline_doc:
                    score += 35.0
            else:
                if is_dataline_doc:
                    return -100.0

            # 5. Service / Category Preference
            is_aqwa_query = any(k in q_lower for k in ["أقوى كارت", "اقوى كارت", "اقوي كارت", "أقوي كارت", "aqwa card", "كروت الشحن"])
            if is_aqwa_query:
                if "prepaid" in src or "aqwa" in content:
                    score += 120.0
                elif "super connect" in content or "hekaya" in src:
                    score -= 40.0

            if service and service.lower() != "general":
                s_lower = service.lower()
                if s_lower in src or s_lower in product:
                    score += 20.0

            # 6. Conservative Budget Proximity
            if budget_egp and budget_egp > 0 and not query_entities:
                extracted_prices = extract_conservative_prices(doc.page_content)
                for price in extracted_prices:
                    diff_ratio = abs(price - budget_egp) / budget_egp
                    if diff_ratio <= 0.35:
                        score += 25.0 * (1.0 - diff_ratio)
                        break

            # 7. Legacy Chunk Handling
            is_legacy = doc.metadata.get("plan_status") == "legacy" or doc.metadata.get("applies_to_current_plans") is False
            if is_legacy:
                is_legacy_query = any(k in q_lower for k in ["قديم", "قديمة", "legacy", "previous", "old system", "older system", "القديم", "القديمة"])
                if not is_legacy_query:
                    score -= 100.0
                else:
                    score += 60.0

            return score

        scored_docs = [(score_doc(d), d) for d in documents]
        valid_docs = [d for score, d in scored_docs if score > -50.0]
        ranked_docs = sorted(valid_docs, key=lambda d: score_doc(d), reverse=True)

        # Symmetrical Dual-Entity Slotting for Comparisons
        if is_comparison and len(query_entities) >= 2:
            selected: List[Document] = []
            entity_docs: Dict[str, List[Document]] = {e: [] for e in query_entities}

            for doc in ranked_docs:
                c_low = doc.page_content.lower()
                p_low = str(doc.metadata.get("plan_name", "")).lower()
                for e in query_entities:
                    if e.lower() in p_low or e.lower() in c_low:
                        entity_docs[e].append(doc)

            # Pick top document for each entity first
            for e, d_list in entity_docs.items():
                if d_list:
                    selected.append(d_list[0])

            # Fill remaining slots with highest ranked documents
            for doc in ranked_docs:
                if doc not in selected and len(selected) < final_k:
                    selected.append(doc)

            return selected

        return ranked_docs[:final_k]
