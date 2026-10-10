"""FastAPI routes for grounded AI explanations and advisory remediation planning."""

from typing import Optional
import uuid
from fastapi import APIRouter, Body, Query, status

from app.api.deps import AIServiceDep, CurrentUserDep, DBSessionDep, verify_analysis_owner
from app.core.rate_limit import rate_limiter
from app.schemas.ai import (
    AIReportResponse,
    FindingExplanationResponse,
    GenerateAIPlanRequest,
)

router = APIRouter(tags=["AI Interpretation"])


@router.post(
    "/analyses/{run_id}/issues/{issue_id}/explain",
    response_model=FindingExplanationResponse,
    status_code=status.HTTP_200_OK,
    summary="Generate or retrieve grounded explanation for a QualityIssue",
    description=(
        "Interpret and contextualize an individual deterministic defect without calculating "
        "new statistics or inventing numbers. Results are cached per issue, model, and prompt version."
    ),
)
async def explain_finding_endpoint(
    run_id: uuid.UUID,
    issue_id: uuid.UUID,
    db: DBSessionDep,
    ai_service: AIServiceDep,
    current_user: CurrentUserDep,
) -> FindingExplanationResponse:
    """Generate or retrieve cached grounded explanation for an individual finding."""
    rate_limiter.enforce(f"ai_explain:{current_user.id}", max_requests=20, window_seconds=60, action_name="AI explanation")
    await verify_analysis_owner(db=db, run_id=run_id, user_id=current_user.id)

    return await ai_service.explain_issue(
        db=db,
        run_id=run_id,
        issue_id=issue_id,
    )


@router.post(
    "/analyses/{run_id}/generate-ai-plan",
    response_model=AIReportResponse,
    status_code=status.HTTP_200_OK,
    summary="Generate advisory AI remediation plan and risk assessment",
    description=(
        "Synthesize a prioritized remediation plan and allowlisted transformation proposals "
        "grounded in the deterministic findings digest. Advisory only; does not modify data."
    ),
)
async def generate_ai_plan_endpoint(
    run_id: uuid.UUID,
    db: DBSessionDep,
    ai_service: AIServiceDep,
    current_user: CurrentUserDep,
    payload: Optional[GenerateAIPlanRequest] = Body(default=None),
    force_regenerate: bool = Query(
        default=False,
        description="If True, bypasses existing cached report and synthesizes a new plan",
    ),
) -> AIReportResponse:
    """Generate or retrieve advisory remediation plan for a completed analysis run."""
    rate_limiter.enforce(f"ai_plan:{current_user.id}", max_requests=10, window_seconds=60, action_name="AI remediation plan")
    await verify_analysis_owner(db=db, run_id=run_id, user_id=current_user.id)

    force = force_regenerate or (payload.force_regenerate if payload else False)
    return await ai_service.generate_remediation_plan(
        db=db,
        run_id=run_id,
        force_regenerate=force,
    )


@router.get(
    "/analyses/{run_id}/ai-plan",
    response_model=AIReportResponse,
    status_code=status.HTTP_200_OK,
    summary="Get latest stored AI remediation plan",
    description="Retrieve the most recent advisory AI remediation plan synthesized for this analysis run.",
)
async def get_ai_plan_endpoint(
    run_id: uuid.UUID,
    db: DBSessionDep,
    ai_service: AIServiceDep,
    current_user: CurrentUserDep,
) -> AIReportResponse:
    """Retrieve the latest stored AI remediation plan."""
    await verify_analysis_owner(db=db, run_id=run_id, user_id=current_user.id)

    return await ai_service.get_latest_remediation_plan(
        db=db,
        run_id=run_id,
    )
