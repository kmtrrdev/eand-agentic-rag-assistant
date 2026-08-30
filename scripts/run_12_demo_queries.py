"""
scripts/run_12_demo_queries.py
------------------------------
Executes the 12 mandatory demo queries against the live running e& Egypt KB API,
recording the full response, latency, sources, confidence, and MCP tools called.
"""
import json
import os
import sys
import time
import urllib.request
import urllib.error
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

API_URL = "http://127.0.0.1:8000/chat"

DEMO_QUERIES = [
    {
        "id": 1,
        "title": "Budget package recommendation (Egyptian Arabic)",
        "question": "عايز باقة نت ومكالمات في حدود 100 جنيه",
        "conversation_id": "demo_conv_1",
    },
    {
        "id": 2,
        "title": "USSD code lookup (Egyptian Arabic)",
        "question": "كود تجديد باقة حكاية ميكس 92 كام؟",
        "conversation_id": "demo_conv_2",
    },
    {
        "id": 3,
        "title": "Quota & tax calculation (Arabic)",
        "question": "باقة حكاية 52 بتديني كام ميكس وسعرها كام شامل الضريبة؟",
        "conversation_id": "demo_conv_3",
    },
    {
        "id": 4,
        "title": "Postpaid roaming inquiry (English)",
        "question": "What is the price of Emerald 430 and what are its roaming benefits?",
        "conversation_id": "demo_conv_4",
    },
    {
        "id": 5,
        "title": "Home 4G Wireless / DataLine (Arabic)",
        "question": "عايز راوتر هوائي وباقة نت بدون خط أرضي",
        "conversation_id": "demo_conv_5",
    },
    {
        "id": 6,
        "title": "Telecom tax & recharge calculation (Egyptian Arabic)",
        "question": "لو شحنت بـ 100 جنيه رصيد، هدفع كام شامل ضريبة الشحن وهاخد رصيد صافي كام؟",
        "conversation_id": "demo_conv_6",
    },
    {
        "id": 7,
        "title": "Mix transfer feature procedure (Arabic)",
        "question": "ازاي احول ميكسات لحد تاني في باقات حكاية؟",
        "conversation_id": "demo_conv_7",
    },
    {
        "id": 8,
        "title": "Super Connect quota & code (Arabic)",
        "question": "باقة سوبر كونكت 60 بتديني كام ميجا وكود الاشتراك ايه؟",
        "conversation_id": "demo_conv_8",
    },
    {
        "id": 9,
        "title": "Salafny emergency service (Egyptian Arabic)",
        "question": "ازاي استلف رصيد لما رصيدي يخلص؟",
        "conversation_id": "demo_conv_9",
    },
    {
        "id": 10,
        "title": "Cheapest prepaid tier (English)",
        "question": "Tell me about the cheapest prepaid package and its validity period",
        "conversation_id": "demo_conv_10",
    },
    {
        "id": 11,
        "title": "Aqwa recharge cards (Egyptian Arabic)",
        "question": "عايز اعرف نظام كروت الشحن واقوى كارت بيدي ايه",
        "conversation_id": "demo_conv_11",
    },
    {
        "id": 12,
        "title": "Multi-turn context follow-up (Turn 1)",
        "question": "عايز باقة نت بـ 150 جنيه",
        "conversation_id": "demo_conv_12_multiturn",
    },
    {
        "id": 13,
        "title": "Multi-turn context follow-up (Turn 2 - 'وكود التجديد بتاعها ايه؟')",
        "question": "وكود التجديد بتاعها ايه؟",
        "conversation_id": "demo_conv_12_multiturn",
    },
]


def send_chat_query(question: str, conversation_id: str = None) -> dict:
    payload = {"question": question}
    if conversation_id:
        payload["conversation_id"] = conversation_id

    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        API_URL,
        data=data,
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST"
    )

    t0 = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=90) as resp:
            elapsed = round(time.perf_counter() - t0, 2)
            result = json.loads(resp.read().decode("utf-8"))
            result["latency_s"] = elapsed
            result["status_code"] = resp.status
            return result
    except urllib.error.HTTPError as e:
        elapsed = round(time.perf_counter() - t0, 2)
        err_body = e.read().decode("utf-8", errors="replace")
        return {
            "status_code": e.code,
            "error": err_body,
            "latency_s": elapsed,
        }
    except Exception as e:
        elapsed = round(time.perf_counter() - t0, 2)
        return {
            "status_code": 500,
            "error": str(e),
            "latency_s": elapsed,
        }


def main():
    print("\n" + "=" * 70)
    print("  Executing 12 Mandatory Demo Queries against e& Egypt Agentic KB")
    print(f"  Target: {API_URL}")
    print("=" * 70 + "\n")

    results = []
    for item in DEMO_QUERIES:
        q_id = item["id"]
        title = item["title"]
        question = item["question"]
        conv_id = item["conversation_id"]

        print(f"[{q_id}/12] {title}")
        print(f"  Q: {question}")

        resp = send_chat_query(question, conv_id)
        status = resp.get("status_code", 0)

        if status == 200:
            ans = resp.get("answer", "")
            conf = resp.get("confidence", "N/A")
            sources = resp.get("sources", [])
            qa = resp.get("query_analysis", {})
            mcp_tools = qa.get("mcp_tools_called", [])
            lat = resp.get("latency_s", 0)

            print(f"  A (tail): {ans[:120]}...")
            print(f"  Confidence: {conf} | Latency: {lat}s | MCP Tools: {mcp_tools} | Sources: {len(sources)}")
            print("-" * 50)

            results.append({
                "id": q_id,
                "title": title,
                "question": question,
                "conversation_id": conv_id,
                "status": "SUCCESS",
                "answer": ans,
                "confidence": conf,
                "latency_s": lat,
                "mcp_tools_called": mcp_tools,
                "sources_count": len(sources),
                "sources": sources,
            })
        else:
            print(f"  FAILED: Status {status}, Error: {resp.get('error')}")
            results.append({
                "id": q_id,
                "title": title,
                "question": question,
                "conversation_id": conv_id,
                "status": "FAILED",
                "error": resp.get("error"),
            })

    # Save to JSON report
    out_dir = Path(__file__).resolve().parent.parent / "evaluation" / "results"
    out_dir.mkdir(parents=True, exist_ok=True)
    report_file = out_dir / "demo_12_queries_report.json"

    with open(report_file, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    print(f"\n[DONE] Saved 12 demo queries report to: {report_file}")


if __name__ == "__main__":
    main()
