"""Automated test suite for dynamic chunk retrieval based on similarity."""
from app.retrieval.hybrid_retriever import search, _filter_by_similarity
from app.config import settings

def test_filter_by_similarity_cliff():
    print("=== Test 1: Cliff Detection in _filter_by_similarity ===")
    candidates = [
        {"content": "chunk 1", "similarity_score": 0.95},
        {"content": "chunk 2", "similarity_score": 0.90},
        # Significant drop > 0.22 from 0.90 to 0.50
        {"content": "chunk 3", "similarity_score": 0.50},
        {"content": "chunk 4", "similarity_score": 0.48},
        {"content": "chunk 5", "similarity_score": 0.45},
    ]
    # min_k=2, max_k=5, cliff_gap=0.22, ratio_threshold=0.40
    filtered = _filter_by_similarity(candidates, min_k=2, max_k=5, ratio_threshold=0.40, cliff_gap=0.22)
    print(f"Candidates: {len(candidates)} -> Selected: {len(filtered)}")
    assert len(filtered) == 2, f"Expected 2 chunks due to cliff drop, got {len(filtered)}"
    assert filtered[0]["content"] == "chunk 1"
    assert filtered[1]["content"] == "chunk 2"
    print("✅ PASS: Cliff correctly pruned chunks 3, 4, 5")

def test_filter_by_similarity_smooth():
    print("\n=== Test 2: Smooth Relevance Selection ===")
    candidates = [
        {"content": "chunk 1", "similarity_score": 0.90},
        {"content": "chunk 2", "similarity_score": 0.85},
        {"content": "chunk 3", "similarity_score": 0.80},
        {"content": "chunk 4", "similarity_score": 0.75},
        {"content": "chunk 5", "similarity_score": 0.70},
        {"content": "chunk 6", "similarity_score": 0.40}, # Below 0.90 * 0.60 = 0.54
    ]
    filtered = _filter_by_similarity(candidates, min_k=2, max_k=6, ratio_threshold=0.60, cliff_gap=0.22)
    print(f"Candidates: {len(candidates)} -> Selected: {len(filtered)}")
    assert len(filtered) == 5, f"Expected 5 chunks, got {len(filtered)}"
    assert filtered[-1]["content"] == "chunk 5"
    print("✅ PASS: Smoothly kept all 5 relevant chunks, excluded chunk 6")

def test_retrieval_query_counts():
    print("\n=== Test 3: Real Query Retrieval Dynamic Variance ===")
    
    # 1. Very specific query (focused)
    q_focused = "كود تفعيل حكاية 132"
    res_focused = search(q_focused, strategy="TOOL_ACTIVATION", intent="activation_code")
    print(f"Query: '{q_focused}' (focused) -> Chunks returned: {len(res_focused)}")
    for i, r in enumerate(res_focused):
        print(f"  [{i+1}] sim={r.get('similarity_score')} | {r['content'][:60]}...")
    assert len(res_focused) <= 4, f"Focused query returned too many chunks: {len(res_focused)}"
    assert all("similarity_score" in r for r in res_focused), "Missing similarity_score in results"
    print("✅ PASS: Focused query returned small targeted set (<= 4)")

    # 2. Broad comparison query
    q_broad = "قارن بين باقات حكاية مكسات وحكاية انترنت بالتفصيل ومزايا كل عائلة"
    res_broad = search(q_broad, strategy="RAG_ONLY", intent="comparison")
    print(f"\nQuery: '{q_broad}' (broad) -> Chunks returned: {len(res_broad)}")
    for i, r in enumerate(res_broad):
        print(f"  [{i+1}] sim={r.get('similarity_score')} | {r['content'][:60]}...")
    assert len(res_broad) >= 4, f"Broad query returned too few chunks: {len(res_broad)}"
    assert len(res_broad) > len(res_focused), "Broad query should return more chunks than focused query"
    print(f"✅ PASS: Broad query returned more chunks ({len(res_broad)} > {len(res_focused)}) adaptively")

if __name__ == "__main__":
    test_filter_by_similarity_cliff()
    test_filter_by_similarity_smooth()
    test_retrieval_query_counts()
    print("\n===========================================")
    print("ALL DYNAMIC RETRIEVAL TESTS PASSED!")
    print("===========================================")
