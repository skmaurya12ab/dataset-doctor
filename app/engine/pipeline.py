"""Deterministic analysis pipeline coordinating the 5 Phase 2 profiling modules."""

from datetime import datetime, timezone
import time
from typing import Any, Dict, List, Optional

from app.core.json_utils import to_json_safe
from app.core.logging import get_logger
from app.engine.base import AnalysisContext, BaseAnalyzer, ModuleResult, QualityIssueData
from app.engine.modules.cardinality_analyzer import CardinalityAnalyzer
from app.engine.modules.dtype_analyzer import DataTypeAnalyzer
from app.engine.modules.duplicate_analyzer import DuplicateAnalyzer
from app.engine.modules.missing_analyzer import MissingValueAnalyzer
from app.engine.modules.schema_analyzer import SchemaAnalyzer
from app.engine.scoring import MLReadinessHeuristicScorer

logger = get_logger(__name__)



def get_default_analyzers() -> List[BaseAnalyzer]:
    """Return the 5 Phase 2 analyzers in strict deterministic order."""
    return [
        SchemaAnalyzer(),
        DataTypeAnalyzer(),
        MissingValueAnalyzer(),
        DuplicateAnalyzer(),
        CardinalityAnalyzer(),
    ]


class AnalysisPipeline:
    """Orchestrates an ordered sequence of deterministic BaseAnalyzer modules over an AnalysisContext."""

    def __init__(self, analyzers: Optional[List[BaseAnalyzer]] = None):
        self.analyzers = analyzers if analyzers is not None else get_default_analyzers()

    def execute(self, ctx: AnalysisContext) -> Dict[str, Any]:
        """Run all registered analyzers sequentially and assemble structured findings."""
        start_time = time.perf_counter()
        module_results: List[ModuleResult] = []
        all_issues: List[QualityIssueData] = []
        analyzer_versions: Dict[str, str] = {}
        combined_metrics: Dict[str, Any] = {}

        logger.info(
            "Starting deterministic analysis pipeline for dataset version %s with %d analyzers",
            ctx.dataset_version_id,
            len(self.analyzers),
        )

        for analyzer in self.analyzers:
            analyzer_start = time.perf_counter()
            analyzer_name = analyzer.name
            analyzer_versions[analyzer_name] = analyzer.version

            try:
                res = analyzer.analyze(ctx)
                res.execution_time_ms = int((time.perf_counter() - analyzer_start) * 1000)
                module_results.append(res)
                all_issues.extend(res.issues)
                combined_metrics[analyzer_name] = res.metrics

                logger.info(
                    "Analyzer %s (v%s) completed in %d ms with %d issues",
                    analyzer_name,
                    analyzer.version,
                    res.execution_time_ms,
                    len(res.issues),
                )
            except Exception as e:
                logger.exception("Error executing analyzer %s: %s", analyzer_name, str(e))
                raise

        total_time_ms = int((time.perf_counter() - start_time) * 1000)

        # Build centralized summary metrics deterministically
        schema_m = combined_metrics.get("schema_analyzer", {})
        dtype_m = combined_metrics.get("dtype_analyzer", {})
        missing_m = combined_metrics.get("missing_analyzer", {})
        dup_m = combined_metrics.get("duplicate_analyzer", {})
        card_m = combined_metrics.get("cardinality_analyzer", {})

        summary_metrics: Dict[str, Any] = {
            "row_count": schema_m.get("row_count", 0),
            "column_count": schema_m.get("column_count", 0),
            "missing_columns": missing_m.get("missing_columns_count", 0),
            "total_missing_cells": missing_m.get("total_missing_cells", 0),
            "overall_missing_percentage": missing_m.get("overall_missing_percentage", 0.0),
            "columns_with_type_warnings": dtype_m.get("columns_with_type_warnings", 0),
            "duplicate_row_count": dup_m.get("duplicate_row_count", 0),
            "duplicate_percentage": dup_m.get("duplicate_percentage", 0.0),
            "constant_columns": card_m.get("constant_columns_count", 0),
            "high_cardinality_columns": card_m.get("high_cardinality_columns_count", 0),
        }

        critical_count = sum(1 for iss in all_issues if iss.severity.value == "CRITICAL")
        total_count = len(all_issues)

        logger.info(
            "Deterministic analysis pipeline finished in %d ms: %d total issues (%d critical)",
            total_time_ms,
            total_count,
            critical_count,
        )

        heuristic = MLReadinessHeuristicScorer.calculate(all_issues)

        return {
            "dataset_version_id": ctx.dataset_version_id,
            "total_execution_time_ms": total_time_ms,
            "module_results": module_results,
            "all_issues": all_issues,
            "analyzer_versions": analyzer_versions,
            "combined_metrics": to_json_safe(combined_metrics),
            "summary_metrics": to_json_safe(summary_metrics),
            "total_issues_count": total_count,
            "critical_issues_count": critical_count,
            "heuristic_breakdown": heuristic,
        }

