"""
benchmark.py
------------
Comprehensive, production-ready benchmark suite for Local LLM on Lenovo Legion Slim 5i.
Hardware: RTX 4050 Laptop (4GB VRAM) / 16GB RAM / Windows.

Benchmark Scenarios:
1. Normal Chat (General Conversational)
2. Arabic Dialect (Egyptian Arabic Telecom Inquiry)
3. English Telecom (Emerald Postpaid Inquiries)
4. RAG-Style Grounded Factual QA (Grounded with context)
5. MCP / Tool Calling (Function calling & parameter extraction)
6. Structured JSON Output (Pydantic-style schema extraction)
7. Multi-Step Agent Workflow (Profiling -> Constraint Evaluation -> Recommendation)

Metrics Recorded:
- Latency (seconds) & Time-To-First-Token (TTFT)
- Generation speed (tokens/second)
- GPU Dedicated VRAM Used / Total & Temperature (°C)
- System RAM Used & Total (MB)
- CPU Utilization (%)
- Success & Schema Compliance Rate
"""
import argparse
import json
import os
import subprocess
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

# Ensure UTF-8 output on Windows consoles
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

try:
    import psutil
    HAS_PSUTIL = True
except ImportError:
    HAS_PSUTIL = False

try:
    import requests
except ImportError:
    print("[ERROR] requests library is required. Install: pip install requests")
    sys.exit(1)

from dotenv import load_dotenv

load_dotenv()

# ── Configuration ─────────────────────────────────────────────
BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
DEFAULT_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5:3b")
OUTPUT_DIR = Path(__file__).resolve().parent.parent  # local-llm-deploy/


