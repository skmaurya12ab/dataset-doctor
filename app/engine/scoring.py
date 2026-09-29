"""Explainable ML Readiness Heuristic calculation.

CRITICAL ARCHITECTURAL CONSTRAINTS:
This is an explainable heuristic, NOT an 'objectively calibrated ground truth' score.
All penalty weights, contributing factors, and deductions must remain transparent
and inspectable in the resulting breakdown.
"""

from dataclasses import dataclass, field
from typing import List
from app.engine.base import QualityIssue, Severity


@dataclass
class ItemizedPenalty:
    """Explicit record of a penalty deduction applied to the readiness score."""

    module: str
    severity: Severity
    reason: str
    penalty: float


@dataclass
class HeuristicBreakdown:
    """Complete transparent explanation of how the ML Readiness Heuristic was calculated."""

    heuristic_score: float
    rating: str
    base_score: float = 100.0
    total_penalties: float = 0.0
    itemized_penalties: List[ItemizedPenalty] = field(default_factory=list)
    disclaimer: str = (
        "This score is a deterministic heuristic reflecting structural and statistical "
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
    def calculate(cls, issues: List[QualityIssue]) -> HeuristicBreakdown:
        """Compute the heuristic score and return the complete itemized breakdown."""
        penalties: List[ItemizedPenalty] = []
        total_penalty = 0.0

        for issue in issues:
            weight = cls.PENALTY_WEIGHTS.get(issue.severity, 0.0)
            if weight > 0:
                total_penalty += weight
                penalties.append(
                    ItemizedPenalty(
                        module=issue.module,
                        severity=issue.severity,
                        reason=f"{issue.title}: {issue.description}",
                        penalty=weight,
                    )
                )

        score = max(0.0, round(100.0 - total_penalty, 2))

        if score >= 90.0:
            rating = "Production Ready"
        elif score >= 75.0:
            rating = "Minor Remediation Needed"
        elif score >= 50.0:
            rating = "Significant Preprocessing Required"
        else:
            rating = "Not ML-Ready / High Risk"

        return HeuristicBreakdown(
            heuristic_score=score,
            rating=rating,
            base_score=100.0,
            total_penalties=round(total_penalty, 2),
            itemized_penalties=penalties,
        )
