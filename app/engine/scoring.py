"""Explainable ML Readiness Heuristic calculation.

CRITICAL ARCHITECTURAL CONSTRAINTS:
This is an explainable heuristic, NOT an 'objectively calibrated ground truth' score.
All penalty weights, contributing factors, and deductions must remain transparent
and inspectable in the resulting breakdown.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional
from app.engine.base import QualityIssue, Severity


@dataclass
class ItemizedPenalty:
    """Explicit record of a penalty deduction applied to the readiness score."""

    module: str
    severity: Severity
    reason: str
    penalty: float
    column_name: Optional[str] = None


@dataclass
class HeuristicBreakdown:
    """Complete transparent explanation of how the ML Readiness Heuristic was calculated."""

    heuristic_score: float
    rating: str
    base_score: float = 100.0
    total_penalties: float = 0.0
    itemized_penalties: List[ItemizedPenalty] = field(default_factory=list)
    disclaimer: str = (
        "This score is a deterministic heuristic reflecting structural, statistical, and modeling "
        "data hygiene. It does not guarantee downstream model performance."
    )


class MLReadinessHeuristicScorer:
    """Calculates the explainable ML Readiness Heuristic from detected quality issues."""

    # Configurable penalty weights
    PENALTY_WEIGHTS = {
        Severity.CRITICAL: 25.0,
        Severity.HIGH: 10.0,
        Severity.MEDIUM: 4.0,
        Severity.LOW: 1.0,
        Severity.INFO: 0.0,
    }

    @classmethod
    def calculate(
        cls,
        issues: List[QualityIssue],
        max_penalty_per_column: float = 25.0,
    ) -> HeuristicBreakdown:
        """Compute the heuristic score and return the complete itemized breakdown with de-duplication."""
        penalties: List[ItemizedPenalty] = []
        column_penalties: Dict[str, float] = {}
        total_penalty = 0.0

        for issue in issues:
            raw_weight = cls.PENALTY_WEIGHTS.get(issue.severity, 0.0)
            if raw_weight <= 0.0:
                continue

            col = issue.column_name
            effective_penalty = raw_weight

            # De-duplication safeguard: Cap cumulative penalties applied to any single column
            if col:
                current_col_penalty = column_penalties.get(col, 0.0)
                if current_col_penalty >= max_penalty_per_column:
                    continue
                if current_col_penalty + raw_weight > max_penalty_per_column:
                    effective_penalty = max_penalty_per_column - current_col_penalty
                column_penalties[col] = current_col_penalty + effective_penalty

            total_penalty += effective_penalty
            penalties.append(
                ItemizedPenalty(
                    module=issue.module,
                    severity=issue.severity,
                    reason=f"{issue.title}: {issue.description}",
                    penalty=round(effective_penalty, 2),
                    column_name=col,
                )
            )

        score = max(0.0, round(100.0 - total_penalty, 2))

        # Rating labels as defined in Section 8.6
        if score >= 90.0:
            rating = "Production-oriented readiness"
        elif score >= 75.0:
            rating = "Minor remediation"
        elif score >= 50.0:
            rating = "Significant preprocessing"
        else:
            rating = "High risk / substantial remediation"

        return HeuristicBreakdown(
            heuristic_score=score,
            rating=rating,
            base_score=100.0,
            total_penalties=round(total_penalty, 2),
            itemized_penalties=penalties,
        )
