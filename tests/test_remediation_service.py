"""Unit and integration tests for RemediationService covering lifecycle, immutability, provenance, and idempotency."""

import hashlib
from pathlib import Path
import uuid
from datetime import datetime, timezone
import pandas as pd
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import InvalidTransformationException, ValidationException
from app.models.ai import AIReport
from app.models.analysis import AnalysisRun, AnalysisStatus
from app.models.dataset import Dataset, DatasetVersion
from app.models.remediation import RemediationExecution, RemediationExecutionStatus
from app.schemas.remediation import RemediationApplyRequest
from app.services.file_storage import FileStorageService
from app.services.remediation_service import RemediationService


@pytest.fixture
async def setup_remediation_environment(test_db_session: AsyncSession, test_storage: FileStorageService):
    """Set up dataset, v1 Parquet file, AnalysisRun, and AIReport with allowlisted specs."""
    dataset = Dataset(id=uuid.uuid4(), name="Remediation Test Dataset")
    test_db_session.add(dataset)

    # Create physical Parquet file for v1
    v1_df = pd.DataFrame({
        "id": [1, 2, 2, 4, 5],
        "age": [20.0, 30.0, 30.0, None, 50.0],
        "category": ["A", "B", "B", "A", "A"],
        "junk": [9, 9, 9, 9, 9],
        "target": [0, 1, 1, 0, 1],
    })
    v1_path = test_storage.save_canonical_parquet(v1_df, dataset.id, 1)
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
        row_count=len(v1_df),
        column_count=len(v1_df.columns),
        raw_schema={"columns": [{"name": c, "dtype": str(v1_df[c].dtype)} for c in v1_df.columns]},
    )
    test_db_session.add(v1)

    run = AnalysisRun(
        id=uuid.uuid4(),
        dataset_version_id=v1.id,
        status=AnalysisStatus.COMPLETED.value,
        target_column="target",
        problem_type="classification",
        summary_metrics={"row_count": 5, "column_count": 5},
    )
    test_db_session.add(run)

    report = AIReport(
        id=uuid.uuid4(),
        analysis_run_id=run.id,
        provider_model="mock-gpt",
        prompt_version="1.0.0",
        executive_summary="Summary",
        risk_assessment=[],
        remediation_plan=[],
        transformation_specs=[
            {
                "action": "REMOVE_DUPLICATES",
                "parameters": {"subset": ["id"]},
                "rationale": "Deduplicate by id",
                "source_issue_ids": [],
            },
            {
                "action": "IMPUTE",
                "column": "age",
                "parameters": {"strategy": "mean"},
                "rationale": "Impute missing age",
                "source_issue_ids": [],
            },
            {
                "action": "DROP_COLUMN",
                "column": "junk",
                "rationale": "Drop junk column",
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
        "v1_path": v1_path,
        "v1_hash": v1_hash,
        "storage": test_storage,
    }


@pytest.mark.asyncio
async def test_apply_remediation_success(test_db_session: AsyncSession, setup_remediation_environment):
    env = setup_remediation_environment
    service = RemediationService(storage=env["storage"])

    req = RemediationApplyRequest(
        ai_report_id=env["report"].id,
        approval=True,
        approved_by="test_reviewer",
    )

    execution = await service.apply_remediation(test_db_session, env["run"].id, req)

    assert execution.status == RemediationExecutionStatus.COMPLETED.value
    assert execution.result_dataset_version_id is not None
    assert execution.approved_by == "test_reviewer"
    assert len(execution.transformation_provenance) == 3

    # Verify v2 was created in database
    v2 = await test_db_session.get(DatasetVersion, execution.result_dataset_version_id)
    assert v2 is not None
    assert v2.version_number == 2
    assert v2.parent_version_id == env["v1"].id
    assert v2.row_count == 4  # 1 duplicate row removed
    assert v2.column_count == 4  # 'junk' column dropped

    # Verify Source Version (v1) was completely untouched!
    with open(env["v1_path"], "rb") as f:
        current_v1_hash = hashlib.sha256(f.read()).hexdigest()
    assert current_v1_hash == env["v1_hash"]

    # Verify v2 has independent storage and distinct hash
    assert v2.sha256_hash != env["v1_hash"]
    v2_full_path = env["storage"].base_dir / v2.storage_path
    assert v2_full_path.exists()
    assert v2_full_path != env["v1_path"]


@pytest.mark.asyncio
async def test_apply_remediation_requires_approval(test_db_session: AsyncSession, setup_remediation_environment):
    env = setup_remediation_environment
    service = RemediationService(storage=env["storage"])

    # Schema rejects approval=False upfront
    with pytest.raises(Exception):
        RemediationApplyRequest(
            ai_report_id=env["report"].id,
            approval=False,
        )


@pytest.mark.asyncio
async def test_apply_remediation_idempotency(test_db_session: AsyncSession, setup_remediation_environment):
    env = setup_remediation_environment
    service = RemediationService(storage=env["storage"])

    req = RemediationApplyRequest(
        ai_report_id=env["report"].id,
        approval=True,
    )

    # First execution
    exec1 = await service.apply_remediation(test_db_session, env["run"].id, req)
    assert exec1.status == RemediationExecutionStatus.COMPLETED.value
    v2_id = exec1.result_dataset_version_id

    # Second execution with same parameters -> should return existing completed execution without creating v3
    exec2 = await service.apply_remediation(test_db_session, env["run"].id, req)
    assert exec2.id == exec1.id
    assert exec2.result_dataset_version_id == v2_id


@pytest.mark.asyncio
async def test_apply_remediation_target_protection(test_db_session: AsyncSession, setup_remediation_environment):
    env = setup_remediation_environment
    # Add a report trying to drop target
    bad_report = AIReport(
        id=uuid.uuid4(),
        analysis_run_id=env["run"].id,
        provider_model="mock-gpt",
        prompt_version="1.0.0",
        executive_summary="Malicious drop",
        risk_assessment=[],
        remediation_plan=[],
        transformation_specs=[
            {
                "action": "DROP_COLUMN",
                "column": "target",
                "rationale": "Drop target",
            }
        ],
        ml_preparation_plan=[],
    )
    test_db_session.add(bad_report)
    await test_db_session.commit()

    service = RemediationService(storage=env["storage"])
    req = RemediationApplyRequest(ai_report_id=bad_report.id, approval=True)

    with pytest.raises(InvalidTransformationException, match="Dropping the modeling target 'target' is prohibited"):
        await service.apply_remediation(test_db_session, env["run"].id, req)


@pytest.mark.asyncio
async def test_remediation_chaining_v1_to_v2_to_v3(test_db_session: AsyncSession, setup_remediation_environment):
    env = setup_remediation_environment
    service = RemediationService(storage=env["storage"])

    # 1. Apply remediation from v1 -> v2
    req1 = RemediationApplyRequest(ai_report_id=env["report"].id, approval=True)
    exec1 = await service.apply_remediation(test_db_session, env["run"].id, req1)
    v2_id = exec1.result_dataset_version_id
    v2 = await test_db_session.get(DatasetVersion, v2_id)
    assert v2.version_number == 2

    # 2. Simulate analysis run on v2
    run2 = AnalysisRun(
        id=uuid.uuid4(),
        dataset_version_id=v2.id,
        status=AnalysisStatus.COMPLETED.value,
        target_column="target",
        problem_type="classification",
        summary_metrics={"row_count": v2.row_count, "column_count": v2.column_count},
    )
    test_db_session.add(run2)

    # 3. Simulate AI report on run2
    report2 = AIReport(
        id=uuid.uuid4(),
        analysis_run_id=run2.id,
        provider_model="mock-gpt",
        prompt_version="1.0.0",
        executive_summary="Second remediation",
        risk_assessment=[],
        remediation_plan=[],
        transformation_specs=[
            {
                "action": "CAST_TYPE",
                "column": "age",
                "parameters": {"target_type": "int64"},
                "rationale": "Cast age to int64",
            }
        ],
        ml_preparation_plan=[],
    )
    test_db_session.add(report2)
    await test_db_session.commit()

    # 4. Apply second remediation from v2 -> v3
    req2 = RemediationApplyRequest(ai_report_id=report2.id, approval=True)
    exec2 = await service.apply_remediation(test_db_session, run2.id, req2)
    v3_id = exec2.result_dataset_version_id
    v3 = await test_db_session.get(DatasetVersion, v3_id)

    assert v3 is not None
    assert v3.version_number == 3
    assert v3.parent_version_id == v2.id
    assert v2.parent_version_id == env["v1"].id


@pytest.mark.asyncio
async def test_remediation_triggers_reanalysis_on_v2(test_db_session: AsyncSession, setup_remediation_environment):
    """Verify that re-analysis is created for v2, references v2.id, and does not reuse v1 findings."""
    env = setup_remediation_environment
    service = RemediationService(storage=env["storage"])

    req = RemediationApplyRequest(ai_report_id=env["report"].id, approval=True)
    execution = await service.apply_remediation(test_db_session, env["run"].id, req)

    v2_id = execution.result_dataset_version_id
    assert v2_id is not None

    # Query all analysis runs
    stmt = select(AnalysisRun).where(AnalysisRun.dataset_version_id == v2_id)
    res = await test_db_session.execute(stmt)
    v2_runs = res.scalars().all()

    assert len(v2_runs) >= 1
    new_run = v2_runs[0]
    assert new_run.dataset_version_id == v2_id
    assert new_run.dataset_version_id != env["v1"].id
    assert new_run.id != env["run"].id
    assert new_run.target_column == env["run"].target_column
    assert new_run.problem_type == env["run"].problem_type
    assert new_run.total_issues_count == 0  # fresh run, zero stale findings

