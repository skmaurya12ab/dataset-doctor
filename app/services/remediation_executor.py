"""Deterministic Python transformation executor for approved remediation plans.

Implements strict isolation and deterministic transformation execution:
- Only allowlisted operations: DROP_COLUMN, REMOVE_DUPLICATES, IMPUTE, CAST_TYPE, CLIP_OUTLIERS.
- Zero execution of arbitrary Python, shell commands, SQL, dynamic expressions, or dynamic imports.
- Rejects modification or dropping of modeling target columns by default.
- Strict pre-mutation plan validation ensuring conflicts and invalid schemas are rejected upfront.
- Deterministic execution sequence: REMOVE_DUPLICATES -> CAST_TYPE -> IMPUTE -> CLIP_OUTLIERS -> DROP_COLUMN.
- In-memory DataFrame copy isolation; source data is never modified.
- Granular transformation provenance tracking with before/after delta metrics.
"""

from datetime import datetime, timezone
import io
from typing import Any, Dict, List, Optional, Set, Tuple
import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from app.core.exceptions import InvalidTransformationException, ValidationException
from app.core.logging import get_logger
from app.schemas.ai import (
    ALLOWED_ACTIONS_SET,
    DISALLOWED_ACTIONS_SET,
    VALID_CAST_TYPES,
    VALID_IMPUTE_STRATEGIES,
    TransformationSpec,
)

logger = get_logger(__name__)

EXECUTOR_VERSION = "1.0.0"

# Explicit deterministic execution hierarchy
EXECUTION_ORDER_WEIGHTS: Dict[str, int] = {
    "REMOVE_DUPLICATES": 1,
    "CAST_TYPE": 2,
    "IMPUTE": 3,
    "CLIP_OUTLIERS": 4,
    "DROP_COLUMN": 5,
}


def compute_snapshot_metrics(df: pd.DataFrame) -> Dict[str, Any]:
    """Calculate deterministic summary metrics snapshot for a DataFrame."""
    total_rows = int(len(df))
    total_cols = int(len(df.columns))
    total_cells = total_rows * total_cols
    missing_cells = int(df.isna().sum().sum())
    missing_pct = round((missing_cells / total_cells * 100), 4) if total_cells > 0 else 0.0
    duplicate_count = int(df.duplicated().sum()) if total_rows > 0 else 0

    col_dtypes = {str(c): str(df[c].dtype) for c in df.columns}
    col_cardinalities = {str(c): int(df[c].nunique(dropna=False)) for c in df.columns}
    col_missing = {str(c): int(df[c].isna().sum()) for c in df.columns}

    return {
        "row_count": total_rows,
        "column_count": total_cols,
        "total_cells": total_cells,
        "missing_cells": missing_cells,
        "missing_percentage": missing_pct,
        "duplicate_rows": duplicate_count,
        "dtypes": col_dtypes,
        "cardinality": col_cardinalities,
        "missing_by_column": col_missing,
    }


