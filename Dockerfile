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
    curl \
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
RUN mkdir -p uploads storage && \
    useradd -u 1000 -m appuser && \
    chown -R appuser:appuser /app

USER appuser

# Expose FastAPI HTTP port
EXPOSE 8000

# Container healthcheck
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Launch uvicorn server
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
