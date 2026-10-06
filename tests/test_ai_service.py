"""Service-level unit tests for AIService: grounded explanations, remediation planning, and caching."""

import uuid
from datetime import datetime, timezone
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import (
    AIRefusalException,
    AIProviderOutputException,
    EntityNotFoundException,
    InvalidTransformationException,
    ValidationException,
)
from app.models.analysis import AnalysisRun, AnalysisStatus, QualityIssue
from app.models.dataset import Dataset, DatasetVersion
from app.schemas.ai import (
    AIReportContent,
    FindingExplanation,
    RemediationStep,
    RiskAssessmentItem,
    TransformationSpec,
)
from app.services.ai.ai_service import AIService
from app.services.ai.mock_provider import MockLLMProvider


@pytest.fixture
async def setup_test_analysis(test_db_session: AsyncSession) -> tuple[AnalysisRun, QualityIssue]:
    """Create persistent test Dataset, DatasetVersion, AnalysisRun, and QualityIssue."""
    dataset = Dataset(
        id=uuid.uuid4(),
        name="Credit Scoring Dataset",
        description="Dataset for testing AI interpretation",
    )
    test_db_session.add(dataset)

    version = DatasetVersion(
        id=uuid.uuid4(),
        dataset_id=dataset.id,
        version_number=1,
        file_name="credit.csv",
        storage_path="uploads/credit.parquet",
        file_size_bytes=4096,
        sha256_hash="0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
        row_count=1000,
        column_count=8,
        raw_schema={"debt_ratio": "float64"},
    )
    test_db_session.add(version)

    run = AnalysisRun(
        id=uuid.uuid4(),
        dataset_version_id=version.id,
        status=AnalysisStatus.COMPLETED.value,
        target_column="default",
        problem_type="binary_classification",
        engine_version="1.0.0",
        ml_readiness_score=85.0,
        summary_metrics={"row_count": 1000, "null_rate": 0.02},
        completed_at=datetime.now(timezone.utc),
    )
    test_db_session.add(run)

    issue = QualityIssue(
        id=uuid.uuid4(),
        analysis_run_id=run.id,
        dataset_version_id=version.id,
        module="missing_analyzer",
        analyzer_version="1.0.0",
        category="MISSING_VALUES",
        severity="HIGH",
        column_name="debt_ratio",
        title="Elevated null fraction in debt_ratio",
        description="Column debt_ratio has 27.4% missing observations.",
        evidence={"missing_percentage": 27.4, "null_count": 274},
        remediation_hint="Impute with median or add missingness indicator.",
        detected_at=datetime.now(timezone.utc),
    )
    test_db_session.add(issue)

    await test_db_session.commit()
    await test_db_session.refresh(run)
    await test_db_session.refresh(issue)

    return run, issue


@pytest.mark.asyncio
async def test_explain_finding_success_and_grounding(
    test_db_session: AsyncSession,
    setup_test_analysis: tuple[AnalysisRun, QualityIssue],
):
    """Test grounded explanation generation citing deterministic evidence without fabricating stats."""
    run, issue = setup_test_analysis

    grounded_explanation = FindingExplanation(
        explanation="The debt_ratio feature exhibits a 27.4% missing rate, which is significant.",
        why_it_matters="High missingness reduces effective training samples.",
        practical_impact="Tree-based algorithms may split sub-optimally.",
        recommended_actions=["Impute with median debt ratio", "Create missingness indicator"],
        limitations=["Imputation may reduce variance"],
    )

    provider = MockLLMProvider(canned_explanation=grounded_explanation)
    service = AIService(provider=provider)

    # First call: generates and persists
    response1 = await service.explain_issue(
        db=test_db_session,
        run_id=run.id,
        issue_id=issue.id,
    )

    assert response1.cached is False
    assert response1.issue_id == issue.id
    assert "27.4%" in response1.explanation
    assert len(response1.recommended_actions) == 2
    assert provider.call_count == 1

    # Second call: must return cached result without calling provider again
    response2 = await service.explain_issue(
        db=test_db_session,
        run_id=run.id,
        issue_id=issue.id,
    )

    assert response2.cached is True
    assert response2.explanation == response1.explanation
    assert provider.call_count == 1  # Unchanged!


