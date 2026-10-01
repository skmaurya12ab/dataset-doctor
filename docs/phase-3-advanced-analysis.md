# Phase 3 — Advanced Statistical & ML Analysis Specification

## 1. Core Principles & Philosophy

Phase 3 extends the **Dataset Doctor** deterministic engine beyond structural profiling into statistical validation and machine learning readiness.

### Core Tenets
1. **Deterministic First**: All statistics, percentiles, correlations, imbalance metrics, outlier counts, and penalty deductions are strictly calculated by Python numerical routines (`numpy`, `scipy`, `scikit-learn`, `pandas`). The LLM remains completely unused in Phase 3.
2. **Read-Only Non-Destructive Analysis**: Phase 3 never mutates, cleans, drops, imputes, or scales dataset records on disk or in memory.
3. **Avoid False Positives**: Every finding carries deterministic evidence, an explicit rule, explainable rationale, and defensible severity. Advisory signals default to `INFO` rather than falsely claiming `HIGH` or `CRITICAL`.
4. **Fundamental Analytical Distinctions**:
   - $\text{High Correlation} \neq \text{Automatic Leakage}$
   - $\text{Outlier} \neq \text{Bad Data}$
   - $\text{Non-Normal Distribution} \neq \text{Bad Data}$
   - $\text{Class Imbalance} \neq \text{Impossible ML Problem}$
   - $\text{High Readiness Heuristic} \neq \text{Guaranteed Model Performance}$

---

## 2. Module 6 — Outlier Analyzer (`app/engine/modules/outlier_analyzer.py`)

### 2.1 Supported Methodologies
- **Method A — Interquartile Range (IQR)**:
  $$Q_1 = \text{Percentile}(X, 25), \quad Q_3 = \text{Percentile}(X, 75)$$
  $$\text{IQR} = Q_3 - Q_1$$
  $$\text{Lower Bound} = Q_1 - 1.5 \times \text{IQR}, \quad \text{Upper Bound} = Q_3 + 1.5 \times \text{IQR}$$
  Observations outside $[\text{Lower Bound}, \text{Upper Bound}]$ are flagged.
  *Zero IQR Safeguard*: If $\text{IQR} = 0.0$ (e.g. constant or near-constant features), IQR outlier reporting is suppressed to avoid false alarms.
- **Method B — Median Absolute Deviation (MAD)**:
  $$\tilde{x} = \text{median}(X), \quad \text{MAD} = \text{median}(|X - \tilde{x}|)$$
  $$\text{Modified } Z\text{-Score} = \frac{0.6745 \times |x - \tilde{x}|}{\text{MAD}}$$
  Observations with modified $Z\text{-score} > 3.5$ are recorded as supporting MAD anomalies.
- **Method C — Multivariate Isolation Forest**:
  Uses `scikit-learn`'s `IsolationForest` across non-constant numeric features as an advisory multivariate anomaly detector.

### 2.2 Severity Policy
Severity is proportional to the percentage of non-null observations flagged by IQR:
- $0\%$: No issue
- $>0\% - 1\%$: `INFO`
- $>1\% - 5\%$: `LOW`
- $>5\% - 10\%$: `MEDIUM`
- $>10\% - 20\%$: `HIGH`
- $>20\%$: `CRITICAL`

### 2.3 Computational Safeguards
- Eligible columns must have $\ge 4$ non-null observations.
- Isolation Forest row count is capped at `maximum_sample_size = 50,000` with deterministic sampling (`random_seed = 42`).

---

## 3. Module 7 — Distribution Analyzer (`app/engine/modules/distribution_analyzer.py`)

### 3.1 Metrics Computed
For every eligible numeric column:
- `count`, `mean`, `median`, `std`, `min`, `max`, `q1`, `q3`
- `skewness` (Fisher-Pearson coefficient)
- `kurtosis` (Fisher excess kurtosis, normal distribution $= 0.0$)
- Normality test results (`dagostino_k_squared` test)

### 3.2 Skewness Severity Thresholds
- $|\text{skewness}| < 1.0$: No issue
- $1.0 \le |\text{skewness}| < 2.0$: `LOW` (moderately skewed)
- $2.0 \le |\text{skewness}| < 3.0$: `MEDIUM`
- $|\text{skewness}| \ge 3.0$: `HIGH` (strongly skewed)

### 3.3 Normality Tests & Limitations
SciPy's `stats.normaltest` (D'Agostino's $K^2$) is executed when sample size is between $20$ and $5,000$.
- $p < 0.05$ is **not** treated as broken data. Normal distribution is not required for decision trees, gradient boosting, or non-parametric algorithms.
- Normality findings are strictly advisory `INFO` issues.
- Features with $\text{std} = 0.0$ are suppressed to avoid duplicate findings already handled by cardinality analysis.

---

## 4. Module 8 — Correlation Analyzer (`app/engine/modules/correlation_analyzer.py`)

