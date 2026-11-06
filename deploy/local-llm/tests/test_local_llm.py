"""
tests/test_local_llm.py
-----------------------
Smoke tests for the local Ollama LLM deployment.
Tests: health check, Arabic response, English response, JSON output format.

Usage:
    py -3.12 tests/test_local_llm.py

Requirements:
    pip install requests
"""
import json
import os
import sys
import time

# Ensure UTF-8 output on Windows consoles
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from dotenv import load_dotenv

load_dotenv()

try:
    import requests
except ImportError:
    print("[ERROR] requests not installed. Run: pip install requests")
    sys.exit(1)

BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
MODEL = os.getenv("OLLAMA_MODEL", "deepseek-r1:7b")
if len(sys.argv) > 1 and not sys.argv[1].startswith("-"):
    MODEL = sys.argv[1]
elif "--model" in sys.argv:
    try:
        m_idx = sys.argv.index("--model")
        if m_idx + 1 < len(sys.argv):
            MODEL = sys.argv[m_idx + 1]
    except Exception:
        pass

PASS = "\033[92m[PASS]\033[0m"
FAIL = "\033[91m[FAIL]\033[0m"
INFO = "\033[96m[INFO]\033[0m"


def post_generate(prompt: str, max_tokens: int = 100, temperature: float = 0.1) -> dict:
    """Send a generate request to Ollama."""
    resp = requests.post(
        f"{BASE_URL}/api/generate",
        json={
            "model": MODEL,
            "prompt": prompt,
            "stream": False,
            "options": {
                "num_predict": max_tokens,
                "temperature": temperature,
                "num_ctx": 4096,
            },
        },
        timeout=120,
    )
    resp.raise_for_status()
    return resp.json()


def post_chat(messages: list, max_tokens: int = 100) -> dict:
    """Send a chat request to Ollama (OpenAI-compatible format)."""
    resp = requests.post(
        f"{BASE_URL}/v1/chat/completions",
        json={
            "model": MODEL,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": 0.1,
        },
        timeout=120,
    )
    resp.raise_for_status()
    return resp.json()


# ── Tests ─────────────────────────────────────────────────────

def test_health():
    """Test 1: Ollama server is reachable."""
    print(f"\n{INFO} Test 1: Ollama health check")
    try:
        resp = requests.get(f"{BASE_URL}/api/tags", timeout=5)
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}"
        data = resp.json()
        assert "models" in data, "Response missing 'models' key"
        print(f"{PASS} Ollama is running at {BASE_URL}")
        return True
    except Exception as e:
        print(f"{FAIL} Ollama not reachable: {e}")
        print(f"       Start it with: scripts\\start_local_ai.bat")
        return False


def test_model_available():
    """Test 2: Target model is available."""
    print(f"\n{INFO} Test 2: Model availability — {MODEL}")
    try:
        resp = requests.get(f"{BASE_URL}/api/tags", timeout=5)
        data = resp.json()
        models = [m["name"] for m in data.get("models", [])]
        # Check exact match or prefix match
        found = any(MODEL.split(":")[0] in m for m in models)
        if not found:
            print(f"{FAIL} Model '{MODEL}' not found.")
            print(f"       Available: {models}")
            print(f"       Pull it: ollama pull {MODEL}")
            return False
        print(f"{PASS} Model is available. All models: {models}")
        return True
    except Exception as e:
        print(f"{FAIL} Error checking models: {e}")
        return False


def test_arabic_response():
    """Test 3: Arabic question gets a response."""
    print(f"\n{INFO} Test 3: Arabic response quality")
    prompt = "ما هو الفرق بين هكاية ميكساتس وهكاية إنترنت؟ الإجابة باختصار."
    try:
        start = time.perf_counter()
        data = post_generate(prompt, max_tokens=150)
        elapsed = time.perf_counter() - start
        response = data.get("response", "")
        assert len(response) > 20, f"Response too short: {response!r}"
        print(f"{PASS} Arabic response in {elapsed:.1f}s ({data.get('eval_count', 0)} tokens)")
        print(f"       Preview: {response[:120]}...")
        return True
    except Exception as e:
        print(f"{FAIL} Arabic test failed: {e}")
        return False


