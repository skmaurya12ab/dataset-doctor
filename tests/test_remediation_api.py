"""API integration tests for remediation execution, approval, provenance, and version comparison endpoints."""

import hashlib
from pathlib import Path
import uuid
from datetime import datetime, timezone
import pandas as pd
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ai import AIReport
from app.models.analysis import AnalysisRun, AnalysisStatus, QualityIssue
from app.models.dataset import Dataset, DatasetVersion
from app.services.file_storage import FileStorageService


@pytest.fixture
async def api_remediation_env(test_db_session: AsyncSession, test_storage: FileStorageService):
    """Fixture providing dataset, v1 parquet, analysis run, issues, and AI report for HTTP testing."""
    dataset = Dataset(
        id=uuid.uuid4(),
        name="API Remediation Dataset",
        owner_id=uuid.UUID("00000000-0000-0000-0000-000000000001"),
    )
    test_db_session.add(dataset)

    # v1 DataFrame with duplicates and missing value
    df1 = pd.DataFrame({
        "id": [1, 2, 2, 4],
        "feature_a": [10.0, 20.0, 20.0, None],
        "target": [0, 1, 1, 0],
    })
    v1_path = test_storage.save_canonical_parquet(df1, dataset.id, 1)
    with open(v1_path, "rb") as f:
        v1_hash = hashlib.sha256(f.read()).hexdigest()

    v1 = DatasetVersion(
        id=uuid.uuid4(),
        dataset_id=dataset.id,
        version_number=1,
        file_name="data.parquet",
        storage_path=str(v1_path.relative_to(test_storage.base_dir)),
        file_size_bytes=v1_path.stat().st_size,
        sha256_hash=v1_hash,
        row_count=len(df1),
        column_count=len(df1.columns),
        raw_schema={"columns": [{"name": c, "dtype": str(df1[c].dtype)} for c in df1.columns]},
    )
    test_db_session.add(v1)

    run = AnalysisRun(
        id=uuid.uuid4(),
        dataset_version_id=v1.id,
        status=AnalysisStatus.COMPLETED.value,
        target_column="target",
        problem_type="classification",
        ml_readiness_score=60.0,
        total_issues_count=1,
        critical_issues_count=0,
        summary_metrics={"row_count": 4, "column_count": 3, "missing_cells": 1, "duplicate_rows": 1},
        completed_at=datetime.now(timezone.utc),
    )
    test_db_session.add(run)

    issue = QualityIssue(
        id=uuid.uuid4(),
        analysis_run_id=run.id,
        dataset_version_id=v1.id,
        module="missing_analyzer",
        analyzer_version="1.0.0",
        category="MISSING_VALUES",
        severity="MEDIUM",
        column_name="feature_a",
        title="Missing feature_a",
        description="Missing values present",
        evidence={},
    )
    test_db_session.add(issue)

    report = AIReport(
        id=uuid.uuid4(),
        analysis_run_id=run.id,
        provider_model="mock-gpt",
        prompt_version="1.0.0",
        executive_summary="Plan summary",
        risk_assessment=[],
        remediation_plan=[],
        transformation_specs=[
            {
                "action": "REMOVE_DUPLICATES",
                "parameters": {"subset": ["id"]},
                "rationale": "Deduplicate",
                "source_issue_ids": [],
            },
            {
                "action": "IMPUTE",
                "column": "feature_a",
                "parameters": {"strategy": "mean"},
                "rationale": "Impute feature_a",
                "source_issue_ids": [],
            },
        ],
        ml_preparation_plan=[],
    )
    test_db_session.add(report)
    await test_db_session.commit()

    return {
        "dataset": dataset,
        "v1": v1,
        "run": run,
        "report": report,
    }


@pytest.mark.asyncio
async def test_apply_remediation_api_success(async_client: AsyncClient, api_remediation_env):
    env = api_remediation_env
    run_id = env["run"].id
    report_id = env["report"].id

    payload = {
        "ai_report_id": str(report_id),
        "approval": True,
        "approved_by": "lead_engineer",
    }

    res = await async_client.post(f"/api/v1/analyses/{run_id}/remediations/apply", json=payload)
    assert res.status_code == 201
    data = res.json()
    assert data["status"] == "COMPLETED"
    assert data["approved_by"] == "lead_engineer"
    assert data["result_dataset_version_id"] is not None
    assert len(data["transformation_provenance"]) == 2

    execution_id = data["id"]

    # Test GET /api/v1/remediations/{execution_id}
    get_res = await async_client.get(f"/api/v1/remediations/{execution_id}")
    assert get_res.status_code == 200
    assert get_res.json()["id"] == execution_id

    # Test GET /api/v1/datasets/{dataset_id}/remediations
    list_res = await async_client.get(f"/api/v1/datasets/{env['dataset'].id}/remediations")
    assert list_res.status_code == 200
    assert list_res.json()["total"] >= 1


@pytest.mark.asyncio
async def test_apply_remediation_api_requires_explicit_approval(async_client: AsyncClient, api_remediation_env):
    env = api_remediation_env
    run_id = env["run"].id

    payload = {
        "ai_report_id": str(env["report"].id),
        "approval": False,
    }

    res = await async_client.post(f"/api/v1/analyses/{run_id}/remediations/apply", json=payload)
    assert res.status_code == 422


@pytest.mark.asyncio
async def test_apply_remediation_api_nonexistent_run(async_client: AsyncClient, api_remediation_env):
    fake_run_id = uuid.uuid4()
    payload = {
        "ai_report_id": str(api_remediation_env["report"].id),
        "approval": True,
    }

    res = await async_client.post(f"/api/v1/analyses/{fake_run_id}/remediations/apply", json=payload)
    assert res.status_code == 404


@pytest.mark.asyncio
async def test_compare_versions_api(async_client: AsyncClient, api_remediation_env, test_db_session: AsyncSession):
    env = api_remediation_env
    dataset_id = env["dataset"].id
    v1_id = env["v1"].id

    # Create v2 manually to test comparison endpoint
    v2 = DatasetVersion(
        id=uuid.uuid4(),
        dataset_id=dataset_id,
        parent_version_id=v1_id,
        version_number=2,
        file_name="data_v2.parquet",
        storage_path="uploads/data_v2.parquet",
        file_size_bytes=2048,
        sha256_hash="hash2",
        row_count=3,
        column_count=3,
        raw_schema={"columns": []},
    )
    test_db_session.add(v2)

    run2 = AnalysisRun(
        id=uuid.uuid4(),
        dataset_version_id=v2.id,
        status=AnalysisStatus.COMPLETED.value,
        target_column="target",
        ml_readiness_score=90.0,
        total_issues_count=0,
        critical_issues_count=0,
        summary_metrics={"row_count": 3, "column_count": 3, "missing_cells": 0, "duplicate_rows": 0},
        completed_at=datetime.now(timezone.utc),
    )
    test_db_session.add(run2)
    await test_db_session.commit()

    res = await async_client.get(
        f"/api/v1/datasets/{dataset_id}/compare-versions?v1={v1_id}&v2={v2.id}"
    )
    assert res.status_code == 200
    data = res.json()
    assert data["dataset_id"] == str(dataset_id)
    assert data["dataset_metrics"]["rows"]["before"] == 4
    assert data["dataset_metrics"]["rows"]["after"] == 3
    assert data["dataset_metrics"]["rows"]["delta"] == -1
    assert data["heuristic"]["delta"] == 30.0
    assert data["heuristic"]["after_rating"] == "EXCELLENT"