# ── Benchmark Scenarios ───────────────────────────────────────
BENCHMARK_SCENARIOS = [
    {
        "id": "1_normal_chat",
        "category": "1. Normal Chat",
        "type": "chat",
        "prompt": "Hello! Can you introduce yourself and explain how you can help me as an e& Egypt customer support assistant?",
        "max_tokens": 250,
        "temperature": 0.2,
        "validator": lambda r: len(r.strip()) > 30 and ("e&" in r or "etisalat" in r.lower() or "help" in r.lower() or "مساعد" in r),
    },
    {
        "id": "2_arabic_dialect",
        "category": "2. Arabic Telecom",
        "type": "arabic",
        "prompt": "عايز اعرف ايه الفرق بين باقات حكاية ميكساتس وحكاية إنترنت، وايه الأنسب ليا لو بستخدم نت كتير وبكلم صحابي عادي؟",
        "max_tokens": 350,
        "temperature": 0.2,
        "validator": lambda r: len(r.strip()) > 40 and ("حكاية" in r or "إنترنت" in r or "ميكسات" in r or "نت" in r),
    },
    {
        "id": "3_english_telecom",
        "category": "3. English Telecom",
        "type": "english",
        "prompt": "Explain the Emerald 780 postpaid plan. What are the included family sharing benefits, data allowances, and minutes?",
        "max_tokens": 300,
        "temperature": 0.2,
        "validator": lambda r: len(r.strip()) > 30 and ("emerald" in r.lower() or "780" in r or "data" in r.lower() or "minutes" in r.lower()),
    },
    {
        "id": "4_rag_grounded",
        "category": "4. RAG Grounded QA",
        "type": "rag",
        "prompt": (
            "Context Information:\n"
            "-------------------\n"
            "Package: Hekaya Mixat 92\n"
            "Pre-tax Price: 92 EGP\n"
            "Total Price (incl. tax): 131.44 EGP\n"
            "Units: 4,000 Mixes\n"
            "Activation Code: *319*92#\n"
            "Super Internet on TikTok and YouTube: 1 MB = 1 Super MB\n"
            "-------------------\n"
            "Based ONLY on the context above, answer: What is the USSD activation code, total price with tax, and total units for Hekaya Mixat 92?"
        ),
        "max_tokens": 200,
        "temperature": 0.0,
        "validator": lambda r: "*319*92#" in r and "131" in r and "4" in r,
    },
    {
        "id": "5_mcp_tool_calling",
        "category": "5. MCP / Tool Calling",
        "type": "tool_calling",
        "prompt": (
            "You have access to the following tool definition:\n"
            "Tool: calculate_price(base_price: float, is_tax_inclusive: bool, tax_type: str)\n\n"
            "A customer asks: 'معايا ميزانية 200 جنيه شاملة الضريبة، احسبلي الرصيد الصافي قبل الضريبة'.\n"
            "Select and format the tool call in valid JSON format:\n"
            '{"tool": "calculate_price", "parameters": {"base_price": 200.0, "is_tax_inclusive": true, "tax_type": "prepaid"}}'
        ),
        "max_tokens": 150,
        "temperature": 0.0,
        "validator": lambda r: "calculate_price" in r and ("200" in r or "parameters" in r),
    },
    {
        "id": "6_structured_output",
        "category": "6. Structured JSON",
        "type": "json_schema",
        "prompt": (
            "Extract customer profiling into JSON adhering to this exact schema:\n"
            '{"service": "Hekaya", "sub_track": "Mixat", "budget_egp": 120.0, "needs_clarification": false, "language": "ar"}\n\n'
            "Customer query: 'عايز باقة حكاية مكسات في حدود 120 جنيه'\n"
            "Output ONLY the valid JSON object without markdown or commentary:"
        ),
        "max_tokens": 150,
        "temperature": 0.0,
        "validator": lambda r: _validate_json_schema(r),
    },
    {
        "id": "7_multistep_agent",
        "category": "7. Multi-Step Agent",
        "type": "agent_workflow",
        "prompt": (
            "System: You are an autonomous telecom sales agent.\n"
            "Step 1: Understand user constraint (Budget: 150 EGP total including tax, primarily calls).\n"
            "Step 2: Compare Hekaya Mixat 69 (total ~98.58 EGP) vs Hekaya Mixat 92 (total ~131.44 EGP) vs Hekaya Mixat 120 (total ~171.44 EGP).\n"
            "Step 3: Provide the single highest package within the 150 EGP budget, with exact pre-tax price, total price, and USSD code.\n\n"
            "Give your concise step-by-step reasoning and final recommendation."
        ),
        "max_tokens": 400,
        "temperature": 0.1,
        "validator": lambda r: "92" in r and ("131" in r or "98" in r or "319" in r),
    },
]


def _validate_json_schema(text: str) -> bool:
    try:
        clean = text.strip()
        start = clean.find("{")
        end = clean.rfind("}") + 1
        if start >= 0 and end > start:
            parsed = json.loads(clean[start:end])
            return isinstance(parsed, dict) and "service" in parsed
    except Exception:
        pass
    return False


@dataclass
class ScenarioResult:
    scenario_id: str
    category: str
    prompt: str
    response: str
    success: bool
    latency_s: float
    ttft_s: float
    tokens_generated: int
    tokens_per_second: float
    vram_used_mb: int
    vram_total_mb: int
    gpu_temp_c: int
    gpu_util_pct: int
    ram_used_mb: int
    cpu_util_pct: float
    error: Optional[str] = None


@dataclass
class BenchmarkSuiteSummary:
    model: str
    timestamp: str
    hardware_name: str
    vram_dedicated_mb: int
    vram_reported_mb: int
    total_ram_mb: int
    results: List[ScenarioResult] = field(default_factory=list)
    total_duration_s: float = 0.0


def check_ollama() -> bool:
    try:
        r = requests.get(f"{BASE_URL}/api/tags", timeout=3)
        return r.status_code == 200
    except Exception:
        return False


