"""Unit tests for Pydantic AI schemas, allowlisted transformations, and boundary validations."""

import pytest
from pydantic import ValidationError

from app.schemas.ai import (
    ALLOWED_ACTIONS_SET,
    DISALLOWED_ACTIONS_SET,
    AIReportContent,
    FindingExplanation,
    RemediationStep,
    RiskAssessmentItem,
    TransformationSpec,
)


def test_transformation_spec_allowed_actions():
    """Verify that all allowlisted transformation actions are accepted with valid parameters."""
    for action in ALLOWED_ACTIONS_SET:
        if action == "DROP_COLUMN":
            spec = TransformationSpec(
                action=action,
                column="leak_col",
                rationale="Dropping target leakage column",
            )
        elif action == "REMOVE_DUPLICATES":
            spec = TransformationSpec(
                action=action,
                parameters={"subset": ["id"], "keep": "first"},
                rationale="Removing duplicate records",
            )
        elif action == "IMPUTE":
            spec = TransformationSpec(
                action=action,
                column="age",
                parameters={"strategy": "median"},
                rationale="Imputing missing numerical entries",
            )
        elif action == "CAST_TYPE":
            spec = TransformationSpec(
                action=action,
                column="zip_code",
                parameters={"target_type": "string"},
                rationale="Casting postal code to string",
            )
        elif action == "CLIP_OUTLIERS":
            spec = TransformationSpec(
                action=action,
                column="income",
                parameters={"lower_quantile": 0.01, "upper_quantile": 0.99},
                rationale="Winsorizing extreme income values",
            )
        assert spec.action == action


def test_transformation_spec_disallowed_actions_strictly_rejected():
    """Verify that dangerous and non-allowlisted actions are strictly rejected."""
    for action in DISALLOWED_ACTIONS_SET:
        with pytest.raises(ValidationError) as exc:
            TransformationSpec.model_validate({
                "action": action,
                "column": "col1",
                "rationale": "Adversarial action attempt",
            })
        assert "Input should be" in str(exc.value) or "allowlist" in str(exc.value)


def test_transformation_spec_drop_column_validation():
    """Test DROP_COLUMN validation requiring at least one target column."""
    # Valid with single column
    spec1 = TransformationSpec(action="DROP_COLUMN", column="feat1", rationale="test")
    assert spec1.column == "feat1"

    # Valid with multiple columns
    spec2 = TransformationSpec(action="DROP_COLUMN", columns=["feat1", "feat2"], rationale="test")
    assert len(spec2.columns) == 2

    # Valid with parameters['columns']
    spec3 = TransformationSpec(action="DROP_COLUMN", parameters={"columns": ["c1"]}, rationale="test")
    assert spec3.parameters["columns"] == ["c1"]

    # Invalid without any column
    with pytest.raises(ValidationError) as exc:
        TransformationSpec(action="DROP_COLUMN", rationale="No column specified")
    assert "requires at least one target column" in str(exc.value)


def test_transformation_spec_impute_validation():
    """Test IMPUTE parameter bounds and strategies."""
    # Valid strategies
    for strat in ["mean", "median", "mode"]:
        spec = TransformationSpec(
            action="IMPUTE",
            column="salary",
            parameters={"strategy": strat},
            rationale="test",
        )
        assert spec.parameters["strategy"] == strat

    # Valid constant with fill_value
    spec_const = TransformationSpec(
        action="IMPUTE",
        column="salary",
        parameters={"strategy": "constant", "fill_value": 0},
        rationale="test",
    )
    assert spec_const.parameters["fill_value"] == 0

    # Invalid strategy
    with pytest.raises(ValidationError) as exc:
        TransformationSpec(
            action="IMPUTE",
            column="salary",
            parameters={"strategy": "arbitrary_model_imputation"},
            rationale="test",
        )
    assert "strategy 'arbitrary_model_imputation' is invalid" in str(exc.value)

    # Constant missing fill_value
    with pytest.raises(ValidationError) as exc:
        TransformationSpec(
            action="IMPUTE",
            column="salary",
            parameters={"strategy": "constant"},
            rationale="test",
        )
    assert "requires 'fill_value'" in str(exc.value)


