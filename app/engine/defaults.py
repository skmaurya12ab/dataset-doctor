"""Centralized default thresholds and parameters for Phase 2 deterministic analyzers."""

from typing import Any, Dict

DEFAULT_SCHEMA_PARAMETERS: Dict[str, Any] = {
    "strip_whitespace_for_blank_check": True,
}

DEFAULT_DTYPE_PARAMETERS: Dict[str, Any] = {
    "numeric_parseable_threshold_pct": 95.0,
    "datetime_parseable_threshold_pct": 95.0,
}

DEFAULT_MISSING_PARAMETERS: Dict[str, Any] = {
    "treat_blank_strings_as_missing": True,
    "low_threshold_pct": 5.0,
    "medium_threshold_pct": 20.0,
    "high_threshold_pct": 40.0,
}

DEFAULT_DUPLICATE_PARAMETERS: Dict[str, Any] = {
    "low_threshold_pct": 1.0,
    "medium_threshold_pct": 5.0,
    "high_threshold_pct": 20.0,
}

DEFAULT_CARDINALITY_PARAMETERS: Dict[str, Any] = {
    "near_constant_ratio_threshold": 0.01,
    "high_cardinality_unique_count": 50,
    "identifier_unique_ratio_threshold": 0.95,
    "identifier_keywords": [
        "id",
        "user_id",
        "customer_id",
        "uuid",
        "guid",
        "email",
        "account_id",
        "client_id",
        "key",
        "code",
    ],
}

DEFAULT_OUTLIER_PARAMETERS: Dict[str, Any] = {
    "iqr_multiplier": 1.5,
    "mad_threshold": 3.5,
    "maximum_sample_size": 50_000,
    "random_seed": 42,
    "enable_isolation_forest": True,
    "isolation_forest_contamination": "auto",
    "info_threshold_pct": 1.0,
    "low_threshold_pct": 5.0,
    "medium_threshold_pct": 10.0,
    "high_threshold_pct": 20.0,
}

DEFAULT_DISTRIBUTION_PARAMETERS: Dict[str, Any] = {
    "skew_low_threshold": 1.0,
    "skew_medium_threshold": 2.0,
    "skew_high_threshold": 3.0,
    "normality_test_sample_size": 5_000,
    "normality_min_sample_size": 20,
    "random_seed": 42,
}

DEFAULT_CORRELATION_PARAMETERS: Dict[str, Any] = {
    "correlation_threshold": 0.90,
    "medium_threshold": 0.95,
    "high_threshold": 0.99,
    "max_features": 100,
    "sample_size": 50_000,
    "random_seed": 42,
    "compute_spearman": True,
}

DEFAULT_IMBALANCE_PARAMETERS: Dict[str, Any] = {
    "binary_low_threshold_pct": 60.0,
    "binary_medium_threshold_pct": 75.0,
    "binary_high_threshold_pct": 90.0,
    "binary_critical_threshold_pct": 95.0,
    "tiny_class_sample_threshold": 10,
}

DEFAULT_LEAKAGE_PARAMETERS: Dict[str, Any] = {
    "identity_threshold": 0.99,
    "correlation_threshold": 0.99,
    "categorical_purity_threshold": 0.99,
    "suspicious_keywords": [
        "target",
        "label",
        "outcome",
        "result",
        "final",
        "approved",
        "cancelled",
        "churned",
        "post_event",
        "future_",
        "after_",
    ],
    "random_seed": 42,
}

DEFAULT_SCORING_PARAMETERS: Dict[str, Any] = {
    "base_score": 100.0,
    "max_penalty_per_column": 25.0,
}

DEFAULT_ANALYSIS_PARAMETERS: Dict[str, Any] = {
    "schema_analyzer": DEFAULT_SCHEMA_PARAMETERS,
    "dtype_analyzer": DEFAULT_DTYPE_PARAMETERS,
    "missing_analyzer": DEFAULT_MISSING_PARAMETERS,
    "duplicate_analyzer": DEFAULT_DUPLICATE_PARAMETERS,
    "cardinality_analyzer": DEFAULT_CARDINALITY_PARAMETERS,
    "outlier_analyzer": DEFAULT_OUTLIER_PARAMETERS,
    "distribution_analyzer": DEFAULT_DISTRIBUTION_PARAMETERS,
    "correlation_analyzer": DEFAULT_CORRELATION_PARAMETERS,
    "imbalance_analyzer": DEFAULT_IMBALANCE_PARAMETERS,
    "leakage_analyzer": DEFAULT_LEAKAGE_PARAMETERS,
    "scoring": DEFAULT_SCORING_PARAMETERS,
}

