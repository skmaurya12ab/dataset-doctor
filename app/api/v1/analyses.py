"""FastAPI routes for triggering analysis, tracking status, and querying quality issues."""

from typing import List, Optional
import uuid
from fastapi import APIRouter, Query, status

from app.api.deps import (
    AnalysisServiceDep,
    CurrentUserDep,
    DBSessionDep,
    verify_analysis_owner,
    verify_dataset_owner,
    verify_version_owner,
)
from app.core.exceptions import EntityNotFoundException
from app.core.rate_limit import rate_limiter
from app.schemas.analysis import (
    AnalysisRequest,
    AnalysisResponse,
    AnalysisRunRead,
    HeuristicBreakdownRead,
    OverviewStatsResponse,
    QualityIssueListResponse,
    QualityIssueRead,
    VisualizationDataResponse,
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
    current_user: CurrentUserDep,
) -> AnalysisResponse:
    rate_limiter.enforce(f"analyze:{current_user.id}", max_requests=10, window_seconds=60, action_name="Analysis trigger")

    # Verify ownership before queuing analysis
    await verify_dataset_owner(db=db, dataset_id=dataset_id, user_id=current_user.id)
    await verify_version_owner(db=db, version_id=version_id, user_id=current_user.id)

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
    current_user: CurrentUserDep,
) -> AnalysisRunRead:
    await verify_analysis_owner(db=db, run_id=run_id, user_id=current_user.id)

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
    current_user: CurrentUserDep,
) -> HeuristicBreakdownRead:
    await verify_analysis_owner(db=db, run_id=run_id, user_id=current_user.id)

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
    current_user: CurrentUserDep,
    severity: Optional[str] = Query(default=None, description="Filter by severity: CRITICAL, HIGH, MEDIUM, LOW, INFO"),
    module: Optional[str] = Query(default=None, description="Filter by module: schema_analyzer, missing_analyzer, etc."),
    column: Optional[str] = Query(default=None, description="Filter by column name"),
    limit: int = Query(default=50, ge=1, le=200, description="Maximum issues per page"),
    offset: int = Query(default=0, ge=0, description="Offset for pagination"),
) -> QualityIssueListResponse:
    await verify_analysis_owner(db=db, run_id=run_id, user_id=current_user.id)

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


@router.get(
    "/datasets/{dataset_id}/versions/{version_id}/analyses",
    response_model=List[AnalysisRunRead],
    status_code=status.HTTP_200_OK,
    summary="List analysis runs for a dataset version",
    description="Retrieve all historical analysis runs for a specific dataset version.",
)
async def list_version_analyses_endpoint(
    dataset_id: uuid.UUID,
    version_id: uuid.UUID,
    db: DBSessionDep,
    analysis_service: AnalysisServiceDep,
    current_user: CurrentUserDep,
) -> List[AnalysisRunRead]:
    await verify_dataset_owner(db=db, dataset_id=dataset_id, user_id=current_user.id)
    await verify_version_owner(db=db, version_id=version_id, user_id=current_user.id)

    runs = await analysis_service.list_analyses_for_version(db=db, version_id=version_id)
    return [AnalysisRunRead.model_validate(r) for r in runs]


@router.get(
    "/analyses/{run_id}/visualizations",
    response_model=VisualizationDataResponse,
    status_code=status.HTTP_200_OK,
    summary="Get server-aggregated analytical visualization series",
    description="Retrieve bounded, pre-aggregated plotting data for missingness, distributions, cardinality, outliers, and correlations.",
)
async def get_analysis_visualizations_endpoint(
    run_id: uuid.UUID,
    db: DBSessionDep,
    analysis_service: AnalysisServiceDep,
    current_user: CurrentUserDep,
) -> VisualizationDataResponse:
    await verify_analysis_owner(db=db, run_id=run_id, user_id=current_user.id)

    data = await analysis_service.get_visualization_data(db=db, run_id=run_id)
    return VisualizationDataResponse.model_validate(data)


@router.get(
    "/overview/stats",
    response_model=OverviewStatsResponse,
    status_code=status.HTTP_200_OK,
    summary="Get overview dashboard system statistics",
    description="Retrieve high-level metrics on datasets, active analysis runs, recent remediations, and issue counts.",
)
async def get_overview_stats_endpoint(
    db: DBSessionDep,
    analysis_service: AnalysisServiceDep,
    current_user: CurrentUserDep,
) -> OverviewStatsResponse:
    stats = await analysis_service.get_overview_stats(db=db, user_id=current_user.id)
    return OverviewStatsResponse.model_validate(stats)
