"""AI interpretation, grounded explanation, and remediation planning orchestration service."""

import logging
from typing import Optional
import uuid
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.exceptions import (
    AIRefusalException,
    AIProviderOutputException,
    EntityNotFoundException,
    InvalidTransformationException,
    ValidationException,
)
from app.models.ai import AIReport, FindingExplanationRecord
from app.models.analysis import AnalysisRun, AnalysisStatus, QualityIssue
from app.schemas.ai import (
    ALLOWED_ACTIONS_SET,
    AIReportContent,
    AIReportResponse,
    FindingExplanationResponse,
    RiskAssessmentItem,
    RemediationStep,
    TransformationSpec,
)
from app.services.ai.findings_digest import FindingsDigestGenerator
from app.services.ai.prompts.finding_explanation import FINDING_EXPLANATION_PROMPT_VERSION
from app.services.ai.prompts.remediation_plan import REMEDIATION_PLAN_PROMPT_VERSION
from app.services.ai_provider import BaseLLMProvider

logger = logging.getLogger(__name__)


class AIService:
    """Orchestrates grounded explanation generation, remediation planning, and persistence."""

    def __init__(
        self,
        provider: BaseLLMProvider,
        digest_generator: Optional[FindingsDigestGenerator] = None,
        settings: Optional[Settings] = None,
    ):
        self.provider = provider
        self.digest_generator = digest_generator or FindingsDigestGenerator()
        self.settings = settings or get_settings()

    async def explain_issue(
        self,
        db: AsyncSession,
        run_id: uuid.UUID,
        issue_id: uuid.UUID,
    ) -> FindingExplanationResponse:
        """Generate or retrieve a cached grounded conceptual explanation for an individual QualityIssue."""
        # 1. Validate AnalysisRun existence
        run_query = select(AnalysisRun).where(AnalysisRun.id == run_id)
        run_res = await db.execute(run_query)
        run = run_res.scalar_one_or_none()
        if not run:
            raise EntityNotFoundException("AnalysisRun", str(run_id))

        # 2. Validate QualityIssue existence
        issue_query = select(QualityIssue).where(QualityIssue.id == issue_id)
        issue_res = await db.execute(issue_query)
        issue = issue_res.scalar_one_or_none()
        if not issue:
            raise EntityNotFoundException("QualityIssue", str(issue_id))

        # 3. Validate that issue belongs to the specified run
        if issue.analysis_run_id != run_id:
            raise ValidationException(
                f"QualityIssue '{issue_id}' belongs to run '{issue.analysis_run_id}', not '{run_id}'"
            )

        # 4. Check for existing cached explanation
        cache_query = (
            select(FindingExplanationRecord)
            .where(
                FindingExplanationRecord.quality_issue_id == issue_id,
                FindingExplanationRecord.provider_model == self.provider.model_name,
                FindingExplanationRecord.prompt_version == FINDING_EXPLANATION_PROMPT_VERSION,
            )
            .order_by(FindingExplanationRecord.created_at.desc())
        )
        cache_res = await db.execute(cache_query)
        cached_record = cache_res.scalar_one_or_none()

        if cached_record:
            logger.info("Cache hit for FindingExplanation on issue %s (model: %s)", issue_id, self.provider.model_name)
            return FindingExplanationResponse(
                issue_id=cached_record.quality_issue_id,
                provider=self.provider.provider_name,
                model=cached_record.provider_model,
                prompt_version=cached_record.prompt_version,
                explanation=cached_record.explanation_text,
                why_it_matters=cached_record.why_it_matters,
                practical_impact=cached_record.practical_impact,
                recommended_actions=cached_record.recommended_actions,
                limitations=cached_record.limitations,
                cached=True,
                created_at=cached_record.created_at,
            )

        # 5. Call AI provider
        logger.info("Requesting grounded explanation for issue %s from provider %s", issue_id, self.provider.provider_name)
        result = await self.provider.explain_finding(finding=issue)

        # 6. Check provider status and refusals
        if result.refusal:
            raise AIRefusalException(result.refusal)
        if result.is_error or not result.parsed:
            raise AIProviderOutputException(result.error_message or "Failed to explain finding")

        parsed = result.parsed

        # 7. Persist explanation
        record = FindingExplanationRecord(
            quality_issue_id=issue.id,
            provider_model=self.provider.model_name,
            prompt_version=FINDING_EXPLANATION_PROMPT_VERSION,
            explanation_text=parsed.explanation,
            why_it_matters=parsed.why_it_matters,
            practical_impact=parsed.practical_impact,
            recommended_actions=parsed.recommended_actions,
            limitations=parsed.limitations,
            input_tokens=result.usage.input_tokens,
            output_tokens=result.usage.output_tokens,
        )
        db.add(record)
        await db.commit()
        await db.refresh(record)

        return FindingExplanationResponse(
            issue_id=record.quality_issue_id,
            provider=self.provider.provider_name,
            model=record.provider_model,
            prompt_version=record.prompt_version,
            explanation=record.explanation_text,
            why_it_matters=record.why_it_matters,
            practical_impact=record.practical_impact,
            recommended_actions=record.recommended_actions,
            limitations=record.limitations,
            cached=False,
            created_at=record.created_at,
        )

    async def generate_remediation_plan(
        self,
        db: AsyncSession,
        run_id: uuid.UUID,
        force_regenerate: bool = False,
    ) -> AIReportResponse:
        """Synthesize an advisory, allowlisted data remediation plan and risk assessment."""
        # 1. Validate AnalysisRun existence and status
        run_query = (
            select(AnalysisRun)
            .where(AnalysisRun.id == run_id)
            .options(selectinload(AnalysisRun.dataset_version))
        )
        run_res = await db.execute(run_query)
        run = run_res.scalar_one_or_none()
        if not run:
            raise EntityNotFoundException("AnalysisRun", str(run_id))

        if run.status != AnalysisStatus.COMPLETED.value:
            raise ValidationException(
                f"Cannot generate AI plan for AnalysisRun '{run_id}' with status '{run.status}'. Must be COMPLETED."
            )

        # 2. Check for existing cached AIReport
        if not force_regenerate:
            report_query = (
                select(AIReport)
                .where(
                    AIReport.analysis_run_id == run_id,
                    AIReport.provider_model == self.provider.model_name,
                    AIReport.prompt_version == REMEDIATION_PLAN_PROMPT_VERSION,
                )
                .order_by(AIReport.created_at.desc())
            )
            report_res = await db.execute(report_query)
            cached_report = report_res.scalar_one_or_none()

            if cached_report:
                logger.info("Cache hit for AIReport on run %s (model: %s)", run_id, self.provider.model_name)
                return self._build_report_response(cached_report, cached=True)

        # 3. Load issues for the run
        issues_query = select(QualityIssue).where(QualityIssue.analysis_run_id == run_id)
        issues_res = await db.execute(issues_query)
        issues = list(issues_res.scalars().all())

        # 4. Generate token-bounded findings digest
        digest = self.digest_generator.create_digest(
            analysis_run=run,
            issues=issues,
            max_tokens=self.settings.openai_max_input_tokens,
        )

        # 5. Call AI provider
        logger.info(
            "Synthesizing AI remediation plan for run %s (%d issues, truncated: %s)",
            run_id,
            digest.included_issues,
            digest.findings_truncated,
        )
        result = await self.provider.generate_remediation_plan(findings_digest=digest)

        # 6. Validate provider response
        if result.refusal:
            raise AIRefusalException(result.refusal)
        if result.is_error or not result.parsed:
            raise AIProviderOutputException(result.error_message or "Failed to generate remediation plan")

        parsed = result.parsed

        # 7. Strict domain validation on proposed transformation specs
        for spec in parsed.transformation_specs:
            if spec.action not in ALLOWED_ACTIONS_SET:
                raise InvalidTransformationException(
                    f"Transformation action '{spec.action}' is forbidden. Allowed: {sorted(ALLOWED_ACTIONS_SET)}"
                )

        # Ensure python code has warning header if present
        py_code = parsed.generated_python_code
        if py_code and not py_code.startswith("# AI-GENERATED ADVISORY CODE"):
            py_code = "# AI-GENERATED ADVISORY CODE - DO NOT EXECUTE AUTOMATICALLY\n" + py_code

        # 8. Persist AIReport record
        report = AIReport(
            analysis_run_id=run.id,
            provider_model=self.provider.model_name,
            prompt_version=REMEDIATION_PLAN_PROMPT_VERSION,
            executive_summary=parsed.executive_summary,
            risk_assessment=[item.model_dump() for item in parsed.risk_assessment],
            remediation_plan=[step.model_dump() for step in parsed.prioritized_remediation_steps],
            transformation_specs=[spec.model_dump() for spec in parsed.transformation_specs],
            ml_preparation_plan=parsed.ml_preparation_plan,
            generated_python_code=py_code,
            input_tokens=result.usage.input_tokens,
            output_tokens=result.usage.output_tokens,
            total_tokens=result.usage.total_tokens,
        )
        db.add(report)
        await db.commit()
        await db.refresh(report)

        return self._build_report_response(report, cached=False)

    async def get_latest_remediation_plan(
        self,
        db: AsyncSession,
        run_id: uuid.UUID,
    ) -> AIReportResponse:
        """Retrieve the latest stored AI remediation plan for an analysis run."""
        report_query = (
            select(AIReport)
            .where(AIReport.analysis_run_id == run_id)
            .order_by(AIReport.created_at.desc())
        )
        report_res = await db.execute(report_query)
        report = report_res.scalar_one_or_none()
        if not report:
            raise EntityNotFoundException("AIReport", f"No AI report found for analysis run '{run_id}'")

        return self._build_report_response(report, cached=True)

    def _build_report_response(self, report: AIReport, cached: bool) -> AIReportResponse:
        """Convert an AIReport database record into an AIReportResponse schema."""
        risk_items = [RiskAssessmentItem.model_validate(r) for r in report.risk_assessment]
        steps = [RemediationStep.model_validate(s) for s in report.remediation_plan]
        specs = [TransformationSpec.model_validate(t) for t in report.transformation_specs]

        return AIReportResponse(
            id=report.id,
            analysis_run_id=report.analysis_run_id,
            provider=self.provider.provider_name,
            model=report.provider_model,
            prompt_version=report.prompt_version,
            executive_summary=report.executive_summary,
            risk_assessment=risk_items,
            remediation_plan=steps,
            transformation_specs=specs,
            ml_preparation_plan=report.ml_preparation_plan,
            generated_python_code=report.generated_python_code,
            cached=cached,
            created_at=report.created_at,
        )
