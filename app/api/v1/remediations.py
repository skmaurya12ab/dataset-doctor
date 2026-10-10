"""FastAPI routes for deterministic remediation execution, approval, and version comparison."""

from typing import List
import uuid
from fastapi import APIRouter, Query, status

from app.api.deps import (
    ComparisonServiceDep,
    CurrentUserDep,
    DBSessionDep,
    RemediationServiceDep,
    verify_analysis_owner,
    verify_dataset_owner,
    verify_remediation_owner,
)
from app.core.rate_limit import rate_limiter
from app.schemas.remediation import (
    RemediationApplyRequest,
    RemediationExecutionRead,
    RemediationListResponse,
    VersionComparisonResponse,
)

router = APIRouter(tags=["Remediation & Version Comparison"])


@router.post(
    "/analyses/{run_id}/remediations/apply",
    response_model=RemediationExecutionRead,
    status_code=status.HTTP_201_CREATED,
    summary="Approve and deterministically apply an AI remediation plan",
    description=(
        "Requires explicit human approval (approval=True). Validates all TransformationSpecs, "
        "executes transformations deterministically in memory, creates a new immutable DatasetVersion, "
        "and automatically queues fresh deterministic re-analysis on the new version."
    ),
)
async def apply_remediation_endpoint(
    run_id: uuid.UUID,
    payload: RemediationApplyRequest,
    db: DBSessionDep,
    remediation_service: RemediationServiceDep,
    current_user: CurrentUserDep,
) -> RemediationExecutionRead:
    """Explicitly approve and execute a deterministic remediation plan."""
    rate_limiter.enforce(f"remediation:{current_user.id}", max_requests=10, window_seconds=60, action_name="Remediation application")
    await verify_analysis_owner(db=db, run_id=run_id, user_id=current_user.id)

    # Derive human approval identity from verified session if not explicitly specified
    if not payload.approved_by:
        payload.approved_by = current_user.email

    return await remediation_service.apply_remediation(
        db=db,
        run_id=run_id,
        request=payload,
    )


@router.get(
    "/remediations/{execution_id}",
    response_model=RemediationExecutionRead,
    status_code=status.HTTP_200_OK,
    summary="Get remediation execution details, provenance, and status",
    description="Retrieve an auditable record of an approved remediation execution.",
)
async def get_remediation_execution_endpoint(
    execution_id: uuid.UUID,
    db: DBSessionDep,
    remediation_service: RemediationServiceDep,
    current_user: CurrentUserDep,
) -> RemediationExecutionRead:
    """Retrieve a specific remediation execution record."""
    await verify_remediation_owner(db=db, execution_id=execution_id, user_id=current_user.id)

    return await remediation_service.get_execution(
        db=db,
        execution_id=execution_id,
    )


@router.get(
    "/datasets/{dataset_id}/remediations",
    response_model=RemediationListResponse,
    status_code=status.HTTP_200_OK,
    summary="List remediation executions for a dataset",
    description="Retrieve all historical remediation executions across versions of a specific dataset.",
)
async def list_dataset_remediations_endpoint(
    dataset_id: uuid.UUID,
    db: DBSessionDep,
    remediation_service: RemediationServiceDep,
    current_user: CurrentUserDep,
) -> RemediationListResponse:
    """List all remediation executions for a dataset."""
    await verify_dataset_owner(db=db, dataset_id=dataset_id, user_id=current_user.id)

    items = await remediation_service.list_dataset_remediations(
        db=db,
        dataset_id=dataset_id,
    )
    return RemediationListResponse(items=items, total=len(items))


@router.get(
    "/datasets/{dataset_id}/compare-versions",
    response_model=VersionComparisonResponse,
    status_code=status.HTTP_200_OK,
    summary="Compare two dataset versions and their deterministic findings",
    description=(
        "Computes exact deltas for dataset summary metrics, categorizes defect lifecycle "
        "(RESOLVED, CHANGED, UNCHANGED, NEW) using deterministic semantic issue keys, "
        "and compares ML readiness heuristic scores without claiming model accuracy gains."
    ),
)
async def compare_dataset_versions_endpoint(
    dataset_id: uuid.UUID,
    db: DBSessionDep,
    comparison_service: ComparisonServiceDep,
    current_user: CurrentUserDep,
    v1: uuid.UUID = Query(..., description="Source dataset version UUID"),
    v2: uuid.UUID = Query(..., description="Target / remediated dataset version UUID"),
) -> VersionComparisonResponse:
    """Compare two versions of a dataset."""
    await verify_dataset_owner(db=db, dataset_id=dataset_id, user_id=current_user.id)

    return await comparison_service.compare_versions(
        db=db,
        dataset_id=dataset_id,
        v1_id=v1,
        v2_id=v2,
    )
