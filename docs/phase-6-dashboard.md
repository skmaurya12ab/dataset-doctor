# Phase 6: Dashboard, Visual Analytics & Remediation Workflow UI

## 1. Executive Summary

Phase 6 delivers a developer-grade visual analytics dashboard and remediation workflow for **Dataset Doctor**, bridging the deterministic profiling engines (Phases 0–3), grounded AI interpretation layers (Phase 4), and deterministic remediation execution with immutable version comparison (Phase 5).

The interface is built with **React**, **TypeScript**, and **Vite**, adopting a focused dark engineering aesthetic (graphite/carbon palettes, subtle borders, crisp typography, and analytical Plotly visualizations) that prioritizes data hierarchy and statistical transparency over superficial design tropes.

---

## 2. Core Architectural Principles

1. **AI Proposes, Human Approves, Python Executes**:
   - The frontend enforces explicit human review (`approval=true` checkbox and confirmation button) prior to triggering any dataset mutation.
   - The UI never executes transformation code autonomously upon page view or plan inspection.
   - All data manipulations execute deterministically in backend Python memory.
2. **Deterministic Source of Truth**:
   - The frontend never calculates or recalculates statistical metrics, null percentages, correlations, skewness, or heuristic scores.
   - All metrics, bounds, ratings, and penalty deductions are rendered directly from backend API responses.
3. **Raw Data Protection**:
   - Raw datasets are never streamed in bulk to the browser.
   - The API provides server-bounded previews (maximum 10 rows) and pre-aggregated plotting payloads to guarantee low latency and confidentiality.
4. **Strict Security Boundaries**:
   - OpenAI and database credentials remain backend-only. The frontend communicates exclusively with authenticated `/api/v1/*` endpoints.

---

## 3. UI Architecture & Page Structure

```text
frontend/
├── src/
│   ├── types/
│   │   ├── dataset.ts          # Dataset, DatasetVersion, Schema & Preview interfaces
│   │   ├── analysis.ts         # AnalysisRun, QualityIssue, Heuristic & Viz interfaces
│   │   ├── ai.ts               # TransformationSpec, RiskAssessment, AIReport interfaces
│   │   └── remediation.ts      # RemediationExecution, MetricDelta, VersionComparison
│   ├── services/
│   │   └── api.ts              # Centralized Axios client & async pollers
│   ├── components/
│   │   ├── Layout.tsx          # Persistent application shell
│   │   ├── Sidebar.tsx         # Primary navigation (Overview, Datasets, Analysis, etc.)
│   │   ├── Header.tsx          # Breadcrumbs and quick upload trigger
│   │   ├── MetricCard.tsx      # Statistical delta and KPI cards
│   │   ├── SeverityBadge.tsx   # CRITICAL, HIGH, MEDIUM, LOW, INFO badges
│   │   ├── ReadinessCard.tsx   # ML readiness score, ratings, and penalty breakdowns
│   │   ├── IssueTable.tsx      # Filterable & searchable deterministic findings table
│   │   ├── AIExplanationModal.tsx # Grounded single-finding explanation modal
│   │   ├── RemediationPlanView.tsx# Advisory transformation plan inspection
│   │   ├── ApprovalModal.tsx   # Explicit human approval checkbox & apply modal
│   │   ├── RemediationStatusBadge.tsx # Lifecycle state badges
│   │   ├── VersionTimeline.tsx # Immutable version lineage graph
│   │   ├── VersionComparisonView.tsx # Before/after comparative audit view
│   │   ├── UploadModal.tsx     # CSV, XLSX, JSON, Parquet upload dialog
│   │   └── charts/
│   │       ├── PlotlyChart.tsx # Dark developer theme Plotly wrapper
│   │       ├── MissingnessChart.tsx # Horizontal bar chart (column -> null %)
│   │       ├── DistributionChart.tsx# Histogram & box statistics
│   │       ├── CorrelationHeatmap.tsx # Pearson & Spearman heatmaps
│   │       ├── ClassDistributionChart.tsx # Class imbalance bar chart
│   │       └── CardinalityTable.tsx # Uniqueness ratio classification
│   └── pages/
│       ├── OverviewPage.tsx    # High-level telemetry, running jobs & recent actions
│       ├── DatasetsPage.tsx    # Datasets registry with search and sorting
│       ├── DatasetDetailPage.tsx # Quality summary, lineage timeline & run analysis
│       ├── VersionDetailPage.tsx # Immutable snapshot metadata, schema & bounded preview
│       ├── AnalysisPage.tsx    # 11-module findings hierarchy, charts & AI explanation
│       ├── RemediationPage.tsx # Advisory plan, approval modal & status poller
│       ├── ComparisonPage.tsx  # Version comparison (v1 -> v2 deltas & lifecycle)
│       └── SettingsPage.tsx    # Architectural principles and safety boundaries
```

