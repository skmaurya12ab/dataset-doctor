"""End-to-End verification test executing the full Phase 5 remediation lifecycle:

Upload v1 -> Analyze v1 -> Generate AI Plan -> Retrieve Plan -> Approve ->
Apply Remediation -> Verify v2 -> Verify v1 untouched -> Verify Provenance ->
Verify Re-analysis on v2 -> Compare v1 vs v2 -> Verify Deltas.
"""

import hashlib
import io
import uuid
import pandas as pd
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.analysis import AnalysisRun, AnalysisStatus
from app.models.dataset import DatasetVersion
from app.models.remediation import RemediationExecution, RemediationExecutionStatus


@pytest.mark.asyncio
async def test_phase5_complete_end_to_end_lifecycle(
    async_client: AsyncClient,
    test_db_session: AsyncSession,
):
    """Execute complete 13-step verification test for Phase 5."""

    # 1. Upload Version 1
    # Create CSV with duplicate rows, missing values, outliers, and useless feature
    csv_content = (
        "id,age,income,category,useless_col,target\n"
        "1,25,50000,A,1,0\n"
        "2,30,60000,B,1,1\n"
        "2,30,60000,B,1,1\n"  # Duplicate row
        "4,,75000,A,1,0\n"     # Missing age
        "5,999,80000,A,1,1\n"  # Outlier age
        "6,35,90000,B,1,0\n"
    ).encode("utf-8")

    upload_res = await async_client.post(
        "/api/v1/datasets/upload",
        files={"file": ("raw_data.csv", csv_content, "text/csv")},
        data={"name": "End-to-End E2E Dataset"},
    )
    assert upload_res.status_code == 201
    upload_data = upload_res.json()
    dataset_id = upload_data["dataset_id"]
    v1_id = upload_data["version_id"]
    assert upload_data["version_number"] == 1
    assert upload_data["row_count"] == 6
    assert upload_data["column_count"] == 6

    # Record v1 metadata for immutability verification
    v1_record = await test_db_session.get(DatasetVersion, uuid.UUID(v1_id))
    v1_initial_hash = v1_record.sha256_hash

    # 2. Run deterministic analysis on Version 1
    analyze_res = await async_client.post(
        f"/api/v1/datasets/{dataset_id}/versions/{v1_id}/analyze",
        json={"target_column": "target", "problem_type": "classification"},
    )
    assert analyze_res.status_code == 202
    run1_id = analyze_res.json()["analysis_run_id"]

    # Mark run 1 as completed in the test session with issues and metrics for AI planning
    run1 = await test_db_session.get(AnalysisRun, uuid.UUID(run1_id))
    run1.status = AnalysisStatus.COMPLETED.value
    run1.ml_readiness_score = 62.0
    run1.summary_metrics = {
        "row_count": 6,
        "column_count": 6,
        "missing_cells": 1,
        "missing_percentage": 2.77,
        "duplicate_rows": 1,
    }
    await test_db_session.commit()

    # 3. Generate AI remediation plan using MockLLMProvider
    plan_gen_res = await async_client.post(
        f"/api/v1/analyses/{run1_id}/generate-ai-plan",
    )
    assert plan_gen_res.status_code == 200
    plan_data = plan_gen_res.json()
    ai_report_id = plan_data["id"]
    assert len(plan_data["transformation_specs"]) > 0

    # 4. Retrieve the remediation plan & verify allowlisted actions
    specs = plan_data["transformation_specs"]
    for s in specs:
        assert s["action"] in {"DROP_COLUMN", "REMOVE_DUPLICATES", "IMPUTE", "CAST_TYPE", "CLIP_OUTLIERS"}

    # 5. Explicitly approve the plan
    approval_payload = {
        "ai_report_id": ai_report_id,
        "approval": True,
        "approved_by": "qa_validator",
    }

    # 6. Apply the plan deterministically
    apply_res = await async_client.post(
        f"/api/v1/analyses/{run1_id}/remediations/apply",
        json=approval_payload,
    )
    assert apply_res.status_code == 201
    apply_data = apply_res.json()
    execution_id = apply_data["id"]
    v2_id = apply_data["result_dataset_version_id"]

    assert apply_data["status"] == RemediationExecutionStatus.COMPLETED.value
    assert apply_data["approved_by"] == "qa_validator"
    assert v2_id is not None

    # 7. Verify Version 2 exists with correct parent lineage
    v2_record = await test_db_session.get(DatasetVersion, uuid.UUID(v2_id))
    assert v2_record is not None
    assert v2_record.version_number == 2
    assert str(v2_record.parent_version_id) == str(v1_id)
    assert v2_record.row_count <= 6

    # 8. Verify Version 1 is completely untouched and hash is preserved
    await test_db_session.refresh(v1_record)
    assert v1_record.sha256_hash == v1_initial_hash
    assert v1_record.version_number == 1

    # 9. Verify Version 2 has correct provenance
    assert len(apply_data["transformation_provenance"]) > 0
    for prov in apply_data["transformation_provenance"]:
        assert "applied_order" in prov
        assert "rows_changed" in prov
        assert prov["executor_version"] == "1.0.0"

    # 10. Verify Version 2 is automatically queued for re-analysis
    v2_runs_stmt = select(AnalysisRun).where(AnalysisRun.dataset_version_id == uuid.UUID(v2_id))
    v2_runs_res = await test_db_session.execute(v2_runs_stmt)
    v2_runs = v2_runs_res.scalars().all()
    assert len(v2_runs) >= 1

    # 11. Verify the new AnalysisRun is linked to Version 2 and carries target_column
    run2 = v2_runs[0]
    assert run2.dataset_version_id == uuid.UUID(v2_id)
    assert str(run2.id) != str(run1_id)
    assert run2.target_column == "target"

    # Simulate completion of run 2 with improved score and clean metrics for comparison test
    run2.status = AnalysisStatus.COMPLETED.value
    run2.ml_readiness_score = 88.0
    run2.summary_metrics = {
        "row_count": v2_record.row_count,
        "column_count": v2_record.column_count,
        "missing_cells": 0,
        "missing_percentage": 0.0,
        "duplicate_rows": 0,
    }
    await test_db_session.commit()

    # 12. Compare Version 1 vs Version 2
    comp_res = await async_client.get(
        f"/api/v1/datasets/{dataset_id}/compare-versions?v1={v1_id}&v2={v2_id}",
    )
    assert comp_res.status_code == 200
    comp_data = comp_res.json()

    # 13. Verify deterministic before/after metrics
    dataset_metrics = comp_data["dataset_metrics"]
    assert dataset_metrics["missing_cells"]["before"] == 1
    assert dataset_metrics["missing_cells"]["after"] == 0
    assert dataset_metrics["missing_cells"]["delta"] == -1

    assert dataset_metrics["duplicate_rows"]["before"] == 1
    assert dataset_metrics["duplicate_rows"]["after"] == 0
    assert dataset_metrics["duplicate_rows"]["delta"] == -1

    heuristic = comp_data["heuristic"]
    assert heuristic["before_score"] == 62.0
    assert heuristic["after_score"] == 88.0
    assert heuristic["delta"] == 26.0
    assert heuristic["before_rating"] == "MODERATE"
    assert heuristic["after_rating"] == "EXCELLENT"
    assert "not actual model performance" in heuristic["note"]
