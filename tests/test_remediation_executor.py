"""Unit tests for the deterministic RemediationExecutor covering all transformations, validations, and edge cases."""

import numpy as np
import pandas as pd
import pytest

from app.core.exceptions import InvalidTransformationException, ValidationException
from app.schemas.ai import TransformationSpec
from app.services.remediation_executor import RemediationExecutor, compute_snapshot_metrics


@pytest.fixture
def sample_df():
    """Sample DataFrame with missing values, duplicates, outliers, and type-cast targets."""
    return pd.DataFrame({
        "id": [1, 2, 2, 4, 5, 6, 7, 8, 9, 10],
        "age": [25.0, 30.0, 30.0, np.nan, 45.0, 50.0, 35.0, 28.0, 999.0, -50.0],  # outliers: 999, -50; 1 missing
        "salary_str": ["50000", "60000", "60000", "75000", "80000", "90000", "70000", "65000", "120000", "40000"],
        "category": ["A", "B", "B", np.nan, "A", "A", "C", "B", "A", "C"],
        "useless_feature": [1, 1, 1, 1, 1, 1, 1, 1, 1, 1],
        "target": [0, 1, 1, 0, 1, 0, 1, 0, 1, 0],
    })


def test_remove_duplicates(sample_df):
    executor = RemediationExecutor()
    spec = TransformationSpec(
        action="REMOVE_DUPLICATES",
        parameters={"subset": ["id"], "keep": "first"},
        rationale="Remove duplicate id records",
    )
    df_result, prov = executor.execute_plan(sample_df, [spec])
    assert len(df_result) == 9  # row 2 duplicated
    assert prov[0]["rows_changed"] == 1
    assert len(sample_df) == 10  # source df untouched!


def test_remove_duplicates_keep_last(sample_df):
    executor = RemediationExecutor()
    spec = TransformationSpec(
        action="REMOVE_DUPLICATES",
        parameters={"subset": ["id"], "keep": "last"},
        rationale="Remove duplicate id keeping last",
    )
    df_result, prov = executor.execute_plan(sample_df, [spec])
    assert len(df_result) == 9
    assert prov[0]["after_metrics"]["rows"] == 9


def test_impute_mean(sample_df):
    executor = RemediationExecutor()
    spec = TransformationSpec(
        action="IMPUTE",
        column="age",
        parameters={"strategy": "mean"},
        rationale="Impute missing age with mean",
    )
    df_result, prov = executor.execute_plan(sample_df, [spec])
    assert df_result["age"].isna().sum() == 0
    assert prov[0]["rows_changed"] == 1
    # Check non-missing values were untouched
    assert df_result.loc[0, "age"] == 25.0


def test_impute_median(sample_df):
    executor = RemediationExecutor()
    spec = TransformationSpec(
        action="IMPUTE",
        column="age",
        parameters={"strategy": "median"},
        rationale="Impute missing age with median",
    )
    df_result, prov = executor.execute_plan(sample_df, [spec])
    assert df_result["age"].isna().sum() == 0


def test_impute_mode(sample_df):
    executor = RemediationExecutor()
    spec = TransformationSpec(
        action="IMPUTE",
        column="category",
        parameters={"strategy": "mode"},
        rationale="Impute missing category with mode",
    )
    df_result, prov = executor.execute_plan(sample_df, [spec])
    assert df_result["category"].isna().sum() == 0
    assert df_result.loc[3, "category"] == "A"  # 'A' is the most frequent mode


def test_impute_constant(sample_df):
    executor = RemediationExecutor()
    spec = TransformationSpec(
        action="IMPUTE",
        column="category",
        parameters={"strategy": "constant", "fill_value": "UNKNOWN"},
        rationale="Impute missing category with constant UNKNOWN",
    )
    df_result, prov = executor.execute_plan(sample_df, [spec])
    assert df_result["category"].isna().sum() == 0
    assert df_result.loc[3, "category"] == "UNKNOWN"


def test_impute_mean_rejected_on_string_column(sample_df):
    executor = RemediationExecutor()
    spec = TransformationSpec(
        action="IMPUTE",
        column="category",
        parameters={"strategy": "mean"},
        rationale="Invalid mean on string",
    )
    with pytest.raises(InvalidTransformationException, match="only valid for numeric columns"):
        executor.execute_plan(sample_df, [spec])


def test_cast_type_valid(sample_df):
    executor = RemediationExecutor()
    spec = TransformationSpec(
        action="CAST_TYPE",
        column="salary_str",
        parameters={"target_type": "int64"},
        rationale="Cast string salaries to int64",
    )
    df_result, prov = executor.execute_plan(sample_df, [spec])
    assert pd.api.types.is_integer_dtype(df_result["salary_str"])
    assert prov[0]["after_metrics"]["conversion_success"] is True


def test_cast_type_invalid_conversion():
    df = pd.DataFrame({"col": ["not_a_number", "abc"]})
    executor = RemediationExecutor()
    spec = TransformationSpec(
        action="CAST_TYPE",
        column="col",
        parameters={"target_type": "int64"},
        rationale="Invalid cast",
    )
    with pytest.raises(InvalidTransformationException, match="CAST_TYPE failed"):
        executor.execute_plan(df, [spec])


