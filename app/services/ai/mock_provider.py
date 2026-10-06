"""Mock LLM Provider for isolated, deterministic, and adversarial testing."""

import asyncio
from typing import Any, Dict, List, Optional, Type, TypeVar
from pydantic import BaseModel

from app.models.analysis import QualityIssue
from app.schemas.ai import (
    AIReportContent,
    FindingExplanation,
    RemediationStep,
    RiskAssessmentItem,
    TransformationSpec,
)
from app.services.ai.findings_digest import FindingsDigest
from app.services.ai.prompts.finding_explanation import build_finding_explanation_prompts
from app.services.ai.prompts.remediation_plan import build_remediation_plan_prompts
from app.services.ai_provider import BaseLLMProvider, LLMResponseResult, LLMUsage

T = TypeVar("T", bound=BaseModel)


class MockLLMProvider(BaseLLMProvider):
    """Controllable mock provider for unit tests, timeout tests, and injection tests."""

    def __init__(
        self,
        model_name: str = "mock-gpt-4o",
        canned_explanation: Optional[FindingExplanation] = None,
        canned_report: Optional[AIReportContent] = None,
        simulate_refusal: Optional[str] = None,
        simulate_timeout: bool = False,
        simulate_error: Optional[str] = None,
        simulate_malformed: bool = False,
        fail_first_n_calls: int = 0,
        transient_error_message: str = "Simulated temporary rate limit",
    ):
        self._model_name = model_name
        self.canned_explanation = canned_explanation
        self.canned_report = canned_report
        self.simulate_refusal = simulate_refusal
        self.simulate_timeout = simulate_timeout
        self.simulate_error = simulate_error
        self.simulate_malformed = simulate_malformed
        self.fail_first_n_calls = fail_first_n_calls
        self.transient_error_message = transient_error_message
        self.call_count = 0
        self.call_history: List[Dict[str, Any]] = []

    @property
    def provider_name(self) -> str:
        return "mock-provider"

    @property
    def model_name(self) -> str:
        return self._model_name

    async def generate_structured(
        self,
        system_prompt: str,
        user_prompt: str,
        response_schema: Type[T],
        temperature: float = 0.1,
        max_output_tokens: Optional[int] = None,
    ) -> LLMResponseResult[T]:
        self.call_count += 1
        call_record = {
            "call_index": self.call_count,
            "system_prompt": system_prompt,
            "user_prompt": user_prompt,
            "schema_name": response_schema.__name__,
            "temperature": temperature,
        }
        self.call_history.append(call_record)

        # 1. Simulate transient failure for retry testing
        if self.fail_first_n_calls > 0:
            self.fail_first_n_calls -= 1
            return LLMResponseResult[T](
                is_error=True,
                error_message=self.transient_error_message,
                model=self._model_name,
            )

        # 2. Simulate timeout
        if self.simulate_timeout:
            raise asyncio.TimeoutError("Simulated LLM provider request timeout")

        # 3. Simulate explicit provider refusal
        if self.simulate_refusal:
            return LLMResponseResult[T](
                refusal=self.simulate_refusal,
                model=self._model_name,
                usage=LLMUsage(prompt_tokens=50, completion_tokens=10, total_tokens=60),
            )

        # 4. Simulate persistent error
        if self.simulate_error:
            return LLMResponseResult[T](
                is_error=True,
                error_message=self.simulate_error,
                model=self._model_name,
            )

        # 5. Simulate malformed output
        if self.simulate_malformed:
            return LLMResponseResult[T](
                parsed=None,
                raw_content="<<<MALFORMED NOT JSON STRING>>>",
                is_error=True,
                error_message="Schema mismatch: failed to parse structured output",
                model=self._model_name,
            )

        # 6. Default mock responses based on schema
        if response_schema is FindingExplanation:
            explanation = self.canned_explanation or FindingExplanation(
                explanation="The feature exhibits a high concentration of missing values that exceeds nominal quality thresholds.",
                why_it_matters="Pervasive missing values distort feature distributions, drop sample size during listwise deletion, and bias model estimation.",
                practical_impact="Gradient boosting and linear models may either fail at inference or learn biased surrogate splits.",
                recommended_actions=[
                    "Impute missing values using median for numerical or mode for categorical features.",
                    "Evaluate if missingness carries structural signal using a missingness indicator column.",
                ],
                limitations=[
                    "Imputation assumes Missing at Random (MAR); if Missing Not at Random (MNAR), bias persists.",
                ],
            )
            return LLMResponseResult[T](
                parsed=explanation,  # type: ignore
                raw_content=explanation.model_dump_json(),
                model=self._model_name,
                usage=LLMUsage(prompt_tokens=320, completion_tokens=140, total_tokens=460),
            )

        if response_schema is AIReportContent:
            report = self.canned_report or AIReportContent(
                executive_summary="The dataset exhibits moderate structural readiness with key risks in missingness and class balance.",
                risk_assessment=[
                    RiskAssessmentItem(
                        category="Missing Data",
                        severity="HIGH",
                        summary="Multiple columns have significant null fractions exceeding 20%.",
                        ml_impact="Reduces sample efficiency and risks test-set distribution shift.",
                    ),
                    RiskAssessmentItem(
                        category="Target Imbalance",
                        severity="MEDIUM",
                        summary="Minority class represents under 15% of observations.",
                        ml_impact="Model training may favor majority class predictions.",
                    ),
                ],
                prioritized_remediation_steps=[
                    RemediationStep(
                        priority=1,
                        issue_reference="missing_features",
                        problem="Missing values in feature columns",
                        recommendation="Impute numerical features using median strategy",
                        reason="Prevents sample loss and preserves feature distributions",
                        risk="May underestimate feature variance if missing fraction is very high",
                    ),
                    RemediationStep(
                        priority=2,
                        issue_reference="outlier_detection",
                        problem="Extreme numerical values detected",
                        recommendation="Clip outliers between 1st and 99th quantiles",
                        reason="Stabilizes loss surface for linear and neural estimators",
                        risk="Removes true tail phenomena if domain allows extreme values",
                    ),
                ],
                ml_preparation_plan=[
                    "Step 1: Apply deterministic imputation on identified missing columns.",
                    "Step 2: Clip extreme outliers in unbounded continuous features.",
                    "Step 3: Establish stratified train/validation/test splits.",
                ],
                transformation_specs=[
                    TransformationSpec(
                        action="IMPUTE",
                        column="age",
                        parameters={"strategy": "median"},
                        rationale="Age contains missing entries that require central tendency imputation.",
                        source_issue_ids=[],
                    ),
                    TransformationSpec(
                        action="CLIP_OUTLIERS",
                        column="income",
                        parameters={"lower_quantile": 0.01, "upper_quantile": 0.99},
                        rationale="Income contains extreme values that skew feature distribution.",
                        source_issue_ids=[],
                    ),
                ],
                generated_python_code="# AI-GENERATED ADVISORY CODE - DO NOT EXECUTE AUTOMATICALLY\n# import pandas as pd\n# df['age'] = df['age'].fillna(df['age'].median())\n",
            )
            return LLMResponseResult[T](
                parsed=report,  # type: ignore
                raw_content=report.model_dump_json(),
                model=self._model_name,
                usage=LLMUsage(prompt_tokens=1200, completion_tokens=650, total_tokens=1850),
            )

        # Fallback empty model instance
        empty_instance = response_schema.model_construct()
        return LLMResponseResult[T](
            parsed=empty_instance,
            model=self._model_name,
            usage=LLMUsage(prompt_tokens=100, completion_tokens=50, total_tokens=150),
        )

    async def explain_finding(
        self,
        finding: QualityIssue,
        context: Optional[Dict[str, Any]] = None,
    ) -> LLMResponseResult[FindingExplanation]:
        sys_prompt, user_prompt = build_finding_explanation_prompts(finding, context)
        return await self.generate_structured(
            system_prompt=sys_prompt,
            user_prompt=user_prompt,
            response_schema=FindingExplanation,
        )

    async def generate_remediation_plan(
        self,
        findings_digest: FindingsDigest,
        context: Optional[Dict[str, Any]] = None,
    ) -> LLMResponseResult[AIReportContent]:
        sys_prompt, user_prompt = build_remediation_plan_prompts(findings_digest, context)
        return await self.generate_structured(
            system_prompt=sys_prompt,
            user_prompt=user_prompt,
            response_schema=AIReportContent,
        )