### 4.1 Methodology
- Evaluates pairwise Pearson correlation coefficient $r$ and Spearman rank correlation $r_s$ across non-constant numeric features.
- Constant columns ($\text{std} = 0$) are pruned prior to matrix calculation.
- Reports only upper-triangle pairs $(A \leftrightarrow B)$; suppresses self-correlations $(A \leftrightarrow A)$ and duplicate permutations $(B \leftrightarrow A)$.

### 4.2 Severity Thresholds
- $0.90 \le |r| < 0.95$: `LOW`
- $0.95 \le |r| < 0.99$: `MEDIUM`
- $|r| \ge 0.99$: `HIGH`

### 4.3 Target Correlations
If a continuous numerical target column is provided, feature-to-target correlations are computed and saved in `target_correlations`. High target correlation is **not** treated as leakage on its own, as predictive features naturally correlate with targets.

### 4.4 Complexity & Wide-Dataset Safeguards
- Features capped at `max_features = 100` (`MAX_CORRELATION_FEATURES`). When exceeded, `analysis_limited = True` is reported with an advisory `INFO` issue.
- Observations capped at `max_sample_size = 50,000` with deterministic sampling (`random_seed = 42`).

---

## 5. Module 9 — Class Imbalance Analyzer (`app/engine/modules/imbalance_analyzer.py`)

### 5.1 Preconditions & Scope
- Operates only when an explicit `target_column` is provided. If absent, reports `analysis_skipped = True` (`reason = "target_column_not_provided"`).
- Skips continuous numerical targets unless explicitly declared as `classification`.

### 5.2 Metrics
- `class_count`, `class_distribution`, `class_percentages`
- `majority_class`, `minority_class`, `majority_percentage`, `minority_percentage`
- `imbalance_ratio = majority_count / minority_count`

### 5.3 Severity Policy
For binary classification targets:
- Majority $\le 60\%$: No issue
- $>60\% - 75\%$: `LOW`
- $>75\% - 90\%$: `MEDIUM`
- $>90\% - 95\%$: `HIGH`
- $>95\%$: `CRITICAL`

For multiclass targets:
- Evaluates minority class starvation ($< 2\%$ for `HIGH`, $< 5\%$ for `MEDIUM`) and majority concentration ($> 80\%$ for `HIGH`, $> 70\%$ for `MEDIUM`).

### 5.4 Tiny Classes
Any class with sample count $< 10$ produces an advisory `LOW` finding with itemized counts to prevent failed cross-validation folds.

---

## 6. Module 10 — Data Leakage Analyzer (`app/engine/modules/leakage_analyzer.py`)

### 6.1 Preconditions
Requires explicit `target_column` and $\ge 10$ rows. If missing, reports `analysis_skipped = True`.

### 6.2 Detection Signals
1. **Signal A — Target Identity / Near Identity**:
   Calculates exact value match ratio between feature and target. $\text{Match Ratio} \ge 0.99$ generates a `HIGH` potential leakage issue ("Potential target-derived feature").
2. **Signal B — Extreme Numerical Correlation**:
   For continuous targets and features, $|r_{\text{pearson}}| \ge 0.99$ generates a `HIGH` potential leakage issue. Correlations $< 0.99$ are not flagged.
3. **Signal C — Categorical Conditional Purity**:
   For discrete/classification targets, evaluates conditional cross-tabulation purity:
   $$\text{Purity} = \frac{\sum_{g \in \text{Categories}} \max_c N_{g, c}}{N}$$
   $\text{Purity} \ge 0.99$ indicates the feature deterministically resolves the target label.
4. **Signal D — Suspicious Naming**:
   Identifies outcome-related tokens (`outcome`, `cancelled`, `post_event`, `future_`). Suspicious names alone **MUST NEVER** produce `HIGH` or `CRITICAL` findings; they generate strictly `INFO` findings.

---

## 7. Module 11 — ML Readiness Heuristic Scorer (`app/engine/scoring.py`)

### 7.1 Formula & Weights
$$\text{Score} = \max\left(0.0, 100.0 - \sum \text{Effective Penalties}\right)$$
- `CRITICAL`: 25.0 points
- `HIGH`: 10.0 points
- `MEDIUM`: 4.0 points
- `LOW`: 1.0 point
- `INFO`: 0.0 points

### 7.2 Penalty Deduplication Safeguard
To prevent pathological score destruction when multiple modules flag the same underlying problem on a single column (e.g., cardinality, outlier, and distribution all flagging column `salary`), the maximum cumulative penalty applied to any single column is capped at **25.0 points**.

### 7.3 Rating Labels
- $90.0 - 100.0$: **Production-oriented readiness**
- $75.0 - 89.9$: **Minor remediation**
- $50.0 - 74.9$: **Significant preprocessing**
- $0.0 - 49.9$: **High risk / substantial remediation**

### 7.4 Transparency & Provenance
Every run provides a complete itemized penalty breakdown, detailing the origin module, severity, column, title, and exact deduction.
