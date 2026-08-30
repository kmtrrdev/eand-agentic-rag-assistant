"""
app/agent/nodes/evaluate_retrieval.py
-------------------------------------
Evaluates retrieval quality based on relevance signals, RRF scores,
semantic similarity, keyword overlap, domain entity coverage, and service matching.

Distinguishes:
  - RETRIEVAL_GOOD: Strong evidence found, proceed to generation
  - RETRIEVAL_WEAK: Partial evidence found, retryable if progress plausible
  - RETRIEVAL_FAILED: Insufficient evidence found
"""

import logging
from typing import Any, Dict, List
from langchain_core.documents import Document
from app.retrieval.keyword_retriever import tokenize

logger = logging.getLogger("etisalat_kb.node.evaluate")


def evaluate_retrieval_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    Objective & Strategy-Aware Retrieval Evaluation Node:
    - MCP Ground truth bypass: If MCP evidence exists, marks GOOD without evaluating RAG.
    - Multi-factor scoring: entity coverage, intent match, service match, query token coverage, dense similarity.
    - Progress detection: if new score does not improve by >= 0.03 over previous attempt, halts rewrite.
    """
    documents: List[Document] = state.get("documents", [])
    question: str = state.get("question", "")
    entities: List[str] = state.get("entities", [])
    keywords: List[str] = state.get("keywords", [])
    service: str = state.get("service", "general")
    sub_track: str = state.get("sub_track", "")
    strategy: str = state.get("strategy", "")
    previous_score: float = state.get("current_retrieval_score", 0.0)

    # ── 1. Strategy & MCP Evidence Ground Truth Bypass ───────────────────────
    if state.get("mcp_evidence") or "VERIFIED MCP GROUND TRUTH" in (state.get("context") or ""):
        step_info = {
            "node": "evaluate",
            "title_ar": "تقييم جودة الاسترجاع (أدوات MCP)",
            "title_en": "Retrieval Evaluation (MCP Tools)",
            "status": "RETRIEVAL_GOOD",
            "badge": "⚡ حقائق MCP موثقة",
            "description_ar": "تم توثيق الحقائق المطلوبة مباشرة من أدوات MCP الرسمية وتجاوز فحص النصوص.",
            "description_en": "Ground truth verified directly via official MCP tools.",
            "details": {
                "status": "RETRIEVAL_GOOD",
                "matched_entities": len(entities) or 1,
                "relevance_score": 1.0,
                "retryable": False,
            },
        }
        return {
            "retrieval_status": "RETRIEVAL_GOOD",
            "retrieval_relevance_score": 1.0,
            "previous_retrieval_score": previous_score,
            "current_retrieval_score": 1.0,
            "workflow_trace": [step_info],
        }

    # ── 2. No Documents Empty Retrieval Check ────────────────────────────────
    if not documents:
        step_info = {
            "node": "evaluate",
            "title_ar": "تقييم جودة الاسترجاع",
            "title_en": "Retrieval Evaluation",
            "status": "RETRIEVAL_FAILED",
            "badge": "❌ استرجاع غير كافٍ",
            "description_ar": "لم يتم العثور على أي مستندات مطابقة في قاعدة المعرفة.",
            "description_en": "No matching documents found in knowledge base.",
            "details": {
                "status": "RETRIEVAL_FAILED",
                "matched_entities": 0,
                "relevance_score": 0.0,
                "retryable": True,
                "reason": "NO_DOCUMENTS",
            },
        }
        return {
            "retrieval_status": "RETRIEVAL_FAILED",
            "retrieval_relevance_score": 0.0,
            "previous_retrieval_score": previous_score,
            "current_retrieval_score": 0.0,
            "last_retry_reason": "NO_DOCUMENTS",
            "workflow_trace": [step_info],
        }

    # ── 3. Multi-Factor Objective Evaluation ──────────────────────────────────
    query_tokens = set(tokenize(question))
    total_relevance = 0.0
    matched_entity_count = 0
    matched_service_count = 0

    for doc in documents:
        content_lower = doc.page_content.lower()
        doc_tokens = set(tokenize(doc.page_content))

        # 1. Query token coverage
        overlap = len(query_tokens.intersection(doc_tokens))
        token_coverage = overlap / max(len(query_tokens), 1)

        # 2. RRF score signal
        rrf = float(doc.metadata.get("rrf_score", 0.0))

        # 3. Dense semantic similarity signal — only SemanticRetriever attaches this
        # metadata key; a BM25-only hit genuinely has no dense signal at all. This
        # used to default to 0.5 (a fabricated "moderate match") for any chunk
        # missing the key, which silently rewarded pure-keyword hits with credit
        # for a semantic signal they never had. Default to 0.0 (no signal, no
        # credit) instead — a chunk with strong lexical/entity/service overlap can
        # still score RETRIEVAL_GOOD via those other terms.
        dense_sim = float(doc.metadata.get("semantic_similarity", 0.0))

        # 4. Entity coverage
        has_entity = any(str(ent).lower() in content_lower for ent in entities if ent)
        if has_entity:
            matched_entity_count += 1

        # 5. Service match
        service_target = (sub_track or service or "").lower()
        has_service = service_target in content_lower if service_target and service_target != "general" else True
        if has_service:
            matched_service_count += 1

        # Weighted composite score per chunk
        doc_relevance = (
            (token_coverage * 0.30)
            + (min(rrf * 25.0, 1.0) * 0.25)
            + (dense_sim * 0.25)
            + (0.10 if has_entity else 0.0)
            + (0.10 if has_service else 0.0)
        )
        total_relevance += doc_relevance

    avg_relevance = round(total_relevance / len(documents), 4)

    # ── 4. Progress Check: Did score improve compared to previous attempt? ────
    score_improvement = avg_relevance - previous_score
    progress_made = previous_score == 0.0 or score_improvement >= 0.03

    # Classification logic
    entity_required = bool(entities)
    entity_satisfied = (matched_entity_count > 0) if entity_required else True

    if (avg_relevance >= 0.35 and entity_satisfied) or avg_relevance >= 0.55:
        status = "RETRIEVAL_GOOD"
        badge = "⚡ تطابق ممتاز"
        desc_ar = "المستندات المسترجعة كافية وذات صلة قوية بالإجابة."
        desc_en = "Retrieved documents provide strong, relevant evidence."
        reason = "HIGH_RELEVANCE"
        retryable = False
    elif avg_relevance >= 0.18 and progress_made:
        status = "RETRIEVAL_WEAK"
        badge = "⚠️ تطابق جزئي"
        desc_ar = "المستندات ذات صلة جزئية، قد يتم تفعيل إعادة الصياغة مرة واحدة."
        desc_en = "Moderate relevance score; eligible for single targeted rewrite."
        reason = "LOW_RELEVANCE"
        retryable = True
    else:
        status = "RETRIEVAL_FAILED"
        badge = "❌ تطابق ضعيف"
        desc_ar = "المستندات غير كافية أو لم يحدث تحسن في البحث."
        desc_en = "Insufficient evidence or no search progress."
        reason = "INSUFFICIENT_EVIDENCE" if not progress_made else "LOW_RELEVANCE"
        retryable = progress_made

    step_info = {
        "node": "evaluate",
        "title_ar": "تقييم جودة الاسترجاع",
        "title_en": "Retrieval Evaluation",
        "status": status,
        "badge": badge,
        "description_ar": desc_ar,
        "description_en": desc_en,
        "details": {
            "status": status,
            "relevance_score": avg_relevance,
            "previous_score": previous_score,
            "improvement": round(score_improvement, 4),
            "matched_entities_count": matched_entity_count,
            "matched_service_count": matched_service_count,
            "retryable": retryable,
            "reason": reason,
        },
    }

    return {
        "retrieval_status": status,
        "retrieval_relevance_score": avg_relevance,
        "previous_retrieval_score": previous_score,
        "current_retrieval_score": avg_relevance,
        "last_retry_reason": reason,
        "workflow_trace": [step_info],
    }