def get_gpu_telemetry() -> Dict[str, Any]:
    """
    Get detailed GPU metrics via nvidia-smi.
    Distinguishes Dedicated VRAM vs WDDM Shared memory.
    """
    try:
        res = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=name,memory.used,memory.total,temperature.gpu,utilization.gpu,power.draw",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            text=True,
            timeout=3,
        )
        if res.returncode == 0:
            parts = [p.strip() for p in res.stdout.strip().split(",")]
            return {
                "name": parts[0],
                "vram_used_mb": int(parts[1]),
                "vram_total_mb": int(parts[2]),
                "temp_c": int(parts[3]),
                "gpu_util_pct": int(parts[4]),
                "power_w": float(parts[5]) if parts[5] != "N/A" else 0.0,
            }
    except Exception:
        pass
    return {
        "name": "NVIDIA GPU (RTX 4050)",
        "vram_used_mb": 0,
        "vram_total_mb": 4096,
        "temp_c": 0,
        "gpu_util_pct": 0,
        "power_w": 0.0,
    }


def get_system_telemetry() -> Dict[str, Any]:
    if not HAS_PSUTIL:
        return {"ram_used_mb": 0, "ram_total_mb": 16384, "cpu_pct": 0.0}
    vm = psutil.virtual_memory()
    cpu_pct = psutil.cpu_percent(interval=None)
    return {
        "ram_used_mb": int(vm.used / (1024 * 1024)),
        "ram_total_mb": int(vm.total / (1024 * 1024)),
        "cpu_pct": cpu_pct,
    }


