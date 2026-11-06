@echo off
:: ============================================================
:: start_local_ai.bat
:: Production-ready Startup Script for Local Ollama LLM
:: Target Hardware: Lenovo Legion Slim 5i (RTX 4050 4GB VRAM / 16GB RAM)
:: ============================================================

setlocal EnableDelayedExpansion

echo.
echo ========================================================
echo   e^& Egypt Local AI — Production Startup Script
echo   Hardware Target: RTX 4050 Laptop (4GB VRAM) / 16GB RAM
echo ========================================================
echo.

:: ── Locate .env file ─────────────────────────────────────────
set "ENV_FILE=%~dp0..\.env"
if not exist "%ENV_FILE%" (
    set "ENV_FILE=%~dp0.env"
)

:: Default settings
set "MODEL=deepseek-r1:7b"
set "LLM_PROFILE=DEEPSEEK_R1_7B"
set "OLLAMA_NUM_PARALLEL=1"
set "OLLAMA_MAX_LOADED_MODELS=1"
set "OLLAMA_KEEP_ALIVE=5m"
set "OLLAMA_FLASH_ATTENTION=1"
set "CUDA_VISIBLE_DEVICES=0"

:: ── Read from .env if present ───────────────────────────────
if exist "%ENV_FILE%" (
    echo [INFO] Loading configuration from %ENV_FILE%
    for /f "usebackq tokens=1,* delims==" %%A in ("%ENV_FILE%") do (
        set "KEY=%%A"
        set "VAL=%%B"
        :: Strip leading/trailing spaces
        for /f "tokens=* delims= " %%k in ("!KEY!") do set "KEY=%%k"
        if not "!KEY!"=="" if not "!KEY:~0,1!"=="#" (
            if "!KEY!"=="OLLAMA_MODEL" set "MODEL=!VAL!"
            if "!KEY!"=="LLM_PROFILE" set "LLM_PROFILE=!VAL!"
            if "!KEY!"=="OLLAMA_KEEP_ALIVE" set "OLLAMA_KEEP_ALIVE=!VAL!"
            if "!KEY!"=="OLLAMA_NUM_PARALLEL" set "OLLAMA_NUM_PARALLEL=!VAL!"
            if "!KEY!"=="OLLAMA_MAX_LOADED_MODELS" set "OLLAMA_MAX_LOADED_MODELS=!VAL!"
        )
    )
)

:: ── CLI Argument Override ───────────────────────────────────
if /i "%~1"=="deepseek" (
    set "LLM_PROFILE=DEEPSEEK_R1_7B"
    set "MODEL=deepseek-r1:7b"
)
if /i "%~1"=="quality" (
    set "LLM_PROFILE=QUALITY"
    set "MODEL=qwen2.5:7b"
)
if /i "%~1"=="safe" (
    set "LLM_PROFILE=SAFE"
    set "MODEL=qwen2.5:3b"
)

echo [INFO] Profile: %LLM_PROFILE%
echo [INFO] Model:   %MODEL%
echo.

:: ── Check if Ollama is installed ─────────────────────────────
where ollama >nul 2>&1
if errorlevel 1 (
    if exist "%LOCALAPPDATA%\Programs\Ollama\ollama.exe" (
        set "PATH=%LOCALAPPDATA%\Programs\Ollama;%PATH%"
    ) else (
        echo [ERROR] Ollama executable not found in PATH or %LOCALAPPDATA%\Programs\Ollama.
        echo         Please install Ollama from: https://ollama.com/download
        pause
        exit /b 1
    )
)

:: ── Check if Ollama is already running ───────────────────────
curl -s --max-time 2 http://localhost:11434/api/tags >nul 2>&1
if not errorlevel 1 (
    echo [OK] Ollama server is already running.
    goto :check_model
)

