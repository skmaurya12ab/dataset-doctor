"""FastAPI routes for triggering analysis, tracking status, and querying quality issues."""

from typing import Optional
import uuid
from fastapi import APIRouter, Query, status

from app.api.deps import AnalysisServiceDep, DBSessionDep
from app.core.exceptions import EntityNotFoundException
from app.schemas.analysis import (
    AnalysisRequest,
    AnalysisResponse,
    AnalysisRunRead,
    HeuristicBreakdownRead,
    QualityIssueListResponse,
    QualityIssueRead,
)

router = APIRouter(tags=["Analysis"])


@router.post(
    "/datasets/{dataset_id}/versions/{version_id}/analyze",
    response_model=AnalysisResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Trigger asynchronous deterministic analysis",
    description="Queue a dataset version for deterministic profiling across the 5 Phase 2 analyzers.",
)
async def trigger_analysis_endpoint(
    dataset_id: uuid.UUID,
    version_id: uuid.UUID,
    payload: AnalysisRequest,
    db: DBSessionDep,
    analysis_service: AnalysisServiceDep,
) -> AnalysisResponse:
    run = await analysis_service.trigger_analysis(
        db=db,
        dataset_id=dataset_id,
        version_id=version_id,
        request_data=payload,
    )
    return AnalysisResponse(
        analysis_run_id=run.id,
        status=run.status,
    )


@router.get(
    "/analyses/{run_id}",
    response_model=AnalysisRunRead,
    status_code=status.HTTP_200_OK,
    summary="Get analysis run details and status",
    description="Retrieve the current execution state, timing, summary metrics, and version metadata of an analysis run.",
)
async def get_analysis_status_endpoint(
    run_id: uuid.UUID,
    db: DBSessionDep,
    analysis_service: AnalysisServiceDep,
) -> AnalysisRunRead:
    run = await analysis_service.get_analysis(db=db, run_id=run_id)
    if not run:
        raise EntityNotFoundException("AnalysisRun", str(run_id))
    return AnalysisRunRead.model_validate(run)


@router.get(
    "/analyses/{run_id}/heuristic",
    response_model=HeuristicBreakdownRead,
    status_code=status.HTTP_200_OK,
    summary="Get transparent ML Readiness Heuristic breakdown",
    description="Retrieve the complete explainable itemized penalty breakdown and rating for an analysis run.",
)
async def get_analysis_heuristic_endpoint(
    run_id: uuid.UUID,
    db: DBSessionDep,
    analysis_service: AnalysisServiceDep,
) -> HeuristicBreakdownRead:
    run = await analysis_service.get_analysis(db=db, run_id=run_id)
    if not run:
        raise EntityNotFoundException("AnalysisRun", str(run_id))
    if not run.heuristic_breakdown:
        raise EntityNotFoundException("HeuristicBreakdown", f"No heuristic breakdown available for analysis run {run_id}")
    return HeuristicBreakdownRead.model_validate(run.heuristic_breakdown)


@router.get(
    "/analyses/{run_id}/issues",
    response_model=QualityIssueListResponse,
    status_code=status.HTTP_200_OK,
    summary="Get paginated quality issues for an analysis run",
    description="Query detected data quality defects with optional filtering on severity, module, and column name.",
)
async def get_analysis_issues_endpoint(
    run_id: uuid.UUID,
    db: DBSessionDep,
    analysis_service: AnalysisServiceDep,
    severity: Optional[str] = Query(default=None, description="Filter by severity: CRITICAL, HIGH, MEDIUM, LOW, INFO"),
    module: Optional[str] = Query(default=None, description="Filter by module: schema_analyzer, missing_analyzer, etc."),
    column: Optional[str] = Query(default=None, description="Filter by column name"),
    limit: int = Query(default=50, ge=1, le=200, description="Maximum issues per page"),
    offset: int = Query(default=0, ge=0, description="Offset for pagination"),
) -> QualityIssueListResponse:
    # Verify run exists first
    run = await analysis_service.get_analysis(db=db, run_id=run_id)
    if not run:
        raise EntityNotFoundException("AnalysisRun", str(run_id))

    issues, total = await analysis_service.get_analysis_issues(
        db=db,
        run_id=run_id,
        severity=severity,
        module=module,
        column_name=column,
        limit=limit,
        offset=offset,
    )

    issue_items = [QualityIssueRead.model_validate(iss) for iss in issues]
    return QualityIssueListResponse(
        total=total,
        limit=limit,
        offset=offset,
        items=issue_items,
    )