class RemediationExecutor:
    """Safe, deterministic execution engine for approved tabular transformations."""

    def __init__(self, version: str = EXECUTOR_VERSION):
        self.version = version

    def validate_plan(
        self,
        df: pd.DataFrame,
        plan: List[TransformationSpec],
        target_column: Optional[str] = None,
    ) -> None:
        """Validate an entire remediation plan against current DataFrame schema prior to execution.
        
        Rejects the entire plan if any operation is invalid, conflicts with another operation,
        or violates target protection constraints.
        """
        if not plan:
            raise ValidationException("Remediation transformation plan cannot be empty.")

        existing_cols: Set[str] = set(df.columns)
        dropped_cols: Set[str] = set()
        imputed_cols: Set[str] = set()
        cast_cols: Set[str] = set()
        clipped_cols: Set[str] = set()

        for idx, spec in enumerate(plan):
            action = spec.action

            # 1. Reject disallowed or unlisted actions
            if action in DISALLOWED_ACTIONS_SET or action not in ALLOWED_ACTIONS_SET:
                raise InvalidTransformationException(
                    f"Transformation action '{action}' is strictly prohibited. Only allowlisted actions are permitted."
                )

            # 2. Extract referenced columns
            target_cols: List[str] = []
            if action == "DROP_COLUMN":
                if spec.columns:
                    target_cols = list(spec.columns)
                elif spec.column:
                    target_cols = [spec.column]
                elif "columns" in spec.parameters:
                    target_cols = list(spec.parameters["columns"])
            elif action == "REMOVE_DUPLICATES":
                subset = spec.parameters.get("subset")
                if subset:
                    target_cols = list(subset)
            else:
                col = spec.column or spec.parameters.get("column")
                if col:
                    target_cols = [col]

            # 3. Target column protection
            if target_column:
                if action == "DROP_COLUMN" and target_column in target_cols:
                    raise InvalidTransformationException(
                        f"Dropping the modeling target '{target_column}' is prohibited."
                    )
                if action in ("CAST_TYPE", "IMPUTE", "CLIP_OUTLIERS") and target_column in target_cols:
                    raise InvalidTransformationException(
                        f"Direct modification of target column '{target_column}' is prohibited by policy."
                    )

            # 4. Column existence verification
            for c in target_cols:
                if c not in existing_cols:
                    raise InvalidTransformationException(
                        f"Transformation #{idx+1} ({action}) references non-existent column '{c}'."
                    )

            # 5. Conflict tracking
            if action == "DROP_COLUMN":
                for c in target_cols:
                    if c in dropped_cols:
                        raise InvalidTransformationException(f"Conflicting transformation: column '{c}' is dropped multiple times.")
                    dropped_cols.add(c)
            elif action == "IMPUTE":
                for c in target_cols:
                    if c in imputed_cols:
                        raise InvalidTransformationException(f"Conflicting transformation: column '{c}' has multiple IMPUTE operations.")
                    imputed_cols.add(c)
            elif action == "CAST_TYPE":
                for c in target_cols:
                    if c in cast_cols:
                        raise InvalidTransformationException(f"Conflicting transformation: column '{c}' has multiple CAST_TYPE operations.")
                    cast_cols.add(c)
            elif action == "CLIP_OUTLIERS":
                for c in target_cols:
                    if c in clipped_cols:
                        raise InvalidTransformationException(f"Conflicting transformation: column '{c}' has multiple CLIP_OUTLIERS operations.")
                    clipped_cols.add(c)

            # 6. Action-specific validation
            self._validate_action_parameters(df, spec)

        # 7. Check for drop-then-modify or modify-then-drop cross-conflicts
        overlap_with_dropped = dropped_cols.intersection(imputed_cols | cast_cols | clipped_cols)
        if overlap_with_dropped:
            col_conflict = sorted(list(overlap_with_dropped))[0]
            raise InvalidTransformationException(
                f"Conflicting transformation: column '{col_conflict}' cannot be dropped and simultaneously transformed."
            )

        # 8. Check that not all columns are dropped
        if len(dropped_cols) >= len(existing_cols):
            raise InvalidTransformationException(
                "Cannot drop all columns; dataset must retain at least one column."
            )

    def _validate_action_parameters(self, df: pd.DataFrame, spec: TransformationSpec) -> None:
        """Validate parameters and data-type compatibility for a single action."""
        action = spec.action

        if action == "IMPUTE":
            col = spec.column or spec.parameters.get("column")
            strategy = spec.parameters.get("strategy")
            if strategy not in VALID_IMPUTE_STRATEGIES:
                raise InvalidTransformationException(
                    f"IMPUTE strategy '{strategy}' is invalid. Allowed strategies: {sorted(VALID_IMPUTE_STRATEGIES)}"
                )
            if strategy in ("mean", "median"):
                if not pd.api.types.is_numeric_dtype(df[col]):
                    raise InvalidTransformationException(
                        f"IMPUTE strategy '{strategy}' is only valid for numeric columns. Column '{col}' is {df[col].dtype}."
                    )
            elif strategy == "constant":
                if "fill_value" not in spec.parameters:
                    raise InvalidTransformationException("IMPUTE with 'constant' strategy requires 'fill_value' parameter.")

        elif action == "CAST_TYPE":
            col = spec.column or spec.parameters.get("column")
            target_type = spec.parameters.get("target_type")
            if target_type not in VALID_CAST_TYPES:
                raise InvalidTransformationException(
                    f"CAST_TYPE target '{target_type}' is invalid. Allowed types: {sorted(VALID_CAST_TYPES)}"
                )

        elif action == "CLIP_OUTLIERS":
            col = spec.column or spec.parameters.get("column")
            if not pd.api.types.is_numeric_dtype(df[col]):
                raise InvalidTransformationException(
                    f"CLIP_OUTLIERS is only valid for numeric columns. Column '{col}' is {df[col].dtype}."
                )
            lower = spec.parameters.get("lower_quantile", 0.01)
            upper = spec.parameters.get("upper_quantile", 0.99)
            if not isinstance(lower, (int, float)) or not isinstance(upper, (int, float)):
                raise InvalidTransformationException("CLIP_OUTLIERS quantiles must be numeric.")
            if not (0.0 <= lower <= 0.5):
                raise InvalidTransformationException(f"lower_quantile ({lower}) must be between 0.0 and 0.5.")
            if not (0.5 <= upper <= 1.0):
                raise InvalidTransformationException(f"upper_quantile ({upper}) must be between 0.5 and 1.0.")
            if lower >= upper:
                raise InvalidTransformationException(f"lower_quantile ({lower}) must be strictly less than upper_quantile ({upper}).")

        elif action == "REMOVE_DUPLICATES":
            subset = spec.parameters.get("subset")
            if subset is not None:
                if not isinstance(subset, list) or not all(isinstance(c, str) for c in subset):
                    raise InvalidTransformationException("REMOVE_DUPLICATES 'subset' must be a list of column names.")
                for c in subset:
                    if c not in df.columns:
                        raise InvalidTransformationException(f"REMOVE_DUPLICATES subset column '{c}' does not exist.")
            keep = spec.parameters.get("keep")
            if keep is not None and keep not in ("first", "last", False):
                raise InvalidTransformationException("REMOVE_DUPLICATES 'keep' parameter must be 'first', 'last', or False.")

    def sort_plan_deterministically(self, plan: List[TransformationSpec]) -> List[TransformationSpec]:
        """Order transformations in the canonical deterministic sequence:
        1. REMOVE_DUPLICATES
        2. CAST_TYPE
        3. IMPUTE
        4. CLIP_OUTLIERS
        5. DROP_COLUMN
        """
        def sort_key(item: Tuple[int, TransformationSpec]) -> Tuple[int, str, int]:
            original_idx, s = item
            weight = EXECUTION_ORDER_WEIGHTS.get(s.action, 99)
            col_key = s.column or (s.columns[0] if s.columns else "")
            return (weight, col_key, original_idx)

        indexed = list(enumerate(plan))
        sorted_indexed = sorted(indexed, key=sort_key)
        return [s for _, s in sorted_indexed]

    def execute_plan(
        self,
        df: pd.DataFrame,
        plan: List[TransformationSpec],
        target_column: Optional[str] = None,
    ) -> Tuple[pd.DataFrame, List[Dict[str, Any]]]:
        """Validate entire plan and deterministically execute all transformations on a copy of DataFrame.
        
        Returns:
            Tuple of (remediated_dataframe, list_of_transformation_provenance_records)
        """
        # 1. Strict upfront plan validation
        self.validate_plan(df, plan, target_column=target_column)

        # 2. Work strictly on a deep copy to preserve source immutability
        remediated_df = df.copy(deep=True)

        # 3. Deterministically order transformations
        ordered_plan = self.sort_plan_deterministically(plan)

        provenance_records: List[Dict[str, Any]] = []

        # 4. Apply each transformation deterministically
        for order_idx, spec in enumerate(ordered_plan, start=1):
            remediated_df, prov_item = self.apply_spec(
                remediated_df,
                spec,
                applied_order=order_idx,
                target_column=target_column,
            )
            provenance_records.append(prov_item)

        # 5. Output data validation
        self.validate_output_dataframe(remediated_df)

        return remediated_df, provenance_records

    def apply_spec(
        self,
        df: pd.DataFrame,
        spec: TransformationSpec,
        applied_order: int = 1,
        target_column: Optional[str] = None,
    ) -> Tuple[pd.DataFrame, Dict[str, Any]]:
        """Apply a single validated transformation to the DataFrame and return updated DataFrame and provenance."""
        action = spec.action
        now_iso = datetime.now(timezone.utc)

        rows_before = len(df)
        cols_before = len(df.columns)
        rows_changed = 0
        cols_changed = 0

        before_metrics: Dict[str, Any] = {}
        after_metrics: Dict[str, Any] = {}

        if action == "REMOVE_DUPLICATES":
            subset = spec.parameters.get("subset")
            keep = spec.parameters.get("keep", "first")
            before_metrics = {"rows": rows_before, "duplicates": int(df.duplicated(subset=subset).sum())}

            df = df.drop_duplicates(subset=subset, keep=keep)
            rows_after = len(df)
            rows_changed = rows_before - rows_after
            if rows_after == 0:
                raise InvalidTransformationException("REMOVE_DUPLICATES resulted in zero rows.")
            after_metrics = {"rows": rows_after, "rows_removed": rows_changed}

        elif action == "CAST_TYPE":
            col = spec.column or spec.parameters.get("column")
            target_type = spec.parameters.get("target_type")
            source_dtype = str(df[col].dtype)
            before_metrics = {"source_dtype": source_dtype}

            try:
                if target_type == "int64":
                    if df[col].isna().any():
                        # Nullable integer conversion
                        df[col] = pd.to_numeric(df[col], errors="raise").astype("Int64")
                    else:
                        df[col] = pd.to_numeric(df[col], errors="raise").astype("int64")
                elif target_type == "float64":
                    df[col] = pd.to_numeric(df[col], errors="raise").astype("float64")
                elif target_type == "string":
                    df[col] = df[col].astype("string")
                elif target_type == "boolean":
                    df[col] = df[col].astype("boolean")
                elif target_type == "datetime64[ns]":
                    df[col] = pd.to_datetime(df[col], errors="raise")
            except Exception as exc:
                raise InvalidTransformationException(
                    f"CAST_TYPE failed for column '{col}' from '{source_dtype}' to '{target_type}': {exc}"
                )

            after_dtype = str(df[col].dtype)
            after_metrics = {"target_dtype": after_dtype, "conversion_success": True}
            rows_changed = rows_before  # type cast affects all rows in column

        elif action == "IMPUTE":
            col = spec.column or spec.parameters.get("column")
            strategy = spec.parameters.get("strategy")
            missing_before = int(df[col].isna().sum())
            before_metrics = {"missing_before": missing_before, "strategy": strategy}

            if missing_before > 0:
                if strategy == "mean":
                    fill_val = float(df[col].mean())
                elif strategy == "median":
                    fill_val = float(df[col].median())
                elif strategy == "mode":
                    mode_series = df[col].dropna().mode()
                    if len(mode_series) == 0:
                        raise InvalidTransformationException(f"Cannot impute mode for '{col}': all values are null.")
                    # Deterministic mode tie-breaking: sort values and take the first
                    fill_val = sorted(mode_series.tolist())[0]
                elif strategy == "constant":
                    fill_val = spec.parameters.get("fill_value")
                else:
                    raise InvalidTransformationException(f"Unknown impute strategy '{strategy}'")

                df[col] = df[col].fillna(fill_val)
                missing_after = int(df[col].isna().sum())
                rows_changed = missing_before - missing_after
                after_metrics = {"missing_after": missing_after, "imputed_value": str(fill_val)}
            else:
                after_metrics = {"missing_after": 0, "imputed_value": None}
                rows_changed = 0

        elif action == "CLIP_OUTLIERS":
            col = spec.column or spec.parameters.get("column")
            lower_q = float(spec.parameters.get("lower_quantile", 0.01))
            upper_q = float(spec.parameters.get("upper_quantile", 0.99))

            lower_bound = float(df[col].quantile(lower_q))
            upper_bound = float(df[col].quantile(upper_q))
            before_metrics = {
                "lower_quantile": lower_q,
                "upper_quantile": upper_q,
                "lower_bound": lower_bound,
                "upper_bound": upper_bound,
            }

            clipped_mask = (df[col] < lower_bound) | (df[col] > upper_bound)
            rows_changed = int(clipped_mask.sum())
            df[col] = df[col].clip(lower=lower_bound, upper=upper_bound)
            after_metrics = {"values_clipped": rows_changed}

        elif action == "DROP_COLUMN":
            cols_to_drop = []
            if spec.columns:
                cols_to_drop = list(spec.columns)
            elif spec.column:
                cols_to_drop = [spec.column]
            elif "columns" in spec.parameters:
                cols_to_drop = list(spec.parameters["columns"])

            before_metrics = {"columns_to_drop": cols_to_drop, "columns_before": cols_before}
            df = df.drop(columns=cols_to_drop)
            cols_changed = len(cols_to_drop)
            after_metrics = {"columns_after": len(df.columns), "dropped_columns": cols_to_drop}

        provenance_record = {
            "action": action,
            "column": spec.column,
            "columns": spec.columns,
            "parameters": spec.parameters,
            "source_issue_ids": spec.source_issue_ids,
            "reason": spec.rationale,
            "applied_order": applied_order,
            "rows_changed": rows_changed,
            "columns_changed": cols_changed,
            "before_metrics": before_metrics,
            "after_metrics": after_metrics,
            "executor_version": self.version,
            "executed_at": now_iso.isoformat(),
        }

        return df, provenance_record

    def validate_output_dataframe(self, df: pd.DataFrame) -> None:
        """Validate DataFrame integrity and Parquet serializability prior to committing."""
        if len(df.columns) == 0:
            raise InvalidTransformationException("Remediated dataset cannot have 0 columns.")
        if len(df) == 0:
            raise InvalidTransformationException("Remediated dataset cannot have 0 rows.")

        # Check for duplicate column names
        if len(df.columns) != len(set(df.columns)):
            raise InvalidTransformationException("Remediated dataset contains duplicate column names.")

        # Check that column names are all valid non-empty strings
        for col in df.columns:
            if not isinstance(col, str) or not col.strip():
                raise InvalidTransformationException(f"Invalid column header name: '{col}'. Must be non-empty string.")

        # Verify Parquet serialization succeeds in memory and can be reloaded
        try:
            buf = io.BytesIO()
            df.to_parquet(buf, engine="pyarrow", index=False, compression="snappy")
            buf.seek(0)
            reloaded_df = pd.read_parquet(buf, engine="pyarrow")
            if len(reloaded_df) != len(df) or len(reloaded_df.columns) != len(df.columns):
                raise InvalidTransformationException("Parquet serialization verification failed: dimension mismatch.")
        except Exception as exc:
            raise InvalidTransformationException(f"Parquet serialization validation failed: {exc}") from exc
