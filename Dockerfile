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

# Install system dependencies required for sentence-transformers + chromadb
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    git \
    && rm -rf /var/lib/apt/lists/*

# ── Install Python dependencies ───────────────────────────────────────────────
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip setuptools wheel \
    && pip install --no-cache-dir --extra-index-url https://download.pytorch.org/whl/cpu -r requirements.txt

# ── Copy application source ───────────────────────────────────────────────────
COPY app/ ./app/
COPY evaluation/ ./evaluation/
COPY site/ ./site/

# Copy pre-built ChromaDB vector store (skip if rebuilding inside container)
COPY chroma_db/ ./chroma_db/

# Set non-root ownership
RUN chown -R appuser:appgroup /app

# ── Runtime stage ─────────────────────────────────────────────────────────────
FROM base AS runtime

USER appuser

WORKDIR /app

# Expose FastAPI port
EXPOSE 8000

# Health check (aligns with /health endpoint)
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Environment defaults (override with --env-file or -e flags)
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONPATH=/app

# Start server
CMD ["uvicorn", "app.api:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