def test_clip_outliers(sample_df):
    executor = RemediationExecutor()
    spec = TransformationSpec(
        action="CLIP_OUTLIERS",
        column="age",
        parameters={"lower_quantile": 0.05, "upper_quantile": 0.95},
        rationale="Clip extreme age values",
    )
    df_result, prov = executor.execute_plan(sample_df, [spec])
    assert prov[0]["rows_changed"] > 0
    assert df_result["age"].max() < 999.0
    assert df_result["age"].min() > -50.0


def test_clip_outliers_rejected_on_string(sample_df):
    executor = RemediationExecutor()
    spec = TransformationSpec(
        action="CLIP_OUTLIERS",
        column="category",
        parameters={"lower_quantile": 0.05, "upper_quantile": 0.95},
        rationale="Invalid clipping on strings",
    )
    with pytest.raises(InvalidTransformationException, match="only valid for numeric columns"):
        executor.execute_plan(sample_df, [spec])


def test_drop_column(sample_df):
    executor = RemediationExecutor()
    spec = TransformationSpec(
        action="DROP_COLUMN",
        column="useless_feature",
        rationale="Drop constant column",
    )
    df_result, prov = executor.execute_plan(sample_df, [spec])
    assert "useless_feature" not in df_result.columns
    assert "useless_feature" in sample_df.columns  # source untouched


def test_drop_column_target_protection(sample_df):
    executor = RemediationExecutor()
    spec = TransformationSpec(
        action="DROP_COLUMN",
        column="target",
        rationale="Attempt to drop target",
    )
    with pytest.raises(InvalidTransformationException, match="Dropping the modeling target 'target' is prohibited"):
        executor.execute_plan(sample_df, [spec], target_column="target")


def test_target_modification_protection(sample_df):
    executor = RemediationExecutor()
    spec = TransformationSpec(
        action="CLIP_OUTLIERS",
        column="target",
        parameters={"lower_quantile": 0.01, "upper_quantile": 0.99},
        rationale="Attempt to modify target",
    )
    with pytest.raises(InvalidTransformationException, match="Direct modification of target column 'target' is prohibited"):
        executor.execute_plan(sample_df, [spec], target_column="target")


def test_drop_all_columns_rejected():
    df = pd.DataFrame({"a": [1, 2]})
    executor = RemediationExecutor()
    spec = TransformationSpec(
        action="DROP_COLUMN",
        column="a",
        rationale="Drop only column",
    )
    with pytest.raises(InvalidTransformationException, match="Cannot drop all columns"):
        executor.execute_plan(df, [spec])


def test_conflicting_transformations_rejected(sample_df):
    executor = RemediationExecutor()
    # Plan drops 'age' and imputes 'age'
    spec1 = TransformationSpec(
        action="DROP_COLUMN",
        column="age",
        rationale="Drop age",
    )
    spec2 = TransformationSpec(
        action="IMPUTE",
        column="age",
        parameters={"strategy": "mean"},
        rationale="Impute age",
    )
    with pytest.raises(InvalidTransformationException, match="cannot be dropped and simultaneously transformed"):
        executor.execute_plan(sample_df, [spec1, spec2])


def test_multiple_imputes_on_same_column_rejected(sample_df):
    executor = RemediationExecutor()
    spec1 = TransformationSpec(
        action="IMPUTE",
        column="age",
        parameters={"strategy": "mean"},
        rationale="Impute age 1",
    )
    spec2 = TransformationSpec(
        action="IMPUTE",
        column="age",
        parameters={"strategy": "median"},
        rationale="Impute age 2",
    )
    with pytest.raises(InvalidTransformationException, match="has multiple IMPUTE operations"):
        executor.execute_plan(sample_df, [spec1, spec2])


def test_deterministic_ordering(sample_df):
    """Transformations must be ordered deterministically:
    REMOVE_DUPLICATES -> CAST_TYPE -> IMPUTE -> CLIP_OUTLIERS -> DROP_COLUMN
    regardless of input list order.
    """
    executor = RemediationExecutor()
    spec_drop = TransformationSpec(action="DROP_COLUMN", column="useless_feature", rationale="Drop")
    spec_clip = TransformationSpec(action="CLIP_OUTLIERS", column="age", parameters={"lower_quantile": 0.05, "upper_quantile": 0.95}, rationale="Clip")
    spec_impute = TransformationSpec(action="IMPUTE", column="age", parameters={"strategy": "mean"}, rationale="Impute")
    spec_cast = TransformationSpec(action="CAST_TYPE", column="salary_str", parameters={"target_type": "int64"}, rationale="Cast")
    spec_dup = TransformationSpec(action="REMOVE_DUPLICATES", parameters={"subset": ["id"]}, rationale="Deduplicate")

    # Pass in reverse order: Drop -> Clip -> Impute -> Cast -> Dup
    reversed_plan = [spec_drop, spec_clip, spec_impute, spec_cast, spec_dup]
    df_result, prov = executor.execute_plan(sample_df, reversed_plan)

    applied_actions = [p["action"] for p in prov]
    assert applied_actions == ["REMOVE_DUPLICATES", "CAST_TYPE", "IMPUTE", "CLIP_OUTLIERS", "DROP_COLUMN"]


def test_snapshot_metrics(sample_df):
    metrics = compute_snapshot_metrics(sample_df)
    assert metrics["row_count"] == 10
    assert metrics["column_count"] == 6
    assert metrics["duplicate_rows"] == 1
    assert metrics["missing_cells"] == 2
    assert "age" in metrics["dtypes"]
