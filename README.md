# Dataset Doctor

Dataset Doctor is an AI-assisted data quality and ML-readiness platform designed to inspect raw datasets deterministically using Python, detect structural, statistical, and modeling issues, compute an explainable **ML Readiness Heuristic**, and synthesize an actionable cleaning and pipeline-preparation plan via an AI domain interpreter.

> **Status:** `Phase 3 complete — Advanced statistical & ML analysis engine operational across 10 deterministic profiling modules with ML Readiness Heuristic, PostgreSQL persistence, provenance tracking, and REST API.`

### Project Roadmap Status
- **Phase 0 — Foundations & Core Abstractions**: ✅
- **Phase 1 — Ingestion & Immutable Dataset Versioning**: ✅
- **Phase 2 — Core Deterministic Analysis**: ✅
- **Phase 3 — Advanced Statistical & ML Analysis**: ✅
- **Phase 4 — AI Remediation & Action Planning**: 🚧 Next

---

## Core Architectural Principle

**Python calculates factual statistics and findings. The LLM interprets those structured findings. The LLM is never responsible for calculating raw statistics.**

---

## Current Supported Capabilities

The deterministic analysis pipeline profiles datasets across ten dedicated modules followed by the explainable heuristic:

### Phase 2 Core Quality Analyzers
1. **Schema Analyzer (`schema_analyzer`, v1.0.0)**: Duplicate column headers, blank headers, unicode preservation.
2. **Data Type Analyzer (`dtype_analyzer`, v1.0.0)**: Conceptual taxonomy mapping, mixed scalar types, nested structures, parseable strings.
3. **Missing Value Analyzer (`missing_analyzer`, v1.0.0)**: Null value rates, blank string classification, tiered severity ($>0-5\%$ LOW, $>5-20\%$ MEDIUM, $>20-40\%$ HIGH, $>40\%$ CRITICAL).
4. **Duplicate Analyzer (`duplicate_analyzer`, v1.0.0)**: Exact record duplication rates with complete cluster member accounting.
5. **Cardinality Analyzer (`cardinality_analyzer`, v1.0.0)**: Constant features, near-constant variance, high-cardinality categoricals, identifier detection.

### Phase 3 Advanced Statistical & ML Analyzers
6. **Outlier Analyzer (`outlier_analyzer`, v1.0.0)**:
   - Method A: Interquartile Range (IQR) with zero-IQR suppression.
   - Method B: Median Absolute Deviation (MAD) with robust modified Z-score thresholds.
   - Method C: Multivariate Isolation Forest with deterministic sampling.
   - Tiered severity based on percentage of affected rows.
7. **Distribution Analyzer (`distribution_analyzer`, v1.0.0)**:
   - Summary statistics (mean, median, std, min, max, quartiles).
   - Fisher-Pearson skewness severity ($1-2$ LOW, $2-3$ MEDIUM, $\ge 3$ HIGH).
   - Fisher excess kurtosis calculation.
   - SciPy D'Agostino's $K^2$ omnibus normality test (`dagostino_k_squared`).
8. **Correlation Analyzer (`correlation_analyzer`, v1.0.0)**:
   - Pairwise Pearson and Spearman correlation across non-constant numeric features.
   - Unique upper-triangle pairs only (no duplicate permutations, no self-correlations).
   - Multicollinearity thresholds ($0.90-0.95$ LOW, $0.95-0.99$ MEDIUM, $\ge 0.99$ HIGH).
   - Separate target correlation profiling.
   - Computational safeguards (`MAX_CORRELATION_FEATURES`, row sampling).
9. **Class Imbalance Analyzer (`imbalance_analyzer`, v1.0.0)**:
   - Evaluates target label distribution for classification tasks.
   - Binary imbalance ratios and severity ($>60\%$ LOW, $>75\%$ MEDIUM, $>90\%$ HIGH, $>95\%$ CRITICAL).
   - Multiclass concentration analysis.
   - Advisory detection for tiny classes ($< 10$ samples).
10. **Data Leakage Analyzer (`leakage_analyzer`, v1.0.0)**:
    - Signal A: Target identity and near-identity ($\ge 0.99$ match ratio).
    - Signal B: Extreme Pearson correlation with target ($\ge 0.99$).
    - Signal C: Categorical conditional purity ($\ge 0.99$).
    - Signal D: Suspicious naming scan (strictly advisory INFO, never elevated based on name alone).
11. **ML Readiness Heuristic Scorer (`scoring.py`, v1.0.0)**:
    - Transparent deduction system (CRITICAL: 25, HIGH: 10, MEDIUM: 4, LOW: 1, INFO: 0).
    - Single-column penalty deduplication cap (max 25.0 points per column).
    - Descriptive rating tiers: Production-oriented readiness, Minor remediation, Significant preprocessing, High risk / substantial remediation.
    - Full itemized penalty breakdown API with provenance disclaimer.


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
