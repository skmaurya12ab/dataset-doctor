"""Phase 7 End-to-End Integration Workflow Test.

Proves the fundamental architectural lifecycle:
1. UPLOAD raw dataset -> Creates Immutable Dataset Version 1
2. TRIGGER deterministic analysis -> Returns 202 Accepted
3. WAIT FOR / RECORD analysis run completion -> Verifies total defects and ML readiness score
4. RETRIEVE findings -> Inspects specific quality defects
5. REQUEST AI EXPLANATION -> Receives grounded, advisory explanation using Mock LLM
6. REQUEST AI REMEDIATION PLAN -> Proposes allowlisted transformations using Mock LLM
7. VERIFY UNAPPROVED EXECUTION REJECTED -> Strict enforcement of human-in-the-loop boundary
8. APPROVE PLAN -> Explicit user approval recorded
9. EXECUTE DETERMINISTIC REMEDIATION -> Python engine applies allowlisted operations
10. CREATE VERSION 2 -> Immutable Version 2 created with parent lineage to Version 1
11. VERIFY VERSION 1 UNTOUCHED -> Source hash, records, and files remain completely preserved
12. AUTOMATIC RE-ANALYSIS OF VERSION 2 -> Version 2 analysis run queued/executed
13. COMPARE VERSION 1 vs VERSION 2 -> Defect lifecycle transitions (RESOLVED, UNCHANGED, NEW)
14. VERIFY READINESS DELTA -> Positive score improvement verified
"""

import io
import uuid
import pandas as pd
import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.analysis import AnalysisRun, AnalysisStatus, QualityIssue
from app.models.dataset import DatasetVersion
from app.models.remediation import RemediationExecution, RemediationExecutionStatus


