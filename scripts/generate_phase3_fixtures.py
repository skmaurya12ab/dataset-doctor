"""Script to deterministically generate Phase 3 test fixtures."""

from pathlib import Path
import numpy as np
import pandas as pd

FIXTURES_DIR = Path("tests/fixtures")
FIXTURES_DIR.mkdir(parents=True, exist_ok=True)

# 1. Outlier fixtures
# normal_distribution.csv
rng = np.random.RandomState(42)
vals_norm = rng.normal(50.0, 4.0, 100)
# Clip to strictly avoid any natural outliers beyond 1.5 * IQR
q1, q3 = np.percentile(vals_norm, [25, 75])
iqr = q3 - q1
vals_norm = np.clip(vals_norm, q1 - 1.2 * iqr, q3 + 1.2 * iqr)
df_norm = pd.DataFrame({"id": range(1, 101), "value": vals_norm.round(2)})
df_norm.to_csv(FIXTURES_DIR / "normal_distribution.csv", index=False)

# single_outlier.csv: 20 rows, 1 outlier at index 19
# Baseline 19 items between 10.0 and 12.0, 1 item at 500.0 (5% -> LOW)
vals_single = [10.0, 11.0, 10.5, 11.2, 10.8, 11.5, 10.2, 11.1, 10.9, 11.3,
               10.4, 11.6, 10.7, 11.0, 10.6, 11.4, 10.3, 11.2, 10.5, 500.0]
df_single = pd.DataFrame({"id": range(1, 21), "val": vals_single})
df_single.to_csv(FIXTURES_DIR / "single_outlier.csv", index=False)

# many_outliers.csv: 30 rows, 7 extreme values (> 20% -> CRITICAL)
vals_many = [
    10.0, 10.2, 10.5, 10.8, 11.0, 11.2, 11.5, 11.8, 12.0, 12.2, 12.5, 12.8,
    13.0, 13.2, 13.5, 13.8, 14.0, 14.2, 14.5, 14.8, 15.0, 15.2, 15.5,
] + [100.0, 105.0, 110.0, 115.0, 120.0, 125.0, 130.0]
df_many = pd.DataFrame({"id": range(1, 31), "val": vals_many})
df_many.to_csv(FIXTURES_DIR / "many_outliers.csv", index=False)

# zero_iqr.csv: 20 rows where Q1 == Q3 (IQR == 0)
vals_zero_iqr = [5.0] * 18 + [10.0, 12.0]
df_zero_iqr = pd.DataFrame({"id": range(1, 21), "val": vals_zero_iqr})
df_zero_iqr.to_csv(FIXTURES_DIR / "zero_iqr.csv", index=False)

# 2. Distribution fixtures
# symmetric.csv: 60 rows symmetrically distributed around 50
sym_vals = []
for i in range(30):
    delta = i * 0.5
    sym_vals.extend([50.0 - delta, 50.0 + delta])
df_sym = pd.DataFrame({"id": range(1, 61), "val": sym_vals})
df_sym.to_csv(FIXTURES_DIR / "symmetric.csv", index=False)

# moderately_skewed.csv: skewness between 1.0 and 2.0
# Exponential with scale 2.0
exp_vals = rng.exponential(scale=2.0, size=100) + 10.0
df_mod_skew = pd.DataFrame({"id": range(1, 101), "val": exp_vals.round(3)})
df_mod_skew.to_csv(FIXTURES_DIR / "moderately_skewed.csv", index=False)

# strongly_skewed.csv: skewness >= 3.0
# Lognormal with high sigma
lognorm_vals = np.exp(rng.normal(0, 1.6, 100))
df_str_skew = pd.DataFrame({"id": range(1, 101), "val": lognorm_vals.round(3)})
df_str_skew.to_csv(FIXTURES_DIR / "strongly_skewed.csv", index=False)

# constant.csv: 30 rows with identical values
df_const = pd.DataFrame({"id": range(1, 31), "val": [42.0] * 30})
df_const.to_csv(FIXTURES_DIR / "constant.csv", index=False)

# small_sample.csv: 5 rows (below D'Agostino normality test threshold of 8/20)
df_small = pd.DataFrame({"id": range(1, 6), "val": [1.0, 2.0, 3.0, 4.0, 5.0]})
df_small.to_csv(FIXTURES_DIR / "small_sample.csv", index=False)

# 3. Correlation fixtures
# highly_correlated.csv: r ~ 0.96 (between 0.95 and 0.99 -> MEDIUM)
x_corr = np.linspace(1, 50, 50)
y_corr = x_corr * 1.5 + rng.normal(0, 4.0, 50)
df_high_corr = pd.DataFrame({"id": range(1, 51), "feat_a": x_corr, "feat_b": y_corr.round(2)})
df_high_corr.to_csv(FIXTURES_DIR / "highly_correlated.csv", index=False)

# perfectly_correlated.csv: r = 1.0 (>= 0.99 -> HIGH)
df_perf_corr = pd.DataFrame({
    "id": range(1, 51),
    "feat_a": x_corr,
    "feat_b": (x_corr * 3.0 + 7.0).round(2),
})
df_perf_corr.to_csv(FIXTURES_DIR / "perfectly_correlated.csv", index=False)