@pytest.mark.asyncio
async def test_explain_finding_wrong_analysis_run(
    test_db_session: AsyncSession,
    setup_test_analysis: tuple[AnalysisRun, QualityIssue],
):
    """Verify that requesting an issue with an unrelated run_id raises ValidationException."""
    run, issue = setup_test_analysis
    unrelated_run_id = uuid.uuid4()

    # Create another run in the DB
    other_run = AnalysisRun(
        id=unrelated_run_id,
        dataset_version_id=run.dataset_version_id,
        status=AnalysisStatus.COMPLETED.value,
    )
    test_db_session.add(other_run)
    await test_db_session.commit()

    provider = MockLLMProvider()
    service = AIService(provider=provider)

    with pytest.raises(ValidationException) as exc:
        await service.explain_issue(
            db=test_db_session,
            run_id=unrelated_run_id,
            issue_id=issue.id,
        )
    assert "belongs to run" in str(exc.value)


@pytest.mark.asyncio
async def test_explain_finding_refusal_raises_error(
    test_db_session: AsyncSession,
    setup_test_analysis: tuple[AnalysisRun, QualityIssue],
):
    """Verify that an AI refusal triggers AIRefusalException."""
    run, issue = setup_test_analysis
    provider = MockLLMProvider(simulate_refusal="I refuse to process this finding")
    service = AIService(provider=provider)

    with pytest.raises(AIRefusalException) as exc:
        await service.explain_issue(
            db=test_db_session,
            run_id=run.id,
            issue_id=issue.id,
        )
    assert "refuse" in str(exc.value)


@pytest.mark.asyncio
async def test_generate_ai_plan_success_and_caching(
    test_db_session: AsyncSession,
    setup_test_analysis: tuple[AnalysisRun, QualityIssue],
):
    """Test generating full AI remediation plan and caching behavior."""
    run, _ = setup_test_analysis
    provider = MockLLMProvider()
    service = AIService(provider=provider)

    # First call: generates and persists
    plan1 = await service.generate_remediation_plan(
        db=test_db_session,
        run_id=run.id,
        force_regenerate=False,
    )

    assert plan1.cached is False
    assert plan1.analysis_run_id == run.id
    assert len(plan1.risk_assessment) > 0
    assert len(plan1.transformation_specs) > 0
    assert plan1.generated_python_code.startswith("# AI-GENERATED ADVISORY CODE")
    assert provider.call_count == 1

    # Second call without force_regenerate: returns cached plan
    plan2 = await service.generate_remediation_plan(
        db=test_db_session,
        run_id=run.id,
        force_regenerate=False,
    )

    assert plan2.cached is True
    assert plan2.id == plan1.id
    assert provider.call_count == 1

    # Third call with force_regenerate=True: synthesizes new plan
    plan3 = await service.generate_remediation_plan(
        db=test_db_session,
        run_id=run.id,
        force_regenerate=True,
    )

    assert plan3.cached is False
    assert provider.call_count == 2


@pytest.mark.asyncio
async def test_generate_ai_plan_incomplete_run_rejected(
    test_db_session: AsyncSession,
    setup_test_analysis: tuple[AnalysisRun, QualityIssue],
):
    """Verify that attempting to plan remediation for a PENDING or RUNNING run raises ValidationException."""
    run, _ = setup_test_analysis
    run.status = AnalysisStatus.RUNNING.value
    await test_db_session.commit()

    provider = MockLLMProvider()
    service = AIService(provider=provider)

    with pytest.raises(ValidationException) as exc:
        await service.generate_remediation_plan(
            db=test_db_session,
            run_id=run.id,
        )
    assert "Must be COMPLETED" in str(exc.value)


