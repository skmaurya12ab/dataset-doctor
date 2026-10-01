# Phase 2 Completion Report: Core Deterministic Analysis

**Dataset Doctor** has completed and verified **Phase 2: Core Deterministic Analysis**.

---

## 1. Implementation Summary

### 1.1 Files Created
- `app/engine/defaults.py`: Centralized default thresholds and analysis parameters.
- `app/core/json_utils.py`: Recursive serialization converting NumPy scalars, Pandas Timestamps/NaNs/NaTs/NAs safely to JSON primitives with strict boolean precedence.
- `app/models/analysis.py`: SQLAlchemy 2.0 mapped models for `AnalysisRun` and `QualityIssue` with cascade foreign keys, dialect-adaptive JSONB/JSON, and composite indexes.
- `app/schemas/analysis.py`: Pydantic v2 schemas (`AnalysisRequest`, `AnalysisResponse`, `AnalysisRunRead`, `QualityIssueRead`, `QualityIssueListResponse`).
- `app/engine/modules/schema_analyzer.py`: Module 1 v1.0.0 deterministic schema profiling.
- `app/engine/modules/dtype_analyzer.py`: Module 2 v1.0.0 conceptual type classification and inconsistency detector.
- `app/engine/modules/missing_analyzer.py`: Module 3 v1.0.0 missingness and empty string profiler.
- `app/engine/modules/duplicate_analyzer.py`: Module 4 v1.0.0 exact row duplication detector with all-cluster counting semantics.
- `app/engine/modules/cardinality_analyzer.py`: Module 5 v1.0.0 constant, near-constant, high-cardinality, and identifier analyzer.
- `app/services/analysis_service.py`: Orchestration service managing asynchronous analysis dispatch, thread-isolated worker execution with `NullPool`, and persistence.
- `app/api/v1/analyses.py`: FastAPI endpoints for analysis dispatch (`POST .../analyze`), run status inspection (`GET /analyses/{run_id}`), and paginated defect retrieval (`GET /analyses/{run_id}/issues`).
- `alembic/versions/0002_create_analysis_tables.py`: Database migration creating `analysis_runs` and `quality_issues` tables.
- `tests/fixtures/`: 10 comprehensive fixtures (`clean.csv`, `missing_values.csv`, `duplicates.csv`, `mixed_types.csv`, `cardinality.csv`, `combined_dirty.csv`, `blank_strings.csv`, `constant_columns.csv`, `numeric_strings.csv`, `datetime_strings.csv`).
- `tests/test_schema_analyzer.py`: Unit tests for Module 1.
- `tests/test_dtype_analyzer.py`: Unit tests for Module 2.
- `tests/test_missing_analyzer.py`: Unit tests for Module 3.
- `tests/test_duplicate_analyzer.py`: Unit tests for Module 4.
- `tests/test_cardinality_analyzer.py`: Unit tests for Module 5.
- `tests/test_pipeline.py`: Pipeline sequence and issue aggregation tests.
- `tests/test_analysis_persistence.py`: Database model lifecycle and error state persistence tests.
- `tests/test_analysis_api.py`: FastAPI end-to-end integration tests.
- `tests/test_determinism.py`: Strict reproducibility test verifying identical findings across repeated runs.
- `docs/phase-2-analysis-engine.md`: Comprehensive engine architecture reference.

### 1.2 Files Modified
- `app/engine/base.py`: Extended `AnalysisContext` with `file_format: str = "parquet"`.
- `app/engine/pipeline.py`: Configured 5 Phase 2 analyzers in deterministic order with centralized summary metrics calculation.
- `app/models/__init__.py`: Registered and exported `AnalysisRun`, `QualityIssue`, and `AnalysisStatus`.
- `app/schemas/__init__.py`: Exported Phase 2 analysis request/response schemas.
- `app/services/__init__.py`: Exported `AnalysisService` and `get_job_runner`.
- `app/services/job_runner.py`: Added global singleton accessor `get_job_runner()`.
- `app/api/deps.py`: Added `get_analysis_service` and `AnalysisServiceDep`.
- `app/api/v1/router.py`: Mounted `analyses_router` into `/api/v1`.
- `app/core/exceptions.py`: Added `ValidationException` (HTTP 422).
- `README.md`: Documented Phase 2 completion and analysis capabilities.

---

## 2. Analysis Rules & Heuristics

### 2.1 Missing Values
- **Definition**: Null tokens (`NaN`, `None`, `pd.NA`, `pd.NaT`), plus empty/whitespace strings (`""`, `"   "`) when `treat_blank_strings_as_missing=True`. Categorical string tokens like `"NA"` or `"null"` are preserved as valid values unless configured via `custom_missing_strings`.
- **Thresholds**:
  | Range | Severity | Classification |
  | :--- | :--- | :--- |
  | $0\%$ | *None* | Clean |
  | $>0\%$ and $\le 5\%$ | `LOW` | Minor defect |
  | $>5\%$ and $\le 20\%$ | `MEDIUM` | Moderate defect |
  | $>20\%$ and $\le 40\%$ | `HIGH` | Severe defect |
  | $>40\%$ | `CRITICAL` | Critical defect (100% missing $\to$ CRITICAL) |

