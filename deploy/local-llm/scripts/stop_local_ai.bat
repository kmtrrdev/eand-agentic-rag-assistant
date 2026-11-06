@echo off
:: ============================================================
:: stop_local_ai.bat
:: Production-ready script to unload models and stop Ollama safely
:: Usage:
::   stop_local_ai.bat          -> Unloads models and stops Ollama
::   stop_local_ai.bat --unload -> Unloads models from VRAM only (keeps Ollama running)
:: ============================================================

setlocal EnableDelayedExpansion

echo.
echo ========================================================
echo   e^& Egypt Local AI — Shutdown / VRAM Cleanup Script
echo ========================================================
echo.

:: ── Step 1: Gracefully unload loaded models from VRAM ─────────
echo [INFO] Querying loaded models in VRAM...
for /f "tokens=*" %%M in ('curl -s http://localhost:11434/api/ps 2^>nul ^| findstr /C:"name"') do (
    echo [INFO] Found loaded model entry: %%M
)

:: Unload qwen models from VRAM by setting keep_alive to 0 (does NOT delete model weights)
echo [INFO] Evicting active models from RTX 4050 VRAM...
curl -s -X POST http://localhost:11434/api/generate ^
    -H "Content-Type: application/json" ^
    -d "{\"model\": \"qwen2.5:3b\", \"keep_alive\": 0}" >nul 2>&1

curl -s -X POST http://localhost:11434/api/generate ^
    -H "Content-Type: application/json" ^
    -d "{\"model\": \"qwen2.5:7b\", \"keep_alive\": 0}" >nul 2>&1

if /i "%~1"=="--unload" (
    echo [OK] Active models unloaded from GPU VRAM. Ollama server remains online.
    goto :check_gpu
)

:: ── Step 2: Stop Ollama Server Process ────────────────────────
echo [INFO] Stopping Ollama server processes...
taskkill /F /IM ollama.exe /T >nul 2>&1
taskkill /F /IM ollama_llama_server.exe /T >nul 2>&1

timeout /t 1 /nobreak >nul

:: Verify stopped
curl -s --max-time 2 http://localhost:11434/api/tags >nul 2>&1
if errorlevel 1 (
    echo [OK] Ollama server has been completely stopped.
) else (
    echo [WARN] Ollama process is still running on port 11434.
)

:check_gpu
echo.
echo [INFO] GPU Status after cleanup:
nvidia-smi --query-gpu=name,memory.used,memory.total,temperature.gpu ^
    --format=csv,noheader,nounits 2>nul
if errorlevel 1 (
    echo [WARN] nvidia-smi not available.
)

echo.
echo [OK] Cleanup complete.
echo.
endlocal
