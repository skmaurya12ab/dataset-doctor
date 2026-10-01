# Phase 2: Core Deterministic Analysis Engine Documentation

## 1. Overview & Architectural Principles

Dataset Doctor's Phase 2 implements pure, reproducible, and deterministic data-quality and schema profiling in Python.

### Architectural Invariants
1. **Zero LLM Dependency in Profiling**: Every numerical metric, missingness rate, uniqueness ratio, and defect detection originates strictly from deterministic Python/NumPy/pandas logic. LLMs are completely excluded from Phase 2.
2. **Read-Only / Non-Mutating Execution**: Input datasets, uploaded files, and canonical Parquet replicas are strictly immutable. Analyzers never modify schemas, cast data types in place, or remove duplicate rows.
3. **Traceable Provenance**: Every `QualityIssue` record captures the detecting module, analyzer semantic version (`"1.0.0"`), effective parameters applied, and a timezone-aware UTC detection timestamp.
4. **Layer Separation**:
   ```text
   HTTP API Layer (FastAPI)
         ↓
   Orchestration Layer (AnalysisService)
         ↓
   Worker Pool (AnalysisJobRunner / ThreadPoolJobRunner)
         ↓
   Execution Pipeline (AnalysisPipeline)
         ↓
   Modular Deterministic Analyzers (BaseAnalyzer)
   ```
5. **Thread Safety & Database Isolation**: Worker execution threads operate using isolated sessions and connection pools (`NullPool`), avoiding event loop collisions with the FastAPI asynchronous request handler.

---

## 2. Core Abstractions & Contracts

### 2.1 `AnalysisContext`
```python
@dataclass
class AnalysisContext:
    dataset_version_id: str
    file_path: Optional[Path] = None
    df: Optional[pd.DataFrame] = None
    file_format: str = "parquet"
    target_column: Optional[str] = None
    problem_type: Optional[str] = None
    sample_size: int = 50_000
    random_seed: int = 42
    parameters: Dict[str, Any] = field(default_factory=dict)
    inferred_types: Dict[str, str] = field(default_factory=dict)
    shared_cache: Dict[str, Any] = field(default_factory=dict)
```
- Context serves as the single source of truth for an analysis execution pass.
- `shared_cache` allows downstream analyzers to share precalculated stats (e.g. `inferred_types`, `missing_counts`) without re-computation.

### 2.2 `BaseAnalyzer` & `ModuleResult`
```python
class BaseAnalyzer(ABC):
    @property
    @abstractmethod
    def name(self) -> str: ...

    @property
    @abstractmethod
    def version(self) -> str: ...

    @abstractmethod
    def analyze(self, ctx: AnalysisContext) -> ModuleResult: ...
```
Every analyzer yields a `ModuleResult`:
- `module_name`: Identifier string (e.g., `"missing_analyzer"`)
- `analyzer_version`: Semantic version string (`"1.0.0"`)
- `execution_time_ms`: Execution duration in milliseconds
- `metrics`: Dictionary of JSON-safe summary statistics
- `issues`: List of granular `QualityIssueData` objects

---

## 3. The Five Deterministic Analyzers

The analysis pipeline executes the five modules in strict sequential order:

```text
1. SchemaAnalyzer
      ↓
2. DataTypeAnalyzer
      ↓
3. MissingValueAnalyzer
      ↓
4. DuplicateAnalyzer
      ↓
5. CardinalityAnalyzer
```

### 3.1 Schema Analyzer (`schema_analyzer`, v1.0.0)
- **Purpose**: Inspect structural column headers and matrix shape without computing row-level statistical metrics.
- **Metrics**: `row_count`, `column_count`, `column_names`, `duplicate_column_names`, `blank_column_names`, `column_order`, `has_duplicate_column_names`, `has_blank_column_names`.
- **Findings**:
  - `Duplicate column names detected`: `category="SCHEMA"`, `severity=HIGH`. Evidence: `duplicate_columns`, `duplicate_count`.
  - `Blank column name detected`: `category="SCHEMA"`, `severity=MEDIUM`. Strips surrounding whitespace (`""` or `"   "`). Evidence: `blank_columns`.
