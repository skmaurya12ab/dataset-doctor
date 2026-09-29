"""Tests for BaseAnalyzer abstraction, provenance tracking, and ML Readiness Heuristic."""

from typing import Any, Dict
from app.engine.base import (
    AnalysisContext,
    BaseAnalyzer,
    ModuleResult,
    QualityIssue,
    Severity,
)
from app.engine.pipeline import AnalysisPipeline
from app.engine.scoring import MLReadinessHeuristicScorer


class MockNullAnalyzer(BaseAnalyzer):
    """Deterministic stub analyzer for contract testing."""

    @property
    def name(self) -> str:
        return "mock_null_analyzer"

    @property
    def version(self) -> str:
        return "1.0.0"

    def analyze(self, ctx: AnalysisContext) -> ModuleResult:
        # Detect dummy issue
        issues = [
            QualityIssue(
                module=self.name,
                analyzer_version=self.version,
                category="missing_values",
                severity=Severity.HIGH,
                title="Excessive Null Rate in Age",
                description="Column 'age' has 45% missing values.",
                column_name="age",
                parameters_used={"null_threshold": 0.40},
                evidence={"null_percentage": 45.0, "total_nulls": 450},
                remediation_hint="Impute with median or drop column.",
            )
        ]
        return ModuleResult(
            module_name=self.name,
            analyzer_version=self.version,
            execution_time_ms=5,
            metrics={"missing_columns": 1},
            issues=issues,
        )


def test_analyzer_contract_and_provenance() -> None:
    """Verify that analyzers adhere to the BaseAnalyzer contract and attach full provenance."""
    analyzer = MockNullAnalyzer()
    assert analyzer.name == "mock_null_analyzer"
    assert analyzer.version == "1.0.0"

    ctx = AnalysisContext(
        dataset_version_id="ver-12345",
        target_column="churned",
    )

    result = analyzer.analyze(ctx)
    assert isinstance(result, ModuleResult)
    assert result.module_name == "mock_null_analyzer"
    assert result.analyzer_version == "1.0.0"
    assert len(result.issues) == 1

    issue = result.issues[0]
    assert issue.module == "mock_null_analyzer"
    assert issue.analyzer_version == "1.0.0"
    assert issue.parameters_used == {"null_threshold": 0.40}
    assert issue.evidence["null_percentage"] == 45.0
    assert issue.severity == Severity.HIGH
    assert issue.detected_at is not None
    assert issue.issue_id is not None


def test_ml_readiness_heuristic_scorer_transparency() -> None:
    """Verify that the readiness heuristic computes transparent itemized deductions."""
    analyzer = MockNullAnalyzer()
    ctx = AnalysisContext(dataset_version_id="ver-123")
    result = analyzer.analyze(ctx)

    breakdown = MLReadinessHeuristicScorer.calculate(result.issues)

    # Base score is 100.0, HIGH severity subtracts 10.0
    assert breakdown.base_score == 100.0
    assert breakdown.total_penalties == 10.0
    assert breakdown.heuristic_score == 90.0
    assert breakdown.rating == "Production Ready"
    assert len(breakdown.itemized_penalties) == 1

    penalty = breakdown.itemized_penalties[0]
    assert penalty.module == "mock_null_analyzer"
    assert penalty.severity == Severity.HIGH
    assert penalty.penalty == 10.0
    assert "Excessive Null Rate in Age" in penalty.reason


def test_analysis_pipeline_execution() -> None:
    """Verify that AnalysisPipeline executes registered analyzers sequentially."""
    pipeline = AnalysisPipeline(analyzers=[MockNullAnalyzer()])
    ctx = AnalysisContext(dataset_version_id="ver-pipeline-test")

    output = pipeline.execute(ctx)
    assert output["dataset_version_id"] == "ver-pipeline-test"
    assert output["total_execution_time_ms"] >= 0
    assert len(output["module_results"]) == 1
    assert len(output["all_issues"]) == 1
    assert output["heuristic_breakdown"].heuristic_score == 90.0
