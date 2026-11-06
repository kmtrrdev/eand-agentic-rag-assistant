"""Test follow-up queries: higher tiers, bigger plans, and regression."""
from app.agent.nodes.classify_node import classify_node
from app.agent.nodes.strategy_router_node import strategy_router_node
from app.agent.nodes.tools_node import tools_node

# History: user asked for recommendation, got 132 vs 165
history = [
    {"role": "user", "content": "i have 200 le and i use internet more than minutes suggest for me a plan"},
    {"role": "assistant", "content": "Hekaya Internet 132 (188.57 EGP within budget) and Hekaya Internet 165 (235.71 EGP smart upgrade). 6750 MB vs 8750 MB..."},
]

def run_pipeline(question, hist):
    state = {"question": question, "history": hist}
    c = classify_node(state)
    state.update(c)
    r = strategy_router_node(state)
    state.update(r)
    if state.get("strategy") == "TOOL_RECOMMENDATION":
        t = tools_node(state)
        state.update(t)
    return state

def print_result(label, state):
    print(f"\n{'='*60}")
    print(f"  {label}")
    print(f"{'='*60}")
    print(f"  intent:       {state.get('intent')}")
    print(f"  category:     {state.get('category')}")
    print(f"  budget:       {state.get('budget_egp')}")
    print(f"  min_price:    {state.get('min_price_egp')}")
    print(f"  usage_focus:  {state.get('usage_focus')}")
    print(f"  strategy:     {state.get('strategy')}")
    ev = state.get("tool_evidence", [])
    if ev:
        for e in ev:
            if "recommendations" in e:
                for rec in e["recommendations"]:
                    print(f"  -> {rec['name_en']}: {rec['price_egp']} EGP (total {rec.get('total_egp')}) [{rec.get('recommendation_role')}]")
    else:
        print("  -> No tool evidence")

passed = 0
failed = 0

# ===== Test 1: "What about the higher tiers" =====
s1 = run_pipeline("What about the higher tiers", history)
print_result("T1: What about the higher tiers", s1)
recs1 = []
for e in s1.get("tool_evidence", []):
    for r in e.get("recommendations", []):
        recs1.append(r)
if s1["intent"] == "recommendation" and any(float(r["price_egp"]) > 165 for r in recs1):
    print("  ✅ PASS: Shows tiers above 165")
    passed += 1
else:
    print("  ❌ FAIL: Should show tiers above 165")
    failed += 1

# ===== Test 2: "the higher tiers" (3rd turn) =====
history2 = history + [
    {"role": "user", "content": "What about the higher tiers"},
    {"role": "assistant", "content": "Here are the higher tiers: Hekaya Internet 205, 270, 345..."},
]
s2 = run_pipeline("the higher tiers", history2)
print_result("T2: the higher tiers (3rd turn)", s2)
if s2["intent"] != "greeting":
    print("  ✅ PASS: NOT classified as greeting")
    passed += 1
else:
    print("  ❌ FAIL: Was classified as greeting")
    failed += 1

# ===== Test 3: "عايز باقات أعلى" =====
s3 = run_pipeline("عايز باقات أعلى", history)
print_result("T3: عايز باقات أعلى", s3)
recs3 = []
for e in s3.get("tool_evidence", []):
    for r in e.get("recommendations", []):
        recs3.append(r)
if s3["intent"] == "recommendation" and any(float(r["price_egp"]) > 165 for r in recs3):
    print("  ✅ PASS: Shows higher tiers in Arabic")
    passed += 1
else:
    print("  ❌ FAIL: Should show higher tiers")
    failed += 1

# ===== Test 4: "show me bigger plans" =====
s4 = run_pipeline("show me bigger plans", history)
print_result("T4: show me bigger plans", s4)
recs4 = []
for e in s4.get("tool_evidence", []):
    for r in e.get("recommendations", []):
        recs4.append(r)
if s4["intent"] == "recommendation" and any(float(r["price_egp"]) > 165 for r in recs4):
    print("  ✅ PASS: Shows bigger plans")
    passed += 1
else:
    print("  ❌ FAIL: Should show bigger plans")
    failed += 1

# ===== Test 5: Original flow regression — "i have 200 le..." =====
s5 = run_pipeline("i have 200 le and i use internet more than minutes suggest for me a plan", [])
print_result("T5: REGRESSION - Original budget query", s5)
recs5 = []
for e in s5.get("tool_evidence", []):
    for r in e.get("recommendations", []):
        recs5.append(r)
if (s5["intent"] == "recommendation" and
    any(r.get("recommendation_role") == "within_budget" for r in recs5) and
    any(r.get("recommendation_role") == "slightly_above_budget_upgrade" for r in recs5)):
    print("  ✅ PASS: Still returns within_budget + upgrade")
    passed += 1
else:
    print("  ❌ FAIL: Regression in original flow")
    failed += 1

# ===== Test 6: Greetings still work =====
for greet_q in ["hi", "hello", "مرحبا", "السلام عليكم"]:
    sg = run_pipeline(greet_q, [])
    if sg["intent"] == "greeting":
        print(f"  ✅ PASS: '{greet_q}' -> greeting")
        passed += 1
    else:
        print(f"  ❌ FAIL: '{greet_q}' -> {sg['intent']} (should be greeting)")
        failed += 1

print(f"\n{'='*60}")
print(f"  RESULTS: {passed} passed, {failed} failed")
print(f"{'='*60}")