- **False Positive Protection**: Unusual but valid unicode or symbol-containing names (`"user age"`, `"customer.address"`, `"₹income"`, `"नाम"`) are accepted as valid headers.

### 3.2 Data Type Analyzer (`dtype_analyzer`, v1.0.0)
- **Purpose**: Normalize conceptual types and detect mixed scalar types, nested objects, or miscast string columns.
- **Normalized Type Taxonomy**: `numeric`, `boolean`, `datetime`, `timedelta`, `categorical`, `string`, `object`, `other`. Populates `ctx.inferred_types`.
- **Findings**:
  - `Nested data structures detected`: `category="DTYPE"`, `severity=HIGH`. Flags structured Python objects (`dict`, `list`, `set`).
  - `Mixed scalar data types detected`: `category="DTYPE"`, `severity=HIGH`. Detects columns with conflicting non-null scalar types (`str + int`, `str + float`, `str + datetime`, `str + bool`). Standard missing values are excluded to prevent false positives.
  - `Numeric-like values stored as text`: `category="DTYPE"`, `severity=LOW` (advisory). Triggered when $\ge 95\%$ of non-null string values parse as valid floats/integers.
  - `Datetime-like values stored as text`: `category="DTYPE"`, `severity=LOW` (advisory). Triggered when $\ge 95\%$ of non-null string values match ISO/standard date patterns and parse via `pd.to_datetime`.

### 3.3 Missing Value Analyzer (`missing_analyzer`, v1.0.0)
- **Purpose**: Quantify column-level and dataset-level missingness rates.
- **Missingness Definition**: Standard missing tokens (`np.nan`, `None`, `pd.NA`, `pd.NaT`), plus blank/whitespace strings (`""`, `"   "`) when `treat_blank_strings_as_missing=True`. Arbitrary strings like `"NA"` or `"null"` are preserved as categorical values unless explicitly provided in `custom_missing_strings`.
- **Severity Thresholds**:
  | Missing Percentage | Severity | Action |
  | :--- | :--- | :--- |
  | $0\%$ | *No Issue* | Column clean |
  | $>0\%$ and $\le 5\%$ | `LOW` | Minimal missingness |
  | $>5\%$ and $\le 20\%$ | `MEDIUM` | Moderate missingness |
  | $>20\%$ and $\le 40\%$ | `HIGH` | Heavy missingness |
  | $>40\%$ | `CRITICAL` | Severe defect (100% missing $\to$ CRITICAL) |

### 3.4 Duplicate Analyzer (`duplicate_analyzer`, v1.0.0)
- **Purpose**: Detect exact identical rows across the entire feature space.
- **Duplicate Counting Semantics**: Evaluates `df.duplicated(keep=False)` so that **all** rows belonging to duplicate clusters are accounted for.
- **Severity Thresholds**:
  | Duplicate Percentage | Severity | Action |
  | :--- | :--- | :--- |
  | $0\%$ | *No Issue* | All rows distinct |
  | $>0\%$ and $\le 1\%$ | `LOW` | Minor duplicate rate |
  | $>1\%$ and $\le 5\%$ | `MEDIUM` | Moderate duplication |
  | $>5\%$ and $\le 20\%$ | `HIGH` | Significant duplication |
  | $>20\%$ | `CRITICAL` | Massive data duplication |

### 3.5 Cardinality Analyzer (`cardinality_analyzer`, v1.0.0)
- **Purpose**: Profile distinct value distributions per column to identify constant, low-variance, or identifier columns.
- **Formulation**: Uses non-null rows: $\text{unique\_ratio} = \frac{\text{unique\_count}}{\text{non\_null\_count}}$.
- **Findings**:
  - `Constant column detected`: `unique_count == 1`, `severity=MEDIUM`. Zero predictive variance.
  - `Near-constant column detected`: `unique_count > 1` and $\text{unique\_ratio} \le 0.01$ (1%), `severity=LOW`.
  - `High cardinality categorical column`: `unique_count >= 50` and $\text{unique\_ratio} < 0.95$ for categorical/string features, `severity=LOW`.
  - `Identifier-like high-cardinality column`: $\text{unique\_ratio} \ge 0.95$, `severity=INFO` (strictly advisory). Checks common identifier keywords (`id`, `uuid`, `email`, etc.). Advises review to avoid target leakage or index overfitting.

