"""
monitor.py
----------
Live terminal dashboard for monitoring GPU/RAM/CPU during inference.
Refreshes every 2 seconds.

Usage:
    py -3.12 scripts/monitor.py
    py -3.12 scripts/monitor.py --interval 1

Requirements:
    pip install psutil requests

Press Ctrl+C to exit.
"""
import argparse
import os
import subprocess
import sys
import time
from datetime import datetime

try:
    import psutil
    HAS_PSUTIL = True
except ImportError:
    HAS_PSUTIL = False

try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False

from dotenv import load_dotenv

load_dotenv()

BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5:3b")

# ANSI colors
RED = "\033[91m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
CYAN = "\033[96m"
BOLD = "\033[1m"
RESET = "\033[0m"
CLEAR = "\033c"


def get_gpu_info() -> dict:
    try:
        result = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=name,memory.used,memory.total,temperature.gpu,utilization.gpu,power.draw",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True, text=True, timeout=3,
        )
        if result.returncode == 0:
            parts = [p.strip() for p in result.stdout.strip().split(",")]
            return {
                "name": parts[0],
                "vram_used": int(parts[1]),
                "vram_total": int(parts[2]),
                "temp": int(parts[3]),
                "util": int(parts[4]),
                "power": float(parts[5]) if parts[5] != "N/A" else 0.0,
            }
    except Exception:
        pass
    return {"name": "N/A", "vram_used": 0, "vram_total": 0, "temp": 0, "util": 0, "power": 0.0}


def get_ram_info() -> dict:
    if not HAS_PSUTIL:
        return {"used": 0, "total": 0, "pct": 0}
    mem = psutil.virtual_memory()
    return {
        "used": int(mem.used / 1024 / 1024),
        "total": int(mem.total / 1024 / 1024),
        "pct": mem.percent,
    }


def get_cpu_info() -> dict:
    if not HAS_PSUTIL:
        return {"pct": 0, "freq_ghz": 0}
    cpu_pct = psutil.cpu_percent(interval=None)
    freq = psutil.cpu_freq()
    return {"pct": cpu_pct, "freq_ghz": round(freq.current / 1000, 2) if freq else 0}


def check_ollama() -> bool:
    if not HAS_REQUESTS:
        return False
    try:
        r = requests.get(f"{BASE_URL}/api/tags", timeout=2)
        return r.status_code == 200
    except Exception:
        return False


def get_loaded_models() -> list:
    if not HAS_REQUESTS:
        return []
    try:
        r = requests.get(f"{BASE_URL}/api/ps", timeout=2)
        if r.status_code == 200:
            data = r.json()
            return [m.get("name", "?") for m in data.get("models", [])]
    except Exception:
        pass
    return []


def bar(value: float, total: float, width: int = 20, color: str = GREEN) -> str:
    if total <= 0:
        return "[" + "?" * width + "]"
    filled = int(width * value / total)
    pct = value / total * 100
    bar_str = "█" * filled + "░" * (width - filled)
    color_to_use = color
    if pct > 80:
        color_to_use = RED
    elif pct > 60:
        color_to_use = YELLOW
    return f"{color_to_use}[{bar_str}]{RESET} {pct:.0f}%"


def render_dashboard(gpu: dict, ram: dict, cpu: dict, ollama_up: bool, loaded: list):
    now = datetime.now().strftime("%H:%M:%S")
    status = f"{GREEN}● RUNNING{RESET}" if ollama_up else f"{RED}✗ STOPPED{RESET}"
    loaded_str = ", ".join(loaded) if loaded else "none"

    lines = [
        f"{BOLD}{CYAN}{'='*56}{RESET}",
        f"{BOLD}  e& Egypt Local AI Monitor          {now}{RESET}",
        f"{BOLD}{CYAN}{'='*56}{RESET}",
        f"",
        f"  {BOLD}Ollama Status:{RESET}  {status}",
        f"  {BOLD}Model in VRAM:{RESET}  {loaded_str}",
        f"  {BOLD}Target Model:{RESET}   {MODEL}",
        f"",
        f"  {BOLD}── GPU: {gpu['name']} ──────────────────────────{RESET}",
        f"  VRAM    {bar(gpu['vram_used'], gpu['vram_total'])}  {gpu['vram_used']}/{gpu['vram_total']} MB",
        f"  Util    {bar(gpu['util'], 100)}  {gpu['util']}%",
        f"  Power   {gpu['power']:.0f} W",
        f"  Temp    {'🟢' if gpu['temp'] < 75 else '🟡' if gpu['temp'] < 85 else '🔴'} {gpu['temp']}°C",
        f"",
        f"  {BOLD}── System ──────────────────────────────────────{RESET}",
        f"  RAM     {bar(ram['used'], ram['total'])}  {ram['used']}/{ram['total']} MB",
        f"  CPU     {bar(cpu['pct'], 100)}  {cpu['pct']}%  @ {cpu['freq_ghz']} GHz",
        f"",
        f"  {BOLD}── Thresholds (RTX 4050 4GB VRAM) ─────────────{RESET}",
        f"  VRAM safe zone:  < 3800 MB  {'✅' if gpu['vram_used'] < 3800 else '⚠️ NEAR LIMIT'}",
        f"  Temperature safe: < 85°C   {'✅' if gpu['temp'] < 85 else '⚠️ HIGH TEMP'}",
        f"",
        f"  {CYAN}Press Ctrl+C to exit{RESET}",
        f"{BOLD}{CYAN}{'='*56}{RESET}",
    ]
    print(CLEAR + "\n".join(lines))


def main():
    parser = argparse.ArgumentParser(description="Live GPU/RAM monitor for local LLM")
    parser.add_argument("--interval", type=float, default=2.0, help="Refresh interval in seconds")
    args = parser.parse_args()

    if not HAS_PSUTIL:
        print("[WARN] Install psutil for RAM/CPU metrics: pip install psutil")
    if not HAS_REQUESTS:
        print("[WARN] Install requests for Ollama status: pip install requests")

    print(f"Starting monitor (interval={args.interval}s)...")
    time.sleep(1)

    # Initial CPU measurement
    if HAS_PSUTIL:
        psutil.cpu_percent(interval=None)

    try:
        while True:
            gpu = get_gpu_info()
            ram = get_ram_info()
            cpu = get_cpu_info()
            ollama_up = check_ollama()
            loaded = get_loaded_models()
            render_dashboard(gpu, ram, cpu, ollama_up, loaded)
            time.sleep(args.interval)
    except KeyboardInterrupt:
        print("\n[INFO] Monitor stopped.")


if __name__ == "__main__":
    main()
