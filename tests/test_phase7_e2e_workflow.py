"""End-to-end checks that mock-generated plans cannot cross the approval boundary."""

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
async def test_phase7_mock_plan_cannot_be_applied(
    async_client: AsyncClient,
    test_db_session: AsyncSession,
):
    """Generate a mock plan and confirm approval cannot apply it."""

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

    # Explicit approval cannot turn mock-generated advice into verified advice.
    approved_payload = {
        "ai_report_id": ai_report_id,
        "approval": True,
        "approved_by": "lead_engineer",
    }
    apply_resp = await async_client.post(
        f"/api/v1/analyses/{run1_id}/remediations/apply",
        json=approved_payload,
    )
    assert apply_resp.status_code == 422
    assert "Only reports from a verified AI provider can be applied" in apply_resp.json()["detail"]

    executions = await test_db_session.execute(
        select(RemediationExecution).where(RemediationExecution.analysis_run_id == uuid.UUID(run1_id))
    )
    assert executions.scalars().all() == []
    versions = await test_db_session.execute(
        select(DatasetVersion).where(DatasetVersion.dataset_id == uuid.UUID(dataset_id))
    )
    assert len(versions.scalars().all()) == 1
