"""Pydantic contracts and schemas for AI interpretation, explanation, and remediation planning."""

from datetime import datetime
from typing import Any, Dict, List, Literal, Optional
import uuid
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

# Explicit allowlist of permissible data transformations in Dataset Doctor
AllowedAction = Literal[
    "DROP_COLUMN",
    "REMOVE_DUPLICATES",
    "IMPUTE",
    "CAST_TYPE",
    "CLIP_OUTLIERS",
]

ALLOWED_ACTIONS_SET = {
    "DROP_COLUMN",
    "REMOVE_DUPLICATES",
    "IMPUTE",
    "CAST_TYPE",
    "CLIP_OUTLIERS",
}

DISALLOWED_ACTIONS_SET = {
    "RUN_PYTHON",
    "EXECUTE_SHELL",
    "EXECUTE_SQL",
    "DOWNLOAD_FILE",
    "DELETE_FILE",
    "NETWORK_REQUEST",
    "ARBITRARY_CODE",
}

VALID_IMPUTE_STRATEGIES = {"mean", "median", "mode", "constant"}
VALID_CAST_TYPES = {"int64", "float64", "string", "boolean", "datetime64[ns]"}


class TransformationSpec(BaseModel):
    """Specification of an advisory, allowlisted data cleaning transformation."""

    action: AllowedAction = Field(
        description="Allowlisted transformation operation",
    )
    column: Optional[str] = Field(
        default=None,
        description="Target feature column name if single-column transformation",
    )
    columns: Optional[List[str]] = Field(
        default=None,
        description="Target columns list if multi-column transformation (e.g. DROP_COLUMN)",
    )
    parameters: Dict[str, Any] = Field(
        default_factory=dict,
        description="Validated operational parameters for the transformation",
    )
    rationale: str = Field(
        description="Clear justification grounded in specific deterministic findings",
    )
    source_issue_ids: List[str] = Field(
        default_factory=list,
        description="UUIDs of deterministic QualityIssues that motivated this proposal",
    )

    @model_validator(mode="after")
    def validate_action_and_parameters(self) -> "TransformationSpec":
        """Strict domain-level validation of transformation parameters and bounds."""
        action = self.action

        if action not in ALLOWED_ACTIONS_SET:
            raise ValueError(f"Action '{action}' is not in the allowlist of safe transformations.")

        # 1. DROP_COLUMN validation
        if action == "DROP_COLUMN":
            has_col = bool(self.column and self.column.strip())
            has_cols = bool(self.columns and len(self.columns) > 0)
            param_cols = self.parameters.get("columns")
            has_param_cols = bool(param_cols and isinstance(param_cols, list) and len(param_cols) > 0)

            if not (has_col or has_cols or has_param_cols):
                raise ValueError("DROP_COLUMN requires at least one target column via 'column', 'columns', or parameters['columns']")

        # 2. REMOVE_DUPLICATES validation
        elif action == "REMOVE_DUPLICATES":
            subset = self.parameters.get("subset")
            if subset is not None:
                if not isinstance(subset, list) or not all(isinstance(c, str) for c in subset):
                    raise ValueError("REMOVE_DUPLICATES parameter 'subset' must be a list of column names")
            keep = self.parameters.get("keep")
            if keep is not None and keep not in ("first", "last", False):
                raise ValueError("REMOVE_DUPLICATES parameter 'keep' must be 'first', 'last', or False")

        # 3. IMPUTE validation
        elif action == "IMPUTE":
            target_col = self.column or self.parameters.get("column")
            if not target_col:
                raise ValueError("IMPUTE requires a target column")
            strategy = self.parameters.get("strategy")
            if not strategy or strategy not in VALID_IMPUTE_STRATEGIES:
                raise ValueError(
                    f"IMPUTE strategy '{strategy}' is invalid. Allowed strategies: {sorted(VALID_IMPUTE_STRATEGIES)}"
                )
            if strategy == "constant" and "fill_value" not in self.parameters:
                raise ValueError("IMPUTE with 'constant' strategy requires 'fill_value' parameter")

        # 4. CAST_TYPE validation
        elif action == "CAST_TYPE":
            target_col = self.column or self.parameters.get("column")
            if not target_col:
                raise ValueError("CAST_TYPE requires a target column")
            target_type = self.parameters.get("target_type")
            if not target_type or target_type not in VALID_CAST_TYPES:
                raise ValueError(
                    f"CAST_TYPE target_type '{target_type}' is invalid. Allowed types: {sorted(VALID_CAST_TYPES)}"
                )

        # 5. CLIP_OUTLIERS validation
        elif action == "CLIP_OUTLIERS":
            target_col = self.column or self.parameters.get("column")
            if not target_col:
                raise ValueError("CLIP_OUTLIERS requires a target column")
            lower = self.parameters.get("lower_quantile", 0.01)
            upper = self.parameters.get("upper_quantile", 0.99)
            if not isinstance(lower, (int, float)) or not isinstance(upper, (int, float)):
                raise ValueError("CLIP_OUTLIERS lower_quantile and upper_quantile must be numeric")
            if not (0.0 <= lower <= 0.5):
                raise ValueError(f"CLIP_OUTLIERS lower_quantile must be between 0.0 and 0.5 (got {lower})")
            if not (0.5 <= upper <= 1.0):
                raise ValueError(f"CLIP_OUTLIERS upper_quantile must be between 0.5 and 1.0 (got {upper})")
            if lower >= upper:
                raise ValueError(f"lower_quantile ({lower}) must be strictly less than upper_quantile ({upper})")

        return self


