# Dataset Doctor

Dataset Doctor is an AI-assisted data quality and ML-readiness platform designed to inspect raw datasets deterministically using Python, detect structural, statistical, and modeling issues, compute an explainable **ML Readiness Heuristic**, and synthesize an actionable cleaning and pipeline-preparation plan via an AI domain interpreter.

> **Status:** `Phase 1 complete — Ingestion, Parquet normalization, immutable versioning, and preview API operational.`

---

## Core Architectural Principle

**Python calculates factual statistics and findings. The LLM interprets those structured findings. The LLM is never responsible for calculating raw statistics.**

---

## Architecture Overview

Dataset Doctor decouples deterministic data analysis from AI interpretation:
1. **Deterministic Core (`app/engine`)**: Modular analyzers implementing `BaseAnalyzer` calculate exact statistics, null rates, correlations, distributions, and outliers with full provenance (`QualityIssueData`).
2. **Explainable Heuristic (`app/engine/scoring.py`)**: Computes an explainable ML Readiness Heuristic (0–100) with transparent, itemized deductions.
3. **AI Interpretation Layer (`app/services/ai_provider.py`)**: Abstracted provider boundary supporting structured reasoning via modern Responses API paradigms.
4. **Isolated Job Runner (`app/services/job_runner.py`)**: Asynchronous `ThreadPoolJobRunner` (V1) executing heavy analysis out-of-band without blocking FastAPI's event loop.
5. **Persistence & Versioning (`app/models`)**: Immutable dataset versioning via PostgreSQL 16 and async SQLAlchemy 2.0.

---

## Technology Stack

- **Runtime**: Python 3.13
- **Web Framework**: FastAPI & Uvicorn
- **Configuration & Validation**: Pydantic v2 & Pydantic-Settings
- **Database & ORM**: PostgreSQL 16, SQLAlchemy 2.0 (asyncpg), Alembic
- **Analytics Engine**: pandas, NumPy, SciPy, scikit-learn
- **Containerization**: Docker & Docker Compose
- **Testing**: pytest, pytest-asyncio, httpx

---

## Environment Variables

| Variable | Default Value | Description |
| :--- | :--- | :--- |
| `APP_NAME` | `"Dataset Doctor"` | Name of the application |
| `ENVIRONMENT` | `"development"` | Runtime environment (`development`, `staging`, `production`, `testing`) |
| `DEBUG` | `false` | Enable debug logs & SQL echoing |
| `DATABASE_URL` | `postgresql+asyncpg://postgres:postgres@localhost:5432/dataset_doctor` | Async PostgreSQL connection string |
| `UPLOAD_DIR` | `"uploads"` | Directory for dataset storage |
| `MAX_UPLOAD_SIZE_MB`| `100` | Maximum allowed file upload size in MB |
| `LOG_LEVEL` | `"INFO"` | Logging verbosity (`DEBUG`, `INFO`, `WARNING`, `ERROR`) |
| `MAX_WORKER_THREADS`| `4` | Worker threads for analysis job runner |
| `OPENAI_API_KEY` | `""` | OpenAI API key placeholder |
| `OPENAI_MODEL` | `"gpt-4o-2024-08-06"` | Target model for AI interpretation |

---

## Installation & Setup

### 1. Local Virtual Environment Setup

```bash
# Clone the repository
git clone <repo-url>
cd dataset-doctor

# Copy environment configuration
cp .env.example .env

# Create virtual environment with Python 3.13 (via uv or venv)
uv venv --python 3.13 .venv
.\.venv\Scripts\activate

# Install dependencies in editable mode with development tools
uv pip install -e ".[dev]"
```

### 2. Run with Docker Compose

To spin up PostgreSQL 16 and the FastAPI application in isolated containers:

```bash
docker compose up --build
```

Access the service:
- Health check: `http://localhost:8000/health`
- Swagger API Docs: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`

### 3. Local Development Server

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### 4. Running Automated Tests

```bash
pytest -v
```
