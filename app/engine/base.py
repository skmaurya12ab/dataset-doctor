"""Foundational analyzer interfaces and data contracts for Dataset Doctor.

CRITICAL ARCHITECTURAL CONSTRAINTS:
1. Pure Determinism: Analyzers calculate factual statistics only. Never invoke LLMs or external network APIs.
2. Layer Isolation: Analyzers must NEVER import or depend on FastAPI, Starlette, HTTP request objects,
   or frontend presentation logic.
3. Traceable Provenance: Every detected QualityIssueData is stamped with the analyzer's version and parameters.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional
import uuid


class Severity(str, Enum):
    """Standardized severity classification for dataset quality issues."""

    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    INFO = "INFO"


@dataclass(frozen=True)
class QualityIssueData:
    """Individual data-quality or ML-readiness defect with complete provenance."""

    module: str
    analyzer_version: str
    category: str
    severity: Severity
    title: str
    description: str
    column_name: Optional[str] = None
    parameters_used: Dict[str, Any] = field(default_factory=dict)
    evidence: Dict[str, Any] = field(default_factory=dict)
    remediation_hint: Optional[str] = None
    issue_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    detected_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


# Alias for convenience and backwards-compatibility across codebase
QualityIssue = QualityIssueData


@dataclass
class ModuleResult:
    """Structured output returned by an individual analyzer module."""

    module_name: str
    analyzer_version: str
    execution_time_ms: int
    metrics: Dict[str, Any] = field(default_factory=dict)
    issues: List[QualityIssueData] = field(default_factory=list)


@dataclass
class AnalysisContext:
    """Execution context and dataset reference passed to analyzers.
    
    Contains the dataset data, user-specified target configurations,
    parameters, and an in-memory cache shared across the pipeline.
    """

    dataset_version_id: str
    file_path: Optional[Path] = None
    df: Optional[Any] = None  # DataFrame instance (pandas/polars/pyarrow)
    file_format: str = "parquet"
    target_column: Optional[str] = None
    problem_type: Optional[str] = None  # 'classification', 'regression', 'unsupervised'
    sample_size: int = 50_000
    random_seed: int = 42
    parameters: Dict[str, Any] = field(default_factory=dict)
    inferred_types: Dict[str, str] = field(default_factory=dict)
    shared_cache: Dict[str, Any] = field(default_factory=dict)


class BaseAnalyzer(ABC):
    """Abstract protocol for all deterministic profiling modules."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique identifier for the analyzer module (e.g. 'missing_value_analyzer')."""
        pass

    @property
    @abstractmethod
    def version(self) -> str:
        """Semantic version of the analyzer logic (e.g. '1.0.0')."""
        pass

    @abstractmethod
    def analyze(self, ctx: AnalysisContext) -> ModuleResult:
        """Execute deterministic profiling and return structured metrics and issues.
        
        Must be a pure calculation with no side-effects or external network I/O.
        """
        pass
