"""
Ground-truth Comprehensive General Evaluation Suite for e& Egypt Agentic Knowledge Base.
Executes real catalog test cases, captures full model responses, and performs in-depth
multi-dimensional comparisons against expected catalog ground-truth answers:
  1. Factual Accuracy (Prices, Quotas, USSD codes, Validity)
  2. Keyword & Information Recall
  3. Embedding Semantic Similarity (Cosine)
  4. Completeness & Diagnostic Notes
Saves complete question, expected answer, model answer, and comparison breakdown.
"""
import json
import math
import sys
import time
from pathlib import Path

# Ensure UTF-8 output on Windows terminal
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.agent.graph import get_agent
from app.embeddings.embedding_service import get_embedding_function

DATASET_PATH = ROOT / "evaluation" / "general_eval_dataset.json"
RESULTS_PATH = ROOT / "evaluation" / "general_eval_results.json"


def cosine_similarity(v1: list[float], v2: list[float]) -> float:
    dot = sum(a * b for a, b in zip(v1, v2))
    norm1 = math.sqrt(sum(a * a for a in v1))
    norm2 = math.sqrt(sum(b * b for b in v2))
    if norm1 == 0 or norm2 == 0:
        return 0.0
    return max(0.0, min(1.0, dot / (norm1 * norm2)))


def compare_answers(expected_answer: str, model_answer: str, key_facts: dict, emb_func) -> dict:
    model_lower = model_answer.lower()
    expected_lower = expected_answer.lower()

    # 1. Semantic Similarity via Embeddings
    emb_expected = emb_func.embed_query(expected_answer)
    emb_model = emb_func.embed_query(model_answer)
    sem_sim = round(cosine_similarity(emb_expected, emb_model) * 100, 1)

    # 2. Factual Checks
    factual_checks = {}
    facts_total = 0
    facts_passed = 0

    # Price Check
    p_pre = key_facts.get("price_pretax")
    p_post = key_facts.get("price_after_tax")
    if p_pre:
        facts_total += 1
        has_price = (p_pre in model_lower) or (p_post and p_post in model_lower)
        factual_checks["price_match"] = has_price
        if has_price:
            facts_passed += 1
    else:
        factual_checks["price_match"] = None

    # Quota Check
    quota = key_facts.get("quota")
    if quota:
        facts_total += 1
        clean_quota = quota.replace(",", "")
        model_no_commas = model_lower.replace(",", "")
        has_quota = (clean_quota in model_no_commas) or (quota in model_lower)
        factual_checks["quota_match"] = has_quota
        if has_quota:
            facts_passed += 1
    else:
        factual_checks["quota_match"] = None

    # USSD / Activation Check
    ussd = key_facts.get("ussd_code")
    if ussd:
        facts_total += 1
        if "111" in ussd:
            has_ussd = ("111" in model_lower) or ("فرع" in model_lower) or ("store" in model_lower)
        else:
            clean_ussd = ussd.strip("*#")
            has_ussd = (clean_ussd in model_lower) or (ussd in model_lower)
        factual_checks["ussd_match"] = has_ussd
        if has_ussd:
            facts_passed += 1
    else:
        factual_checks["ussd_match"] = None

    # Validity Check
    val_days = key_facts.get("validity_days")
    if val_days:
        facts_total += 1
        validity_markers = [val_days]
        if val_days == "30":
            validity_markers.extend(["شهر", "30 يوم", "30 days", "monthly"])
        elif val_days == "90":
            validity_markers.extend(["3 أشهر", "3 months", "90"])
        has_val = any(m in model_lower for m in validity_markers)
        factual_checks["validity_match"] = has_val
        if has_val:
            facts_passed += 1
    else:
        factual_checks["validity_match"] = None

    factual_score = (facts_passed / max(facts_total, 1)) * 100 if facts_total > 0 else 100.0

    # 3. Keyword / Key Fact Recall
    keywords = key_facts.get("keywords", [])
    matched_kws = []
    missing_kws = []
    model_no_commas = model_lower.replace(",", "")
    for kw in keywords:
        clean_kw = kw.strip().lower()
        clean_kw_no_comma = clean_kw.replace(",", "")
        if clean_kw in model_lower or clean_kw_no_comma in model_no_commas:
            matched_kws.append(kw)
        else:
            missing_kws.append(kw)

    kw_recall = round((len(matched_kws) / max(len(keywords), 1)) * 100, 1)

    # 4. Overall Weighted Score (40% Facts, 40% Keywords, 20% Semantic Similarity)
    overall_score = round(0.40 * factual_score + 0.40 * kw_recall + 0.20 * sem_sim, 1)

    # 5. Verdict
    if overall_score >= 75.0 and (facts_total == 0 or facts_passed >= max(1, facts_total - 1)):
        verdict = "PASS"
    elif overall_score >= 50.0:
        verdict = "PARTIAL"
    else:
        verdict = "FAIL"

    # 6. Diagnostic Notes
    notes = []
    if factual_checks.get("price_match") is True:
        notes.append("✅ Correct price")
    elif factual_checks.get("price_match") is False:
        notes.append(f"❌ Missing/wrong price (expected: {p_pre} or {p_post})")

    if factual_checks.get("quota_match") is True:
        notes.append("✅ Correct quota")
    elif factual_checks.get("quota_match") is False:
        notes.append(f"❌ Missing/wrong quota (expected: {quota})")

    if factual_checks.get("ussd_match") is True:
        notes.append("✅ Correct activation code")
    elif factual_checks.get("ussd_match") is False:
        notes.append(f"❌ Missing/wrong activation code (expected: {ussd})")

    notes.append(f"Keywords Recall: {len(matched_kws)}/{len(keywords)} ({kw_recall}%)")
    notes.append(f"Semantic Alignment: {sem_sim}%")

    return {
        "verdict": verdict,
        "overall_score_percent": overall_score,
        "semantic_similarity_percent": sem_sim,
        "keyword_recall_percent": kw_recall,
        "factual_accuracy_percent": round(factual_score, 1),
        "factual_checks": factual_checks,
        "matched_key_facts": matched_kws,
        "missing_key_facts": missing_kws,
        "analysis_notes": " | ".join(notes),
    }