def run_single_inference(
    model: str,
    prompt: str,
    max_tokens: int,
    temperature: float = 0.2,
) -> Dict[str, Any]:
    """Execute streaming inference to measure TTFT and total generation metrics."""
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": True,
        "options": {
            "num_predict": max_tokens,
            "temperature": temperature,
            "num_ctx": 4096,
        },
    }

    t0 = time.perf_counter()
    ttft = 0.0
    full_text = []
    eval_count = 0

    try:
        with requests.post(
            f"{BASE_URL}/api/generate",
            json=payload,
            timeout=180,
            stream=True,
        ) as resp:
            if resp.status_code != 200:
                elapsed = time.perf_counter() - t0
                return {"error": f"HTTP {resp.status_code}: {resp.text[:150]}", "latency_s": elapsed, "ttft_s": 0.0}

            for line in resp.iter_lines():
                if line:
                    if ttft == 0.0:
                        ttft = time.perf_counter() - t0
                    try:
                        chunk = json.loads(line.decode("utf-8"))
                        full_text.append(chunk.get("response", ""))
                        if chunk.get("done"):
                            eval_count = chunk.get("eval_count", len("".join(full_text).split()))
                    except Exception:
                        pass

        total_elapsed = time.perf_counter() - t0
        output_str = "".join(full_text)
        if eval_count == 0:
            eval_count = max(1, len(output_str.split()) * 4 // 3)

        gen_time = max(0.001, total_elapsed - ttft)
        tok_per_sec = eval_count / gen_time if gen_time > 0 else 0.0

        return {
            "response": output_str,
            "latency_s": total_elapsed,
            "ttft_s": ttft if ttft > 0 else total_elapsed,
            "eval_count": eval_count,
            "tokens_per_second": tok_per_sec,
        }

    except Exception as exc:
        total_elapsed = time.perf_counter() - t0
        return {"error": str(exc), "latency_s": total_elapsed, "ttft_s": 0.0}


def run_benchmark(model: str = DEFAULT_MODEL) -> BenchmarkSuiteSummary:
    print(f"\n{'='*64}")
    print(f"  e& Egypt Agentic KB — Local LLM E2E Benchmark Suite")
    print(f"  Model:      {model}")
    print(f"  Endpoint:   {BASE_URL}")
    print(f"  Timestamp:  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*64}\n")

    if not check_ollama():
        print(f"[ERROR] Ollama is not responding at {BASE_URL}.")
        print(f"        Please start it using: scripts\\start_local_ai.bat")
        sys.exit(1)

    gpu_init = get_gpu_telemetry()
    sys_init = get_system_telemetry()

    summary = BenchmarkSuiteSummary(
        model=model,
        timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        hardware_name=gpu_init["name"],
        vram_dedicated_mb=4096,
        vram_reported_mb=gpu_init["vram_total_mb"],
        total_ram_mb=sys_init["ram_total_mb"],
    )

    total_start = time.perf_counter()

    for idx, scenario in enumerate(BENCHMARK_SCENARIOS):
        print(f"[{idx+1}/{len(BENCHMARK_SCENARIOS)}] {scenario['category']}")
        print(f"    Prompt: {scenario['prompt'][:75]}...")

        # Sample pre-inference system state
        if HAS_PSUTIL:
            psutil.cpu_percent(interval=None)

        res = run_single_inference(
            model=model,
            prompt=scenario["prompt"],
            max_tokens=scenario["max_tokens"],
            temperature=scenario["temperature"],
        )

        gpu_now = get_gpu_telemetry()
        sys_now = get_system_telemetry()

        if "error" in res:
            print(f"    [FAIL] Error: {res['error']}")
            r_obj = ScenarioResult(
                scenario_id=scenario["id"],
                category=scenario["category"],
                prompt=scenario["prompt"],
                response="",
                success=False,
                latency_s=round(res["latency_s"], 2),
                ttft_s=round(res.get("ttft_s", 0.0), 2),
                tokens_generated=0,
                tokens_per_second=0.0,
                vram_used_mb=gpu_now["vram_used_mb"],
                vram_total_mb=gpu_now["vram_total_mb"],
                gpu_temp_c=gpu_now["temp_c"],
                gpu_util_pct=gpu_now["gpu_util_pct"],
                ram_used_mb=sys_now["ram_used_mb"],
                cpu_util_pct=sys_now["cpu_pct"],
                error=res["error"],
            )
        else:
            response_text = res["response"]
            is_valid = scenario["validator"](response_text)
            status_tag = "[PASS]" if is_valid else "[WARN: Output Check Failed]"

            print(
                f"    {status_tag} {res['latency_s']:.2f}s (TTFT: {res['ttft_s']:.2f}s) | "
                f"{res['eval_count']} tok | {res['tokens_per_second']:.1f} tok/s | "
                f"VRAM: {gpu_now['vram_used_mb']}/{gpu_now['vram_total_mb']} MB ({gpu_now['temp_c']}°C)"
            )

            r_obj = ScenarioResult(
                scenario_id=scenario["id"],
                category=scenario["category"],
                prompt=scenario["prompt"],
                response=response_text,
                success=is_valid,
                latency_s=round(res["latency_s"], 2),
                ttft_s=round(res["ttft_s"], 2),
                tokens_generated=res["eval_count"],
                tokens_per_second=round(res["tokens_per_second"], 1),
                vram_used_mb=gpu_now["vram_used_mb"],
                vram_total_mb=gpu_now["vram_total_mb"],
                gpu_temp_c=gpu_now["temp_c"],
                gpu_util_pct=gpu_now["gpu_util_pct"],
                ram_used_mb=sys_now["ram_used_mb"],
                cpu_util_pct=sys_now["cpu_pct"],
            )

        summary.results.append(r_obj)
        print()

    summary.total_duration_s = round(time.perf_counter() - total_start, 1)
    return summary


def generate_benchmark_markdown(summary: BenchmarkSuiteSummary) -> str:
    passed = [r for r in summary.results if r.success]
    avg_lat = sum(r.latency_s for r in passed) / len(passed) if passed else 0.0
    avg_ttft = sum(r.ttft_s for r in passed) / len(passed) if passed else 0.0
    avg_tps = sum(r.tokens_per_second for r in passed) / len(passed) if passed else 0.0
    peak_vram = max((r.vram_used_mb for r in summary.results), default=0)
    max_temp = max((r.gpu_temp_c for r in summary.results), default=0)

    lines = [
        "# Local LLM Benchmark Report — e& Egypt Agentic KB",
        "",
        f"**Date**: `{summary.timestamp}`  ",
        f"**Model Evaluated**: `{summary.model}`  ",
        f"**Hardware Target**: Lenovo Legion Slim 5i (`{summary.hardware_name}`)  ",
        f"**GPU Memory Architecture**: 4GB Dedicated GDDR6 VRAM (Reported by WDDM: {summary.vram_reported_mb} MB total including shared)  ",
        f"**System Memory**: {summary.total_ram_mb} MB RAM  ",
        f"**Total Suite Duration**: {summary.total_duration_s}s",
        "",
        "---",
        "",
        "## Performance Executive Summary",
        "",
        "| Key Metric | Measured Value | Target SLA / Safety Status |",
        "|---|---|---|",
        f"| **Test Pass Rate** | **{len(passed)} / {len(summary.results)}** ({len(passed)/len(summary.results)*100:.0f}%) | 100% Core Scenarios |",
        f"| **Average Latency** | **{avg_lat:.2f}s** | < 8.0s (Interactive) |",
        f"| **Avg Time-To-First-Token (TTFT)** | **{avg_ttft:.2f}s** | < 1.0s (Instantaneous) |",
        f"| **Average Generation Speed** | **{avg_tps:.1f} tokens/sec** | > 40 tok/s Target |",
        f"| **Peak VRAM Consumed** | **{peak_vram} MB** | Safe within 4,096 MB VRAM (< 3,800 MB limit) |",
        f"| **Peak GPU Temperature** | **{max_temp}°C** | Normal Thermal Zone (< 80°C) |",
        "",
        "---",
        "",
        "## Detailed Scenario Matrix",
        "",
        "| # | Scenario | Latency | TTFT | Speed | VRAM Used | Temp | RAM | Status |",
        "|---|---|---|---|---|---|---|---|---|",
    ]

    for idx, r in enumerate(summary.results):
        status_icon = "✅ PASS" if r.success else "❌ FAIL"
        lines.append(
            f"| {idx+1} | {r.category} | {r.latency_s}s | {r.ttft_s}s | "
            f"{r.tokens_per_second} tok/s | {r.vram_used_mb} MB | {r.gpu_temp_c}°C | "
            f"{r.ram_used_mb} MB | {status_icon} |"
        )

    lines += [
        "",
        "---",
        "",
        "## Detailed Prompts & Model Outputs",
        "",
    ]

    for idx, r in enumerate(summary.results):
        lines += [
            f"### {idx+1}. {r.category}",
            f"- **Latency**: `{r.latency_s}s` | **TTFT**: `{r.ttft_s}s` | **Speed**: `{r.tokens_per_second} tok/s`",
            f"- **Telemetry**: VRAM `{r.vram_used_mb} MB` | GPU Temp `{r.gpu_temp_c}°C` | CPU `{r.cpu_util_pct}%`",
            "",
            "**Input Prompt**:",
            f"```text\n{r.prompt}\n```",
            "",
            "**Model Output**:",
            f"```text\n{r.response if r.response else r.error}\n```",
            "",
        ]

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Run Production Local LLM Benchmark")
    parser.add_argument("--model", default=DEFAULT_MODEL, help="Ollama model tag to benchmark")
    parser.add_argument(
        "--output",
        default=str(OUTPUT_DIR / "benchmark_report.md"),
        help="Path to output markdown report",
    )
    args = parser.parse_args()

    summary = run_benchmark(args.model)
    report_md = generate_benchmark_markdown(summary)

    out_path = Path(args.output)
    out_path.write_text(report_md, encoding="utf-8")

    print(f"{'='*64}")
    print(f"  Benchmark Completed Successfully!")
    print(f"  Pass Rate: {sum(1 for r in summary.results if r.success)}/{len(summary.results)}")
    print(f"  Report written to: {out_path}")
    print(f"{'='*64}\n")


if __name__ == "__main__":
    main()
