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

DEFAULT_ANALYSIS_PARAMETERS: Dict[str, Any] = {
    "schema_analyzer": DEFAULT_SCHEMA_PARAMETERS,
    "dtype_analyzer": DEFAULT_DTYPE_PARAMETERS,
    "missing_analyzer": DEFAULT_MISSING_PARAMETERS,
    "duplicate_analyzer": DEFAULT_DUPLICATE_PARAMETERS,
    "cardinality_analyzer": DEFAULT_CARDINALITY_PARAMETERS,
}
