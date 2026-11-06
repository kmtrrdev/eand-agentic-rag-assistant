# Local LLM Production Deployment Guide
## e& Egypt Agentic KB — Lenovo Legion Slim 5i (RTX 4050 4GB VRAM / 16GB RAM)

> **Hardware Target**: Lenovo Legion Slim 5i  
> **GPU**: NVIDIA GeForce RTX 4050 Laptop GPU (4 GB Dedicated GDDR6 VRAM)  
> **System RAM**: 16 GB DDR5  
> **Operating System**: Windows 11  

---

## 1. Hardware Profiles & Model Strategy

This deployment provides two tuned hardware profiles tailored for 4GB VRAM laptops:

| Profile | Model | Quantization | VRAM Footprint | Generation Speed | Recommended Use Case |
|---|---|---|---|---|---|
| **`SAFE` (Default)** | `qwen2.5:3b` | 4-bit (`Q4_K_M`) | **~1.9 GB** (100% in VRAM) | **~70–75 tokens/sec** | **Production default**: Zero thermal throttling, instant TTFT (<0.4s), stable. |
| **`QUALITY` (Optional)** | `qwen2.5:7b` | 4-bit (`Q4_K_M`) | **~4.5 GB** (GPU + CPU split) | **~25–35 tokens/sec** | **Enhanced Reasoning**: High Arabic dialect depth, complex multi-hop comparisons. |

---

## 2. Quick Start Commands

### Step 1: Start Local AI Server
Run the production startup script (sets GPU variables, checks health, downloads model if needed, and warms up VRAM):

```batch
local-llm-deploy\scripts\start_local_ai.bat
```

*To start with the optional Quality profile:*
```batch
local-llm-deploy\scripts\start_local_ai.bat quality
```

### Step 2: Run Smoke Tests
Verify Ollama health, OpenAI-compatible `/v1` endpoint, Arabic/English responses, and JSON structured output:

```powershell
py -3.12 local-llm-deploy\tests\test_local_llm.py
```

### Step 3: Run Full End-to-End Benchmark
Tests 7 agentic scenarios (Chat, Arabic, English, Grounded RAG, MCP Tool Calling, Structured JSON, and Multi-Step Agent reasoning):

```powershell
py -3.12 local-llm-deploy\scripts\benchmark.py
```

### Step 4: Stop / Unload VRAM
To unload the active model from GPU VRAM without stopping Ollama:
```batch
local-llm-deploy\scripts\stop_local_ai.bat --unload
```

To fully stop the Ollama server:
```batch
local-llm-deploy\scripts\stop_local_ai.bat
```

---

## 3. Integration with the Main Project (`etisalat-agentic-kb`)

The main Agentic RAG application connects seamlessly to the local LLM via its OpenAI-compatible endpoint (`http://localhost:11434/v1`).

### In `etisalat-agentic-kb/.env`:
```env
# Local LLM settings
LOCAL_LLM_BASE_URL=http://localhost:11434/v1
LOCAL_LLM_MODEL=qwen2.5:3b
LOCAL_LLM_API_KEY=ollama
LLM_MAX_CONCURRENT_REQUESTS=1
```

### Start the FastAPI Server with Local LLM:
```powershell
py -3.12 -m uvicorn app.api:app --host 127.0.0.1 --port 8000 --reload
```

---

## 4. Resource & Concurrency Protection

### Semaphore Enforcement (`LLM_MAX_CONCURRENT_REQUESTS=1`)
On a 4GB VRAM GPU, processing multiple simultaneous inferences causes VRAM thrashing, context swapping, and severe performance degradation.
The application enforces strict single-concurrency queueing:
- **`app/llm/client.py`**: Intercepts requests destined for the local LLM with `threading.Semaphore(1)` and `asyncio.Semaphore(1)` locks.
- **Ollama Environment**: `OLLAMA_NUM_PARALLEL=1`, `OLLAMA_MAX_LOADED_MODELS=1`, `OLLAMA_FLASH_ATTENTION=1`, and `OLLAMA_KEEP_ALIVE=5m`.

---

## 5. Live Telemetry & Monitoring

To monitor GPU VRAM, utilization, power, and temperature during inference:

```powershell
py -3.12 local-llm-deploy\scripts\monitor.py
```

Refreshes every 2 seconds and displays:
- Ollama server status & loaded model in VRAM
- Dedicated VRAM consumed vs 4096 MB hardware limit
- GPU temperature (°C) with thermal warning alerts
- System RAM and CPU utilization

---

## 6. Modelfile Customization

To build a custom Ollama model with embedded system prompt and settings:

```powershell
cd local-llm-deploy
ollama create etisalat-assistant -f ollama/Modelfile
ollama run etisalat-assistant
```

---

## 7. Troubleshooting & FAQ

| Problem | Cause | Solution |
|---|---|---|
| `Ollama not running` | Background service stopped | Run `start_local_ai.bat` or `ollama serve` |
| `VRAM > 3800 MB` | Model too large or parallel requests | Ensure profile is `SAFE` (`qwen2.5:3b`) and `LLM_MAX_CONCURRENT_REQUESTS=1` |
| `GPU Temp > 80°C` | High ambient or prolonged load | Use Lenovo Vantage to set thermal mode to "Performance / Cooling", reduce max tokens |
| `Model not found` | Weights not downloaded | Run `ollama pull qwen2.5:3b` |
| `Structured Output parse error` | Small LLM format deviation | Handled automatically by the built-in JSON parser & deterministic fallback pipeline in `understand_query.py` |