---

## 4. API Specifications

### 4.1 Trigger Analysis
- **Route**: `POST /api/v1/datasets/{dataset_id}/versions/{version_id}/analyze`
- **Status Code**: `202 Accepted`
- **Request Body**:
  ```json
  {
    "target_column": "churn",
    "problem_type": "classification",
    "parameters": {}
  }
  ```
- **Response**:
  ```json
  {
    "analysis_run_id": "936d5526-7f12-4c47-a827-023a1a1f0592",
    "status": "PENDING"
  }
  ```

### 4.2 Query Analysis Run Status
- **Route**: `GET /api/v1/analyses/{run_id}`
- **Response**:
  ```json
  {
    "id": "936d5526-7f12-4c47-a827-023a1a1f0592",
    "dataset_version_id": "fa948dbd-a773-4902-8610-093557e034da",
    "status": "COMPLETED",
    "target_column": "churn",
    "problem_type": "classification",
    "engine_version": "1.0.0",
    "analyzer_versions": {
      "schema_analyzer": "1.0.0",
      "dtype_analyzer": "1.0.0",
      "missing_analyzer": "1.0.0",
      "duplicate_analyzer": "1.0.0",
      "cardinality_analyzer": "1.0.0"
    },
    "ml_readiness_score": null,
    "heuristic_breakdown": null,
    "total_issues_count": 4,
    "critical_issues_count": 1,
    "execution_time_ms": 42,
    "summary_metrics": {
      "row_count": 1000,
      "column_count": 12,
      "missing_columns": 2,
      "total_missing_cells": 150,
      "overall_missing_percentage": 1.25,
      "columns_with_type_warnings": 1,
      "duplicate_row_count": 0,
      "duplicate_percentage": 0.0,
      "constant_columns": 1,
      "high_cardinality_columns": 0
    },
    "error_message": null,
    "created_at": "2026-10-01T10:00:00Z",
    "completed_at": "2026-10-01T10:00:01Z"
  }
  ```

### 4.3 Query Quality Issues
- **Route**: `GET /api/v1/analyses/{run_id}/issues`
- **Query Filters**: `severity`, `module`, `column`, `limit` (default 50, max 200), `offset` (default 0)
- **Response**:
  ```json
  {
    "total": 1,
    "limit": 50,
    "offset": 0,
    "items": [
      {
        "id": "c13ea427-4c75-4d7a-8b17-3bf9b106456a",
        "analysis_run_id": "936d5526-7f12-4c47-a827-023a1a1f0592",
        "dataset_version_id": "fa948dbd-a773-4902-8610-093557e034da",
        "module": "missing_analyzer",
        "analyzer_version": "1.0.0",
        "parameters_used": {
          "treat_blank_strings_as_missing": true,
          "low_threshold_pct": 5.0,
          "medium_threshold_pct": 20.0,
          "high_threshold_pct": 40.0
        },
        "category": "MISSING_VALUES",
        "severity": "CRITICAL",
        "column_name": "address",
        "title": "Missing values detected in 'address'",
        "description": "Column 'address' has 450 missing value(s) (45.0% of 1000 total rows).",
        "evidence": {
          "missing_count": 450,
          "total_count": 1000,
          "missing_percentage": 45.0,
          "definition": "null_values_and_blank_strings"
        },
        "remediation_hint": "Investigate missingness mechanism (MCAR, MAR, MNAR) before selecting an imputation strategy or row filtering.",
        "detected_at": "2026-10-01T10:00:00.512000Z"
      }
    ]
  }
  ```

---

## 5. Known Limitations
1. **Linear In-Memory Scanning**: In Phase 2, the five deterministic analyzers operate across the full canonical Parquet dataset. This is optimal for dataset sizes up to the project limit (100 MB), but datasets exceeding several gigabytes will require block-chunked processing in later stages.
2. **Phase 2 Scope Boundary**: Statistical outlier models, multivariate correlation matrices, target leakage detection, class imbalance heuristics, and OpenAI remediation plans belong to Phase 3 and Phase 4.