def test_transformation_spec_cast_type_validation():
    """Test CAST_TYPE target_type verification."""
    # Valid types
    for dtype in ["int64", "float64", "string", "boolean", "datetime64[ns]"]:
        spec = TransformationSpec(
            action="CAST_TYPE",
            column="val",
            parameters={"target_type": dtype},
            rationale="test",
        )
        assert spec.parameters["target_type"] == dtype

    # Invalid target type
    with pytest.raises(ValidationError) as exc:
        TransformationSpec(
            action="CAST_TYPE",
            column="val",
            parameters={"target_type": "eval_code"},
            rationale="test",
        )
    assert "target_type 'eval_code' is invalid" in str(exc.value)


def test_transformation_spec_clip_outliers_validation():
    """Test CLIP_OUTLIERS quantile bounds."""
    # Valid quantiles
    spec = TransformationSpec(
        action="CLIP_OUTLIERS",
        column="val",
        parameters={"lower_quantile": 0.05, "upper_quantile": 0.95},
        rationale="test",
    )
    assert spec.parameters["lower_quantile"] == 0.05

    # Lower quantile out of range (> 0.5)
    with pytest.raises(ValidationError) as exc:
        TransformationSpec(
            action="CLIP_OUTLIERS",
            column="val",
            parameters={"lower_quantile": 0.6, "upper_quantile": 0.95},
            rationale="test",
        )
    assert "lower_quantile must be between 0.0 and 0.5" in str(exc.value)

    # Upper quantile out of range (< 0.5)
    with pytest.raises(ValidationError) as exc:
        TransformationSpec(
            action="CLIP_OUTLIERS",
            column="val",
            parameters={"lower_quantile": 0.01, "upper_quantile": 0.4},
            rationale="test",
        )
    assert "upper_quantile must be between 0.5 and 1.0" in str(exc.value)

    # Lower quantile >= Upper quantile
    with pytest.raises(ValidationError) as exc:
        TransformationSpec(
            action="CLIP_OUTLIERS",
            column="val",
            parameters={"lower_quantile": 0.5, "upper_quantile": 0.5},
            rationale="test",
        )
    assert "strictly less than" in str(exc.value)


def test_finding_explanation_schema_validation():
    """Test FindingExplanation Pydantic model contract."""
    expl = FindingExplanation(
        explanation="High missingness in feature age.",
        why_it_matters="Reduces statistical power.",
        practical_impact="Biases predictions.",
        recommended_actions=["Impute with median"],
        limitations=["May distort variance"],
    )
    assert expl.explanation.startswith("High missingness")
    assert len(expl.recommended_actions) == 1


def test_ai_report_content_schema_validation():
    """Test AIReportContent structured model contract."""
    report = AIReportContent(
        executive_summary="Summary of dataset quality",
        risk_assessment=[
            RiskAssessmentItem(
                category="Leakage",
                severity="CRITICAL",
                summary="Target identity found",
                ml_impact="Model will overfit trivially",
            )
        ],
        prioritized_remediation_steps=[
            RemediationStep(
                priority=1,
                issue_reference="issue_1",
                problem="Leakage feature",
                recommendation="Drop feature",
                reason="Prevents data snooping",
                risk="None",
            )
        ],
        ml_preparation_plan=["Drop leak feature", "Scale features"],
        transformation_specs=[
            TransformationSpec(
                action="DROP_COLUMN",
                column="leak_col",
                rationale="Prevent snooping",
            )
        ],
        generated_python_code="# Non-executable advisory script\n",
    )
    assert len(report.risk_assessment) == 1
    assert len(report.transformation_specs) == 1