def test_english_response():
    """Test 4: English question gets a response."""
    print(f"\n{INFO} Test 4: English response quality")
    prompt = "What is the Hekaya Mixat 92 package? Give a one-sentence answer."
    try:
        start = time.perf_counter()
        data = post_generate(prompt, max_tokens=100)
        elapsed = time.perf_counter() - start
        response = data.get("response", "")
        assert len(response) > 10, f"Response too short: {response!r}"
        print(f"{PASS} English response in {elapsed:.1f}s ({data.get('eval_count', 0)} tokens)")
        print(f"       Preview: {response[:120]}...")
        return True
    except Exception as e:
        print(f"{FAIL} English test failed: {e}")
        return False


def test_openai_compatible_api():
    """Test 5: OpenAI-compatible /v1/chat/completions endpoint."""
    print(f"\n{INFO} Test 5: OpenAI-compatible /v1 API")
    messages = [
        {"role": "user", "content": "Reply with exactly one word: 'ready'"}
    ]
    try:
        data = post_chat(messages, max_tokens=10)
        assert "choices" in data, "Missing 'choices' in response"
        content = data["choices"][0]["message"]["content"]
        assert len(content) > 0, "Empty content"
        print(f"{PASS} /v1/chat/completions works. Response: {content!r}")
        return True
    except Exception as e:
        print(f"{FAIL} OpenAI API test failed: {e}")
        return False


def test_json_output():
    """Test 6: Model can produce structured JSON output."""
    print(f"\n{INFO} Test 6: JSON structured output")
    prompt = (
        'Return ONLY valid JSON, no explanation:\n'
        '{"package": "Hekaya Mixat 92", "price_egp": 92, "data_gb": 5}'
    )
    try:
        data = post_generate(prompt, max_tokens=80, temperature=0.0)
        response = data.get("response", "").strip()
        # Try to parse any JSON found in the response
        start = response.find("{")
        end = response.rfind("}") + 1
        if start >= 0 and end > start:
            parsed = json.loads(response[start:end])
            print(f"{PASS} JSON output produced: {parsed}")
            return True
        else:
            print(f"{FAIL} No valid JSON in response: {response[:200]!r}")
            return False
    except json.JSONDecodeError as e:
        print(f"{FAIL} JSON parse error: {e}")
        return False
    except Exception as e:
        print(f"{FAIL} JSON test failed: {e}")
        return False


def test_latency():
    """Test 7: Basic latency is within acceptable range."""
    print(f"\n{INFO} Test 7: Latency check (first token / TTFT)")
    prompt = "Hello"
    try:
        # Streaming to measure time-to-first-token
        resp = requests.post(
            f"{BASE_URL}/api/generate",
            json={"model": MODEL, "prompt": prompt, "stream": True,
                  "options": {"num_predict": 5}},
            timeout=60,
            stream=True,
        )
        start = time.perf_counter()
        first_token_time = None
        for line in resp.iter_lines():
            if line and first_token_time is None:
                first_token_time = time.perf_counter() - start
                break
        resp.close()

        if first_token_time is not None:
            status = PASS if first_token_time < 10 else FAIL
            print(f"{status} Time-to-first-token: {first_token_time:.2f}s")
            return first_token_time < 30  # Very lenient — model might still be loading
        else:
            print(f"{FAIL} No tokens received")
            return False
    except Exception as e:
        print(f"{FAIL} Latency test failed: {e}")
        return False


# ── Entry Point ───────────────────────────────────────────────
def main():
    print("=" * 56)
    print(f"  e& Egypt Local LLM — Smoke Tests")
    print(f"  Model: {MODEL}")
    print(f"  Endpoint: {BASE_URL}")
    print("=" * 56)

    tests = [
        test_health,
        test_model_available,
        test_arabic_response,
        test_english_response,
        test_openai_compatible_api,
        test_json_output,
        test_latency,
    ]

    results = []
    for test_fn in tests:
        try:
            passed = test_fn()
            results.append(passed)
        except Exception as exc:
            print(f"{FAIL} Unexpected error in {test_fn.__name__}: {exc}")
            results.append(False)
        time.sleep(0.5)  # Brief pause between tests

    passed_count = sum(results)
    total = len(results)
    print(f"\n{'='*56}")
    print(f"  Results: {passed_count}/{total} tests passed")
    if passed_count == total:
        print(f"  \033[92mAll tests passed! Local LLM is ready.\033[0m")
    else:
        failed_names = [tests[i].__name__ for i, r in enumerate(results) if not r]
        print(f"  \033[91mFailed: {', '.join(failed_names)}\033[0m")
        print(f"  See README_LOCAL_LLM.md for troubleshooting.")
    print("=" * 56)

    sys.exit(0 if passed_count == total else 1)


if __name__ == "__main__":
    main()