class RiskAssessmentItem(BaseModel):
    """High-level risk item contextualized for downstream machine learning."""

    category: str = Field(description="Defect category, e.g. Data Leakage, High Nullity, Outlier Contamination")
    severity: Literal["CRITICAL", "HIGH", "MEDIUM", "LOW", "INFO"] = Field(
        description="Standardized severity level",
    )
    summary: str = Field(description="Conceptual risk summary grounded in detected findings")
    ml_impact: str = Field(description="Specific practical consequence for modeling (e.g. overfitting, bias, train/test mismatch)")


class RemediationStep(BaseModel):
    """Prioritized remediation step synthesized from deterministic findings."""

    priority: int = Field(ge=1, description="Execution priority ranking (1 is highest)")
    issue_reference: str = Field(description="Associated issue identifier or column/defect reference")
    problem: str = Field(description="Clear problem statement grounded in deterministic evidence")
    recommendation: str = Field(description="Advisory engineering action")
    reason: str = Field(description="Technical reason for the recommendation")
    risk: str = Field(description="Trade-off or potential downside of this remediation")


class FindingExplanation(BaseModel):
    """Grounded interpretation and contextualization of a single deterministic QualityIssue."""

    explanation: str = Field(
        description="Grounded, conceptual explanation of what this issue means without fabricating numbers",
    )
    why_it_matters: str = Field(
        description="Why this defect compromises tabular data quality or modeling validity",
    )
    practical_impact: str = Field(
        description="Real-world consequences on model training, validation, or inference",
    )
    recommended_actions: List[str] = Field(
        description="Allowlisted, actionable recommendations to fix or mitigate the issue",
    )
    limitations: List[str] = Field(
        default_factory=list,
        description="Known caveats or limitations of standard mitigations for this finding",
    )


class AIReportContent(BaseModel):
    """Structured synthesis of full AI remediation and risk analysis."""

    executive_summary: str = Field(
        description="Comprehensive overview of dataset health and primary risks",
    )
    risk_assessment: List[RiskAssessmentItem] = Field(
        default_factory=list,
        description="Contextualized evaluation of major data risks",
    )
    prioritized_remediation_steps: List[RemediationStep] = Field(
        default_factory=list,
        description="Sequenced list of prioritized remediation actions",
    )
    ml_preparation_plan: List[str] = Field(
        default_factory=list,
        description="Step-by-step strategy for preparing the dataset for ML pipelines",
    )
    transformation_specs: List[TransformationSpec] = Field(
        default_factory=list,
        description="Strictly allowlisted transformation specifications for human review",
    )
    generated_python_code: Optional[str] = Field(
        default=None,
        description="Optional inert, advisory Python code snippet clearly marked as non-executable",
    )


# API Request and Response Models
class FindingExplanationResponse(BaseModel):
    """API response model for single finding explanation."""

    model_config = ConfigDict(from_attributes=True)

    issue_id: uuid.UUID
    provider: str
    model: str
    prompt_version: str
    explanation: str
    why_it_matters: str
    practical_impact: str
    recommended_actions: List[str]
    limitations: List[str]
    cached: bool = False
    created_at: datetime


class GenerateAIPlanRequest(BaseModel):
    """Request payload for generating an AI remediation plan."""

    force_regenerate: bool = Field(
        default=False,
        description="When True, bypasses existing cached report and synthesizes a new plan",
    )


class AIReportResponse(BaseModel):
    """API response model for full AI remediation plan."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    analysis_run_id: uuid.UUID
    provider: str
    model: str
    prompt_version: str
    executive_summary: str
    risk_assessment: List[RiskAssessmentItem]
    remediation_plan: List[RemediationStep]
    transformation_specs: List[TransformationSpec]
    ml_preparation_plan: List[str]
    generated_python_code: Optional[str] = None
    cached: bool = False
    created_at: datetime