def main():
    print("=" * 90)
    print("🔍 GROUND-TRUTH GENERAL EVALUATION SUITE (COMPARING MODEL VS EXPECTED ANSWERS)")
    print("=" * 90)

    if not DATASET_PATH.exists():
        print(f"Error: {DATASET_PATH} not found.")
        sys.exit(1)

    dataset = json.loads(DATASET_PATH.read_text(encoding="utf-8"))
    cases = dataset["cases"]
    print(f"Loaded {len(cases)} test cases with full expected answers.\n")

    agent = get_agent()
    emb_func = get_embedding_function()

    results = []
    latencies = []
    scores = []
    t_start = time.perf_counter()

    for idx, case in enumerate(cases, 1):
        c_id = case["id"]
        cat = case["category"]
        lang = case["language"]
        q = case["question"]
        expected_ans = case["expected_answer"]
        key_facts = case.get("key_facts", {})

        t0 = time.perf_counter()
        try:
            res = agent.invoke({"question": q, "history": []})
            model_ans = (res.get("answer") or "").strip()
        except Exception as exc:
            model_ans = f"AGENT_EXECUTION_ERROR: {exc}"

        latency_ms = int((time.perf_counter() - t0) * 1000)
        latencies.append(latency_ms)

        comparison = compare_answers(expected_ans, model_ans, key_facts, emb_func)
        score = comparison["overall_score_percent"]
        scores.append(score)
        verdict = comparison["verdict"]

        status_sym = "✅ PASS" if verdict == "PASS" else ("⚠️ PARTIAL" if verdict == "PARTIAL" else "❌ FAIL")

        results.append({
            "id": c_id,
            "category": cat,
            "language": lang,
            "question": q,
            "expected_answer": expected_ans,
            "model_answer": model_ans,
            "comparison": comparison,
            "latency_ms": latency_ms,
        })

        print(f"[{idx:02d}/{len(cases):02d}] {c_id} [{cat} - {lang}]: {status_sym} (Score: {score}% | {latency_ms}ms)")
        print(f"      Q: {q[:70]}...")
        print(f"      Notes: {comparison['analysis_notes']}")
        print("-" * 90)

    total_time = round(time.perf_counter() - t_start, 2)

    # Compute Aggregates
    total_cases = len(cases)
    passed_count = sum(1 for r in results if r["comparison"]["verdict"] == "PASS")
    partial_count = sum(1 for r in results if r["comparison"]["verdict"] == "PARTIAL")
    failed_count = sum(1 for r in results if r["comparison"]["verdict"] == "FAIL")

    avg_score = round(sum(scores) / len(scores), 1)
    avg_sem_sim = round(sum(r["comparison"]["semantic_similarity_percent"] for r in results) / total_cases, 1)
    avg_kw_recall = round(sum(r["comparison"]["keyword_recall_percent"] for r in results) / total_cases, 1)
    avg_latency = int(sum(latencies) / len(latencies))

    summary = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "total_cases": total_cases,
        "passed_cases": passed_count,
        "partial_cases": partial_count,
        "failed_cases": failed_count,
        "pass_rate_percent": round((passed_count / total_cases) * 100, 1),
        "average_overall_score_percent": avg_score,
        "average_semantic_similarity_percent": avg_sem_sim,
        "average_keyword_recall_percent": avg_kw_recall,
        "average_latency_ms": avg_latency,
        "total_execution_time_seconds": total_time,
        "results": results,
    }

    RESULTS_PATH.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    print("\n" + "=" * 90)
    print("📊 GROUND-TRUTH GENERAL EVALUATION SUMMARY REPORT")
    print("=" * 90)
    print(f"Total Cases Evaluated                 : {total_cases}")
    print(f"Fully Passed Cases (Score >= 75%)     : {passed_count} ({summary['pass_rate_percent']}%)")
    print(f"Partially Passed Cases (50-74%)       : {partial_count}")
    print(f"Failed Cases (< 50%)                  : {failed_count}")
    print(f"Average Overall Score                 : {avg_score}%")
    print(f"Average Semantic Similarity (Cosine)  : {avg_sem_sim}%")
    print(f"Average Keyword & Fact Recall         : {avg_kw_recall}%")
    print(f"Average Pipeline Latency              : {avg_latency} ms")
    print(f"Total Execution Time                  : {total_time} s")
    print(f"Complete Results Saved To             : {RESULTS_PATH}")
    print("=" * 90)


if __name__ == "__main__":
    main()