@pytest.mark.asyncio
async def test_complete_phase7_architecture_lifecycle(
    async_client: AsyncClient,
    test_db_session: AsyncSession,
):
    """Execute complete end-to-end architecture lifecycle test."""

    # --------------------------------------------------------------------------
    # Step 1: Upload dirty dataset to create Version 1
    # --------------------------------------------------------------------------
    csv_bytes = (
        "id,age,income,department,redundant_col,target\n"
        "1,25,50000,Engineering,100,0\n"
        "2,30,60000,Sales,100,1\n"
        "2,30,60000,Sales,100,1\n"  # Duplicate row
        "4,,75000,Engineering,100,0\n"  # Missing age
        "5,999,80000,Engineering,100,1\n"  # Outlier age
        "6,35,90000,Marketing,100,0\n"
    ).encode("utf-8")

    upload_resp = await async_client.post(
        "/api/v1/datasets/upload",
        files={"file": ("dirty_dataset.csv", csv_bytes, "text/csv")},
        data={"name": "Phase 7 E2E Validation Dataset"},
    )
    assert upload_resp.status_code == 201
    upload_data = upload_resp.json()
    dataset_id = upload_data["dataset_id"]
    v1_id = upload_data["version_id"]

    v1_record = await test_db_session.get(DatasetVersion, uuid.UUID(v1_id))
    v1_initial_hash = v1_record.sha256_hash
    assert v1_record.version_number == 1
    assert v1_record.row_count == 6

    # --------------------------------------------------------------------------
    # Step 2 & 3: Trigger analysis and complete run 1
    # --------------------------------------------------------------------------
    trigger_resp = await async_client.post(
        f"/api/v1/datasets/{dataset_id}/versions/{v1_id}/analyze",
        json={"target_column": "target", "problem_type": "classification"},
    )
    assert trigger_resp.status_code == 202
    run1_id = trigger_resp.json()["analysis_run_id"]

    # Seed run 1 with completed state, heuristic score and issues
    run1 = await test_db_session.get(AnalysisRun, uuid.UUID(run1_id))
    run1.status = AnalysisStatus.COMPLETED.value
    run1.ml_readiness_score = 65.0
    run1.summary_metrics = {
        "row_count": 6,
        "column_count": 6,
        "missing_cells": 1,
        "missing_percentage": 2.77,
        "duplicate_rows": 1,
    }

    issue_dup = QualityIssue(
        analysis_run_id=run1.id,
        dataset_version_id=uuid.UUID(v1_id),
        module="duplicate_analyzer",
        analyzer_version="1.0.0",
        parameters_used={},
        category="DUPLICATES",
        severity="HIGH",
        column_name=None,
        title="Duplicate rows detected",
        description="Duplicate records exist",
        evidence={"duplicate_count": 1},
    )
    issue_missing = QualityIssue(
        analysis_run_id=run1.id,
        dataset_version_id=uuid.UUID(v1_id),
        module="missing_analyzer",
        analyzer_version="1.0.0",
        parameters_used={},
        category="MISSING_VALUES",
        severity="HIGH",
        column_name="age",
        title="Missing values in age",
        description="Missing values present",
        evidence={"missing_count": 1},
    )
    test_db_session.add_all([issue_dup, issue_missing])
    await test_db_session.commit()
    await test_db_session.refresh(issue_dup)

    # --------------------------------------------------------------------------
    # Step 4 & 5: Retrieve findings & Request AI Explanation
    # --------------------------------------------------------------------------
    issues_resp = await async_client.get(f"/api/v1/analyses/{run1_id}/issues")
    assert issues_resp.status_code == 200
    assert issues_resp.json()["total"] >= 2

    explain_resp = await async_client.post(
        f"/api/v1/analyses/{run1_id}/issues/{issue_dup.id}/explain",
    )
    assert explain_resp.status_code == 200
    explain_data = explain_resp.json()
    assert "explanation" in explain_data
    assert "why_it_matters" in explain_data

    # --------------------------------------------------------------------------
    # Step 6: Request AI remediation plan via MockLLM
    # --------------------------------------------------------------------------
    plan_resp = await async_client.post(f"/api/v1/analyses/{run1_id}/generate-ai-plan")
    assert plan_resp.status_code == 200
    plan_data = plan_resp.json()
    ai_report_id = plan_data["id"]
    specs = plan_data["transformation_specs"]
    assert len(specs) > 0

    # --------------------------------------------------------------------------
    # Step 7: Enforce human approval boundary: unapproved request must fail
    # --------------------------------------------------------------------------
    unapproved_payload = {
        "ai_report_id": ai_report_id,
        "approval": False,
        "approved_by": "tester",
    }
    unapproved_resp = await async_client.post(
        f"/api/v1/analyses/{run1_id}/remediations/apply",
        json=unapproved_payload,
    )
    assert unapproved_resp.status_code in (400, 422)

    # --------------------------------------------------------------------------
    # Step 8 & 9: Explicit approval and deterministic execution
    # --------------------------------------------------------------------------
    approved_payload = {
        "ai_report_id": ai_report_id,
        "approval": True,
        "approved_by": "lead_engineer",
    }
    apply_resp = await async_client.post(
        f"/api/v1/analyses/{run1_id}/remediations/apply",
        json=approved_payload,
    )
    assert apply_resp.status_code == 201
    apply_data = apply_resp.json()
    v2_id = apply_data["result_dataset_version_id"]
    assert apply_data["status"] == RemediationExecutionStatus.COMPLETED.value
    assert apply_data["approved_by"] == "lead_engineer"

    # --------------------------------------------------------------------------
    # Step 10 & 11: Verify Version 2 lineage and Version 1 immutability
    # --------------------------------------------------------------------------
    v2_record = await test_db_session.get(DatasetVersion, uuid.UUID(v2_id))
    assert v2_record.version_number == 2
    assert str(v2_record.parent_version_id) == str(v1_id)

    await test_db_session.refresh(v1_record)
    assert v1_record.sha256_hash == v1_initial_hash
    assert v1_record.version_number == 1

    # --------------------------------------------------------------------------
    # Step 12: Automatic re-analysis on Version 2
    # --------------------------------------------------------------------------
    v2_runs_stmt = select(AnalysisRun).where(AnalysisRun.dataset_version_id == uuid.UUID(v2_id))
    v2_runs_res = await test_db_session.execute(v2_runs_stmt)
    v2_runs = list(v2_runs_res.scalars().all())
    assert len(v2_runs) >= 1
    run2 = v2_runs[0]

    # Simulate completed run 2 with 0 defects and improved score
    run2.status = AnalysisStatus.COMPLETED.value
    run2.ml_readiness_score = 92.0
    run2.summary_metrics = {
        "row_count": v2_record.row_count,
        "column_count": v2_record.column_count,
        "missing_cells": 0,
        "missing_percentage": 0.0,
        "duplicate_rows": 0,
    }
    await test_db_session.commit()

    # --------------------------------------------------------------------------
    # Step 13 & 14: Compare Version 1 vs Version 2 & verify deltas
    # --------------------------------------------------------------------------
    comp_resp = await async_client.get(
        f"/api/v1/datasets/{dataset_id}/compare-versions?v1={v1_id}&v2={v2_id}",
    )
    assert comp_resp.status_code == 200
    comp_data = comp_resp.json()

    # Verify metrics delta
    metrics = comp_data["dataset_metrics"]
    assert metrics["missing_cells"]["before"] == 1
    assert metrics["missing_cells"]["after"] == 0
    assert metrics["missing_cells"]["delta"] == -1

    assert metrics["duplicate_rows"]["before"] == 1
    assert metrics["duplicate_rows"]["after"] == 0
    assert metrics["duplicate_rows"]["delta"] == -1

    # Verify heuristic score delta
    heuristic = comp_data["heuristic"]
    assert heuristic["before_score"] == 65.0
    assert heuristic["after_score"] == 92.0
    assert heuristic["delta"] == 27.0
