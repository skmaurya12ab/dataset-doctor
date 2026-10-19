"""End-to-end checks that mock-generated advice stays non-applicable."""

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
async def test_phase5_mock_report_cannot_be_applied(
    async_client: AsyncClient,
    test_db_session: AsyncSession,
):
    """Generate a mock plan and confirm it cannot create an execution or version."""

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

    assert plan_data["provider"] == "mock-provider"

    # Explicit approval cannot turn mock-generated advice into verified advice.
    approval_payload = {
        "ai_report_id": ai_report_id,
        "approval": True,
        "approved_by": "qa_validator",
    }

    # Application must fail closed before any remediation side effect.
    apply_res = await async_client.post(
        f"/api/v1/analyses/{run1_id}/remediations/apply",
        json=approval_payload,
    )
    assert apply_res.status_code == 422
    assert "Only reports from a verified AI provider can be applied" in apply_res.json()["detail"]

    executions = await test_db_session.execute(
        select(RemediationExecution).where(RemediationExecution.analysis_run_id == uuid.UUID(run1_id))
    )
    assert executions.scalars().all() == []
    versions = await test_db_session.execute(
        select(DatasetVersion).where(DatasetVersion.dataset_id == v1_record.dataset_id)
    )
    assert len(versions.scalars().all()) == 1