@pytest.mark.asyncio
async def test_generate_ai_plan_disallowed_transformation_rejection(
    test_db_session: AsyncSession,
    setup_test_analysis: tuple[AnalysisRun, QualityIssue],
):
    """Verify that if LLM returns a forbidden action, it is rejected."""
    run, _ = setup_test_analysis

    # Create canned report that tries to sneak in EXECUTE_SHELL via model construct bypass
    illegal_spec = TransformationSpec.model_construct(
        action="EXECUTE_SHELL",  # type: ignore
        column=None,
        parameters={"command": "rm -rf /"},
        rationale="Sneaky action",
        source_issue_ids=[],
    )
    bad_report = AIReportContent.model_construct(
        executive_summary="Exploit report",
        risk_assessment=[],
        prioritized_remediation_steps=[],
        ml_preparation_plan=[],
        transformation_specs=[illegal_spec],
    )

    provider = MockLLMProvider(canned_report=bad_report)
    service = AIService(provider=provider)

    with pytest.raises(InvalidTransformationException) as exc:
        await service.generate_remediation_plan(
            db=test_db_session,
            run_id=run.id,
            force_regenerate=True,
        )
    assert "forbidden" in str(exc.value).lower()


@pytest.mark.asyncio
async def test_explain_finding_prompt_version_cache_invalidation(
    test_db_session: AsyncSession,
    setup_test_analysis: tuple[AnalysisRun, QualityIssue],
):
    """Verify that cached explanations with older prompt versions are bypassed when prompt version changes."""
    run, issue = setup_test_analysis

    # 1. First run generates cache with prompt_version "1.0.0"
    provider1 = MockLLMProvider()
    service1 = AIService(provider=provider1)
    res1 = await service1.explain_issue(db=test_db_session, run_id=run.id, issue_id=issue.id)
    assert res1.cached is False
    assert provider1.call_count == 1

    # 2. Simulate prompt version upgrade by patching FINDING_EXPLANATION_PROMPT_VERSION
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr("app.services.ai.ai_service.FINDING_EXPLANATION_PROMPT_VERSION", "2.0.0")
        provider2 = MockLLMProvider()
        service2 = AIService(provider=provider2)

        res2 = await service2.explain_issue(db=test_db_session, run_id=run.id, issue_id=issue.id)
        assert res2.cached is False
        assert res2.prompt_version == "2.0.0"
        assert provider2.call_count == 1


@pytest.mark.asyncio
async def test_explain_finding_malformed_response_raises_output_exception(
    test_db_session: AsyncSession,
    setup_test_analysis: tuple[AnalysisRun, QualityIssue],
):
    """Verify that malformed structured output raises AIProviderOutputException."""
    run, issue = setup_test_analysis
    provider = MockLLMProvider(simulate_malformed=True)
    service = AIService(provider=provider)

    # Use a fresh issue to avoid cache hit
    fresh_issue = QualityIssue(
        id=uuid.uuid4(),
        analysis_run_id=run.id,
        dataset_version_id=run.dataset_version_id,
        module="imbalance_analyzer",
        analyzer_version="1.0.0",
        category="CLASS_IMBALANCE",
        severity="HIGH",
        column_name="default",
        title="Class imbalance in default",
        description="Minority ratio 0.05",
        evidence={"ratio": 0.05},
    )
    test_db_session.add(fresh_issue)
    await test_db_session.commit()

    with pytest.raises(AIProviderOutputException) as exc:
        await service.explain_issue(db=test_db_session, run_id=run.id, issue_id=fresh_issue.id)
    assert "schema mismatch" in str(exc.value).lower() or "invalid output" in str(exc.value).lower()


@pytest.mark.asyncio
async def test_generated_python_code_remains_inert_text(
    test_db_session: AsyncSession,
    setup_test_analysis: tuple[AnalysisRun, QualityIssue],
):
    """Verify that generated Python code is never executed, imported, or run in a shell."""
    run, _ = setup_test_analysis
    provider = MockLLMProvider()
    service = AIService(provider=provider)

    plan = await service.generate_remediation_plan(
        db=test_db_session,
        run_id=run.id,
        force_regenerate=True,
    )

    # Code exists as string
    assert plan.generated_python_code is not None
    assert isinstance(plan.generated_python_code, str)
    # Clearly labeled as advisory and not executed
    assert "DO NOT EXECUTE AUTOMATICALLY" in plan.generated_python_code
    # Dataset remains completely unchanged
    assert run.dataset_version.row_count == 1000
    assert run.status == AnalysisStatus.COMPLETED.value

