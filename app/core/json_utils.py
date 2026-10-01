"""Reliable JSON-safe serialization utilities for NumPy, Pandas, and Python types."""

import math
from datetime import date, datetime
from typing import Any
import numpy as np
import pandas as pd


def to_json_safe(obj: Any) -> Any:
    """Recursively convert NumPy, Pandas, and Python objects to JSON-serializable primitives.
    
    Handles:
    - np.integer -> int
    - np.floating -> float (or None if NaN/Inf)
    - np.bool_ -> bool
    - pd.Timestamp, datetime, date -> ISO 8601 formatted string
    - NaN, NaT, None -> None
    - dict -> recursive dictionary with stringified keys
    - list, tuple, set, pd.Series, np.ndarray -> recursive list
    """
    if obj is None:
        return None

    # Handle pandas missing value tokens (NaT, pd.NA)
    if obj is pd.NA:
        return None

    # Float & NumPy floating
    if isinstance(obj, (float, np.floating)):
        if math.isnan(obj) or math.isinf(obj):
            return None
        return float(obj)

    # Boolean & NumPy boolean (MUST check before integer because bool is a subclass of int in Python)
    if isinstance(obj, (bool, np.bool_)):
        return bool(obj)

    # Integer & NumPy integer
    if isinstance(obj, (int, np.integer)):
        return int(obj)


    # Temporal objects
    if isinstance(obj, (pd.Timestamp, datetime, date)):
        if pd.isna(obj):
            return None
        return obj.isoformat()

    # Dictionaries
    if isinstance(obj, dict):
        return {str(k): to_json_safe(v) for k, v in obj.items()}

    # Sequences
    if isinstance(obj, (list, tuple, set, np.ndarray, pd.Series)):
        return [to_json_safe(item) for item in obj]

    # Catch-all for pandas isnull on custom scalar objects
    try:
        if pd.isna(obj):
            return None
    except Exception:
        pass

    return obj