### 2.2 Duplicate Rows
- **Definition**: Exact duplicate rows across all features using `df.duplicated(keep=False)`. All rows belonging to duplicate clusters are accounted for.
- **Thresholds**:
  | Range | Severity | Classification |
  | :--- | :--- | :--- |
  | $0\%$ | *None* | Clean |
  | $>0\%$ and $\le 1\%$ | `LOW` | Minor duplicate rate |
  | $>1\%$ and $\le 5\%$ | `MEDIUM` | Moderate duplication |
  | $>5\%$ and $\le 20\%$ | `HIGH` | High duplication |
  | $>20\%$ | `CRITICAL` | Severe dataset duplication |

### 2.3 Data Types
- **Taxonomy**: `numeric`, `boolean`, `datetime`, `timedelta`, `categorical`, `string`, `object`, `other`.
- **Nested Objects**: `dict`, `list`, `set` detected $\to$ `HIGH` severity (`"Nested data structures detected"`).
- **Mixed Scalars**: Columns containing conflicting scalar types (e.g. `str + int`, `str + float`, `str + datetime`, `str + bool`) $\to$ `HIGH` severity (`"Mixed scalar data types detected"`). Standard missing values do not trigger mixed-type warnings.
- **Numeric-like Strings**: Non-null text columns where $\ge 95\%$ of values parse as numeric $\to$ `LOW` advisory (`"Numeric-like values stored as text"`).
- **Datetime-like Strings**: Non-null text columns where $\ge 95\%$ of values parse as datetime $\to$ `LOW` advisory (`"Datetime-like values stored as text"`).

### 2.4 Cardinality
- Uses non-null row count: $\text{unique\_ratio} = \frac{\text{unique\_count}}{\text{non\_null\_count}}$.
- **Constant**: $\text{unique\_count} == 1 \to$ `MEDIUM` severity (`"Constant column detected"`). Zero variance.
- **Near-Constant**: $\text{unique\_count} > 1$ and $\text{unique\_ratio} \le 0.01 \to$ `LOW` severity (`"Near-constant column detected"`).
- **High-Cardinality Categorical**: Categorical/string columns with $\text{unique\_count} \ge 50$ and $\text{unique\_ratio} < 0.95 \to$ `LOW` severity (`"High cardinality categorical column"`).
- **Identifier-Like**: $\text{unique\_ratio} \ge 0.95$ combined with identifier keywords (`id`, `uuid`, `email`, etc.) $\to$ `INFO` advisory (`"Identifier-like high-cardinality column"`).

---

## 3. Provenance Architecture
Every `QualityIssue` record stores:
- `module`: Detecting module name (e.g. `"missing_analyzer"`)
- `analyzer_version`: `"1.0.0"`
- `parameters_used`: JSON snapshot of effective thresholds applied
- `detected_at`: Timezone-aware UTC timestamp
- `analysis_run_id`: UUID foreign key to parent `AnalysisRun`
- `dataset_version_id`: UUID foreign key to target `DatasetVersion`

---

## 4. Verification Results

### 4.1 Pytest Suite
- **Command**: `python -m pytest -v`
- **Result**: `62 passed in 1.15s` (100% pass rate)
- **Coverage**: Includes unit tests for all 5 analyzers, schema validation, boundary thresholds, type inference, concurrency runner, file storage, persistence, FastAPI routes, and determinism.

### 4.2 PostgreSQL Database Migration
- **Command**: `alembic upgrade head`
- **Result**: Successfully executed `0001_initial -> 0002_create_analysis_tables` creating `analysis_runs` and `quality_issues` tables in PostgreSQL 18.
- **Command**: `alembic check`
- **Result**: `No new upgrade operations detected.` (100% schema-model alignment).

### 4.3 Database Persistence & End-to-End Execution
- **Environment**: PostgreSQL 18 database `dataset_doctor`.
- **Verification Workflow**:
  1. Created `Dataset` and `DatasetVersion` with normalized Parquet file.
  2. Created `AnalysisRun` with initial `PENDING` status.
  3. Executed deterministic analysis pipeline through `AnalysisService`.
  4. Verified `AnalysisRun` transitioned to `COMPLETED` with:
     - `engine_version`: `"1.0.0"`
     - `analyzer_versions`: All 5 modules mapped to `"1.0.0"`
     - `total_issues_count`: `6`
     - `summary_metrics`: Calculated deterministically
     - `completed_at`: Stamped with UTC datetime
  5. Verified 6 `QualityIssue` records persisted with JSON evidence, severity, foreign keys, and provenance.

### 4.4 Determinism Verification
- **Command**: `pytest tests/test_determinism.py`
- **Result**: Passed. Two independent executions against the same input produced bit-for-bit identical summary metrics, combined metrics, issue categories, severities, evidence payloads, and parameters.

---

## 5. Next Steps
Phase 2 is complete and verified. As mandated, Phase 3 (Advanced Statistical & ML Analysis: outliers, distributions, correlations, class imbalance, leakage detection, and ML readiness heuristic scoring) will be implemented separately upon review.
