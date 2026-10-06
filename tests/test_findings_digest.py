"""Unit tests for the token-bounded, deterministic findings digest generator."""

import uuid
from datetime import datetime, timezone
import pytest

from app.models.analysis import AnalysisRun, AnalysisStatus, QualityIssue
from app.models.dataset import DatasetVersion
from app.services.ai.findings_digest import FindingsDigestGenerator


def create_mock_run(issue_count: int = 5) -> tuple[AnalysisRun, list[QualityIssue]]:
    """Helper creating an in-memory AnalysisRun with specified QualityIssues."""
    version = DatasetVersion(
        id=uuid.uuid4(),
        dataset_id=uuid.uuid4(),
        version_number=1,
        file_name="housing_data.csv",
        storage_path="uploads/test.parquet",
        file_size_bytes=1024,
        sha256_hash="0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
        row_count=5000,
        column_count=12,
        raw_schema={"price": "float64"},
        created_at=datetime.now(timezone.utc),
    )

    run = AnalysisRun(
        id=uuid.uuid4(),
        dataset_version_id=version.id,
        status=AnalysisStatus.COMPLETED.value,
        target_column="price",
        problem_type="regression",
        engine_version="1.0.0",
        ml_readiness_score=78.5,
        heuristic_breakdown={
            "missing_penalty": -10.0,
            "outlier_penalty": -11.5,
        },
        summary_metrics={
            "row_count": 5000,
            "column_count": 12,
            "overall_null_percentage": 4.2,
        },
        created_at=datetime.now(timezone.utc),
    )
    run.dataset_version = version

    severities = ["CRITICAL", "HIGH", "MEDIUM", "LOW", "INFO"]
    issues = []
    for i in range(issue_count):
        sev = severities[i % len(severities)]
        issue = QualityIssue(
            id=uuid.uuid4(),
            analysis_run_id=run.id,
            dataset_version_id=version.id,
            module=f"analyzer_{i % 3}",
            analyzer_version="1.0.0",
            parameters_used={"param": i},
            category="DEFECT_CATEGORY",
            severity=sev,
            column_name=f"col_{i}",
            title=f"Quality defect in col_{i}",
            description=f"Detailed description of defect {i} with deterministic evidence.",
            evidence={"missing_percentage": 10.0 + i, "affected_rows": 50 * i},
            remediation_hint=f"Apply remediation strategy {i}",
            detected_at=datetime.now(timezone.utc),
        )
        issues.append(issue)

    return run, issues


def test_findings_digest_contains_no_raw_data():
    """Verify digest never includes raw dataframes, parquet buffers, or individual raw rows."""
    run, issues = create_mock_run(issue_count=10)
    generator = FindingsDigestGenerator()
    digest = generator.create_digest(analysis_run=run, issues=issues, max_tokens=4000)

    digest_json = digest.model_dump_json()

    # Must contain summary metadata
    assert digest.dataset_metadata["row_count"] == 5000
    assert digest.dataset_metadata["column_count"] == 12
    assert digest.target_metadata["target_column"] == "price"
    assert digest.ml_readiness_score == 78.5

    # Must NOT contain raw binary or arbitrary row lists
    assert "parquet" in digest.dataset_metadata["storage_format"]
    assert "b'PAR1'" not in digest_json
    assert "raw_dataframe" not in digest_json
    assert "row_values" not in digest_json


def test_findings_digest_severity_prioritization():
    """Verify that issues are prioritized by CRITICAL > HIGH > MEDIUM > LOW > INFO."""
    run, issues = create_mock_run(issue_count=5)
    generator = FindingsDigestGenerator()
    digest = generator.create_digest(analysis_run=run, issues=issues, max_tokens=4000)

    # First issue must be CRITICAL, second HIGH, third MEDIUM, fourth LOW, fifth INFO
    included_severities = [iss.severity for iss in digest.priority_issues]
    assert included_severities == ["CRITICAL", "HIGH", "MEDIUM", "LOW", "INFO"]


def test_findings_digest_token_bounding_and_truncation():
    """Verify that tight token budgets truncate lower-priority issues and set truncation flag."""
    run, issues = create_mock_run(issue_count=20)
    generator = FindingsDigestGenerator()

    # Set very tight budget to force truncation
    tight_budget = 400
    digest = generator.create_digest(analysis_run=run, issues=issues, max_tokens=tight_budget)

    assert digest.findings_truncated is True
    assert digest.total_issues == 20
    assert digest.included_issues < 20
    assert digest.included_issues > 0

    # Ensure critical/high issues are preserved over low/info issues
    included_severities = {iss.severity for iss in digest.priority_issues}
    assert "CRITICAL" in included_severities

    # Omitted count breakdown should record omitted issues
    total_omitted = sum(digest.omitted_by_severity.values())
    assert total_omitted == (digest.total_issues - digest.included_issues)


def test_findings_digest_evidence_compaction():
    """Verify that large nested evidence objects are pruned to preserve token budget."""
    run, issues = create_mock_run(issue_count=1)
    # Inject large list into evidence
    issues[0].evidence = {
        "huge_list": list(range(100)),
        "huge_dict": {f"key_{i}": i for i in range(50)},
    }

    generator = FindingsDigestGenerator()
    digest = generator.create_digest(analysis_run=run, issues=issues, max_tokens=2000)

    iss = digest.priority_issues[0]
    # Pruned list should have at most 11 elements (10 + truncation note)
    assert len(iss.evidence["huge_list"]) <= 11
    assert any("truncated" in str(item) for item in iss.evidence["huge_list"])
    assert "_truncated_keys_count" in iss.evidence["huge_dict"]
