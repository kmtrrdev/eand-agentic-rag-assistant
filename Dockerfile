# ============================================================
# e& Egypt Agentic Knowledge Base - Production Dockerfile
# ============================================================
# Multi-stage build for a lean, secure runtime image.
#
# Usage:
#   docker build -t etisalat-kb .
#   docker run -p 8000:8000 --env-file .env etisalat-kb
#
# Health check:
#   curl http://localhost:8000/health
# ============================================================

FROM python:3.12-slim AS base

# Security: run as non-root user
RUN groupadd -r appgroup && useradd -r -g appgroup -d /app appuser

WORKDIR /app

# Ensure HuggingFace and model cache persist in /app/.cache
ENV HF_HOME=/app/.cache/huggingface
ENV TRANSFORMERS_CACHE=/app/.cache/huggingface
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONPATH=/app

# Install system dependencies required for sentence-transformers + chromadb
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    git \
    && rm -rf /var/lib/apt/lists/*

# ── Install Python dependencies ───────────────────────────────────────────────
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip setuptools wheel \
    && pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu \
    && pip install --no-cache-dir -r requirements.txt --extra-index-url https://download.pytorch.org/whl/cpu

# ── Copy application source ───────────────────────────────────────────────────
COPY app/ ./app/
COPY site/ ./site/

# Pre-cache ML models and build the Chroma vector store at build time
# so the resulting image is 100% self-contained, fast-starting, and offline-ready.
RUN mkdir -p /app/.cache/huggingface && \
    python -c "from sentence_transformers import CrossEncoder, SentenceTransformer; CrossEncoder('cross-encoder/ms-marco-MiniLM-L-6-v2'); SentenceTransformer('sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2')" && \
    python -m app.ingestion.ingest --rebuild

# Set non-root ownership and permissions
RUN chown -R appuser:appgroup /app && chmod -R 775 /app

# ── Runtime stage ─────────────────────────────────────────────────────────────
FROM base AS runtime

USER appuser

WORKDIR /app

# Expose FastAPI port
EXPOSE 8000

# Health check (aligns with /health endpoint)
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Start server
CMD ["uvicorn", "app.api:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]

