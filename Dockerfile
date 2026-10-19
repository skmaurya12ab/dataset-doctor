# ==============================================================================
# Dataset Doctor - Production Dockerfile
# Base Image: Python 3.13 Slim
# ==============================================================================
FROM python:3.13-slim AS base

# Prevent Python from writing .pyc files and enable unbuffered output
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=off \
    PIP_DISABLE_PIP_VERSION_CHECK=on

# Set working directory
WORKDIR /app

# Install system dependencies (curl for healthcheck, build-essential if needed)
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    curl \
    && update-ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Install uv for fast package installation
COPY --from=ghcr.io/astral-sh/uv:0.5.11 /uv /bin/uv

# Copy dependency configuration files
COPY pyproject.toml README.md ./

# Install python dependencies without the root editable package first (layer caching)
RUN uv pip install --system -e .

# Copy application source code
COPY app/ ./app/
COPY alembic/ ./alembic/
COPY alembic.ini .

# Create uploads directory and non-privileged user for security
ENV UPLOAD_DIR=/app/uploads
RUN mkdir -p /app/uploads /app/storage && \
    useradd -u 1000 -m appuser && \
    chown -R appuser:appuser /app

USER appuser


# Expose the documented local fallback port. Render supplies PORT at runtime; EXPOSE is metadata.
EXPOSE 8000

# Dockerfile HEALTHCHECK uses CMD shell form; CMD-SHELL is Compose-only syntax.
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl --fail --silent --show-error --max-time 4 "http://127.0.0.1:${PORT:-8000}/health" >/dev/null || exit 1

# Launch uvicorn server
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