:: ── Start Ollama with Environment Variables Applied ──────────
echo [INFO] Starting Ollama server with resource safety settings:
echo         OLLAMA_NUM_PARALLEL      = %OLLAMA_NUM_PARALLEL%
echo         OLLAMA_MAX_LOADED_MODELS = %OLLAMA_MAX_LOADED_MODELS%
echo         OLLAMA_KEEP_ALIVE        = %OLLAMA_KEEP_ALIVE%
echo         OLLAMA_FLASH_ATTENTION   = %OLLAMA_FLASH_ATTENTION%
echo         CUDA_VISIBLE_DEVICES     = %CUDA_VISIBLE_DEVICES%
echo.

start "Ollama Server" /min cmd /c "set OLLAMA_NUM_PARALLEL=%OLLAMA_NUM_PARALLEL%&& set OLLAMA_MAX_LOADED_MODELS=%OLLAMA_MAX_LOADED_MODELS%&& set OLLAMA_KEEP_ALIVE=%OLLAMA_KEEP_ALIVE%&& set OLLAMA_FLASH_ATTENTION=%OLLAMA_FLASH_ATTENTION%&& set CUDA_VISIBLE_DEVICES=%CUDA_VISIBLE_DEVICES%&& ollama serve"

:: ── Wait for Ollama Health Check (max 30s) ───────────────────
echo [INFO] Waiting for Ollama server health check...
set /a attempts=0
:wait_loop
    timeout /t 2 /nobreak >nul
    curl -s --max-time 2 http://localhost:11434/api/tags >nul 2>&1
    if not errorlevel 1 (
        echo [OK] Ollama is healthy and responding on port 11434!
        goto :check_model
    )
    set /a attempts+=1
    if !attempts! geq 15 (
        echo [ERROR] Ollama failed to start after 30 seconds.
        echo         Check if port 11434 is blocked or run "ollama serve" manually.
        pause
        exit /b 1
    )
    echo [INFO] Waiting for server... (!attempts!/15)
    goto :wait_loop

:: ── Ensure Model is Pulled ───────────────────────────────────
:check_model
echo.
echo [INFO] Checking local availability of "%MODEL%"...
ollama list | findstr /C:"%MODEL%" >nul 2>&1
if not errorlevel 1 (
    echo [OK] Model "%MODEL%" is available locally.
    goto :warmup
)

echo [INFO] Model "%MODEL%" not found in local library. Downloading now...
echo        Please wait while Ollama downloads the model weights.
echo.
ollama pull %MODEL%
if errorlevel 1 (
    echo [ERROR] Failed to download model "%MODEL%". Check your network connection.
    pause
    exit /b 1
)
echo [OK] Model download complete.

:: ── Warm Up Model (Load into VRAM) ───────────────────────────
:warmup
echo.
echo [INFO] Warming up model (initial load into RTX 4050 VRAM)...
curl -s -X POST http://localhost:11434/api/generate ^
    -H "Content-Type: application/json" ^
    -d "{\"model\": \"%MODEL%\", \"prompt\": \"hi\", \"stream\": false, \"options\": {\"num_predict\": 2}}" ^
    >nul 2>&1
echo [OK] Model is loaded and responsive.

:: ── GPU Status Check ─────────────────────────────────────────
echo.
echo [INFO] GPU Status:
nvidia-smi --query-gpu=name,temperature.gpu,memory.used,memory.total,utilization.gpu ^
    --format=csv,noheader,nounits 2>nul
if errorlevel 1 (
    echo [WARN] nvidia-smi utility not available.
)

:: ── Ready Summary ────────────────────────────────────────────
echo.
echo ========================================================
echo   LOCAL AI IS PRODUCTION-READY
echo   - Model:       %MODEL% (Profile: %LLM_PROFILE%)
echo   - Ollama API:  http://localhost:11434
echo   - OpenAI API:  http://localhost:11434/v1
echo   - Concurrency: 1 request max (Protected)
echo.
echo   To run benchmark:
echo     py -3.12 local-llm-deploy\scripts\benchmark.py
echo   To run smoke tests:
echo     py -3.12 local-llm-deploy\tests\test_local_llm.py
echo   To run monitor:
echo     py -3.12 local-llm-deploy\scripts\monitor.py
echo ========================================================
echo.

endlocal
