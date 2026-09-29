"""Deterministic analysis pipeline coordinating the modular analyzers."""

import time
from typing import Any, Dict, List
from app.core.logging import get_logger
from app.engine.base import AnalysisContext, BaseAnalyzer, ModuleResult
from app.engine.scoring import HeuristicBreakdown, MLReadinessHeuristicScorer

logger = get_logger(__name__)


class AnalysisPipeline:
    """Orchestrates an ordered sequence of BaseAnalyzer modules over an AnalysisContext."""

    def __init__(self, analyzers: List[BaseAnalyzer]):
        self.analyzers = analyzers

    def execute(self, ctx: AnalysisContext) -> Dict[str, Any]:
        """Run all registered analyzers sequentially and compute the readiness heuristic."""
        start_time = time.perf_counter()
        module_results: List[ModuleResult] = []
        all_issues = []

        logger.info(
            "Starting analysis pipeline for dataset version %s with %d analyzers",
            ctx.dataset_version_id,
            len(self.analyzers),
        )

        for analyzer in self.analyzers:
            analyzer_start = time.perf_counter()
            try:
                res = analyzer.analyze(ctx)
                res.execution_time_ms = int((time.perf_counter() - analyzer_start) * 1000)
                module_results.append(res)
                all_issues.extend(res.issues)
            except Exception as e:
                logger.exception("Error executing analyzer %s: %s", analyzer.name, str(e))
                raise

        heuristic = MLReadinessHeuristicScorer.calculate(all_issues)
        total_time_ms = int((time.perf_counter() - start_time) * 1000)

        return {
            "dataset_version_id": ctx.dataset_version_id,
            "total_execution_time_ms": total_time_ms,
            "module_results": module_results,
            "all_issues": all_issues,
            "heuristic_breakdown": heuristic,
        }