# uncorrelated.csv: r ~ 0.0
x_uncorr = rng.normal(10, 2, 50)
y_uncorr = rng.normal(50, 5, 50)
df_uncorr = pd.DataFrame({"id": range(1, 51), "feat_a": x_uncorr.round(2), "feat_b": y_uncorr.round(2)})
df_uncorr.to_csv(FIXTURES_DIR / "uncorrelated.csv", index=False)

# wide_dataset.csv: 25 features to test MAX_CORRELATION_FEATURES safeguard
wide_data = {"id": range(1, 21)}
for i in range(25):
    wide_data[f"feat_{i}"] = rng.normal(10 + i, 2, 20).round(2)
df_wide = pd.DataFrame(wide_data)
df_wide.to_csv(FIXTURES_DIR / "wide_dataset.csv", index=False)

# 4. Imbalance fixtures
# balanced_binary.csv: 50% / 50%
df_bal = pd.DataFrame({
    "id": range(1, 101),
    "target": [0] * 50 + [1] * 50,
})
df_bal.to_csv(FIXTURES_DIR / "balanced_binary.csv", index=False)

# mild_imbalance.csv: 70% / 30% (>60-75% -> LOW)
df_mild = pd.DataFrame({
    "id": range(1, 101),
    "target": [0] * 70 + [1] * 30,
})
df_mild.to_csv(FIXTURES_DIR / "mild_imbalance.csv", index=False)

# severe_imbalance.csv: 85% / 15% (>75-90% -> MEDIUM)
df_sev = pd.DataFrame({
    "id": range(1, 101),
    "target": [0] * 85 + [1] * 15,
})
df_sev.to_csv(FIXTURES_DIR / "severe_imbalance.csv", index=False)

# extreme_imbalance.csv: 97% / 3% (>95% -> CRITICAL)
df_ext = pd.DataFrame({
    "id": range(1, 101),
    "target": [0] * 97 + [1] * 3,
})
df_ext.to_csv(FIXTURES_DIR / "extreme_imbalance.csv", index=False)

# multiclass.csv: 3 classes: A: 70%, B: 20%, C: 10%
df_multi = pd.DataFrame({
    "id": range(1, 101),
    "target": ["A"] * 70 + ["B"] * 20 + ["C"] * 10,
})
df_multi.to_csv(FIXTURES_DIR / "multiclass.csv", index=False)

# tiny_class.csv: class 1 has 4 samples (< 10 -> warning)
df_tiny = pd.DataFrame({
    "id": range(1, 101),
    "target": [0] * 96 + [1] * 4,
})
df_tiny.to_csv(FIXTURES_DIR / "tiny_class.csv", index=False)

# 5. Leakage fixtures
# target_copy.csv: feature matches target exactly (match_ratio = 1.0)
targets = [0, 1] * 25
df_tgt_copy = pd.DataFrame({
    "id": range(1, 51),
    "target": targets,
    "target_clone": targets,
})
df_tgt_copy.to_csv(FIXTURES_DIR / "target_copy.csv", index=False)

# near_target_copy.csv: 100 rows, 99 match, 1 differs (match_ratio = 0.99 >= 0.99)
t_100 = ([0, 1] * 50)
f_100 = list(t_100)
f_100[0] = 1 - f_100[0]  # flip 1 element
df_near_copy = pd.DataFrame({
    "id": range(1, 101),
    "target": t_100,
    "near_target": f_100,
})
df_near_copy.to_csv(FIXTURES_DIR / "near_target_copy.csv", index=False)

# high_correlation_nonleaky.csv: correlation r ~ 0.85 (predictive, not leakage >= 0.99)
x_base = np.linspace(10, 100, 100)
y_pred = x_base + rng.normal(0, 15.0, 100)
df_nonleaky = pd.DataFrame({
    "id": range(1, 101),
    "target": x_base.round(2),
    "feature_pred": y_pred.round(2),
})
df_nonleaky.to_csv(FIXTURES_DIR / "high_correlation_nonleaky.csv", index=False)

# categorical_perfect_mapping.csv: conditional purity = 1.0
cat_targets = [0] * 30 + [1] * 20
cat_features = ["status_denied"] * 30 + ["status_granted"] * 20
df_cat_map = pd.DataFrame({
    "id": range(1, 51),
    "target": cat_targets,
    "status": cat_features,
})
df_cat_map.to_csv(FIXTURES_DIR / "categorical_perfect_mapping.csv", index=False)

# suspicious_name_only.csv: name contains 'outcome_cancelled' but values are random noise
noise_feat = rng.normal(100, 15, 50)
df_susp = pd.DataFrame({
    "id": range(1, 51),
    "target": [0, 1] * 25,
    "outcome_cancelled_flag": noise_feat.round(2),
})
df_susp.to_csv(FIXTURES_DIR / "suspicious_name_only.csv", index=False)

print("All Phase 3 test fixtures successfully generated in tests/fixtures/")