---

## 4. Analytical Visualization Strategy

Plotly visualizations are configured with a unified dark developer theme (`paper_bgcolor: 'transparent'`, `plot_bgcolor: 'transparent'`, monospace fonts, muted slate grids):

1. **Missing Values**:
   - Horizontal bar chart sorting columns descending by null percentage.
   - Bars colored according to backend-assigned severity (`CRITICAL`, `HIGH`, `MEDIUM`, `LOW`).
2. **Distributions**:
   - Interactive column selector displaying backend-computed mean, median, standard deviation, IQR, skewness, and kurtosis alongside box plots.
3. **Correlation Heatmap**:
   - Toggle between Pearson (linear) and Spearman (rank) correlation matrices.
   - Highlights high-correlation feature pairs ($|r| > 0.85$).
4. **Class Imbalance**:
   - Categorical bar chart of class counts and percentages with explicit imbalance ratio indicators.
5. **Data Leakage Warnings**:
   - Highlights feature identity or extreme target relationships with mandatory disclaimer: *"Correlation and statistical signals indicate potential leakage risk; they do not prove leakage."*

---

## 5. Async Analysis & Remediation Polling

The frontend supports long-running background tasks via typed pollers in `services/api.ts`:
- **Analysis Poller**:
  - State machine: `REQUEST` $\rightarrow$ `PENDING` $\rightarrow$ `RUNNING` $\rightarrow$ `COMPLETED` / `FAILED`.
  - Configurable polling interval (default 1500ms) with timeout limit and terminal state detection.
- **Remediation Poller**:
  - State machine: `PENDING_APPROVAL` $\rightarrow$ `APPROVED` $\rightarrow$ `VALIDATING` $\rightarrow$ `RUNNING` $\rightarrow$ `COMPLETED` / `FAILED`.
  - Updates progress dynamically and displays instant link to the newly created `DatasetVersion` and before/after comparison view upon completion.

---

## 6. Version Comparison & Defect Lifecycle UX

The comparison page answers: *"Did remediation actually improve data quality?"*
- **Metric Cards**: Before, After, and Delta for Rows, Columns, Missing %, Duplicate Rows.
- **Readiness Score Shift**:
  - Before: `58 (POOR)` $\rightarrow$ After: `84 (GOOD)` $\rightarrow$ Delta: `+26`.
  - Mandatory disclaimer: *"The heuristic measures data quality/readiness signals, not actual model performance."*
- **Defect Lifecycle Transitions**:
  - `RESOLVED`: Defects fixed by remediation.
  - `CHANGED`: Severity altered or parameters modified.
  - `UNCHANGED`: Defects remaining untouched.
  - `NEW`: Any new defects introduced by transformations.

---

## 7. Limitations & Future Considerations

- WebGL/Canvas rendering in JSDOM unit tests requires mock wrappers (implemented in `src/test/setup.ts`).
- Large tabular schemas (>100 columns) are scrollable and horizontally paginated.
