"""AI interpretation provider abstraction.

CRITICAL ARCHITECTURAL CONSTRAINTS:
1. Vendor Neutrality: Decouples domain logic from OpenAI or any specific model vendor SDK.
2. Failure Resilience: AI output is never assumed to be 100% correct.
   Providers must surface refusal metadata, token counts, and structured error indicators.
3. Factual Grounding: The provider must only interpret deterministic findings;
   it is strictly prohibited from generating fake or synthetic numerical dataset statistics.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any, Dict, Generic, Optional, Type, TypeVar
from pydantic import BaseModel, Field

from app.models.analysis import QualityIssue
from app.schemas.ai import AIReportContent, FindingExplanation

if TYPE_CHECKING:
    from app.services.ai.findings_digest import FindingsDigest

T = TypeVar("T", bound=BaseModel)


class LLMUsage(BaseModel):
    """Token consumption metrics for auditing, cost controls, and rate-limit tracking."""

    prompt_tokens: int = Field(default=0, ge=0)
    completion_tokens: int = Field(default=0, ge=0)
    total_tokens: int = Field(default=0, ge=0)

    @property
    def input_tokens(self) -> int:
        return self.prompt_tokens

    @property
    def output_tokens(self) -> int:
        return self.completion_tokens


class LLMResponseResult(BaseModel, Generic[T]):
    """Standardized response container returned by all LLM providers."""

    parsed: Optional[T] = None
    raw_content: Optional[str] = None
    refusal: Optional[str] = None
    is_error: bool = False
    error_message: Optional[str] = None
    usage: LLMUsage = Field(default_factory=LLMUsage)
    model: str = ""


class BaseLLMProvider(ABC):
    """Abstract interface defining the AI interpretation provider boundary."""

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Name of the underlying provider (e.g. 'openai-responses', 'mock')."""
        pass

    @property
    @abstractmethod
    def model_name(self) -> str:
        """Configured model identifier (e.g. 'gpt-4o-2024-08-06')."""
        pass

    @abstractmethod
    async def generate_structured(
        self,
        system_prompt: str,
        user_prompt: str,
        response_schema: Type[T],
        temperature: float = 0.1,
        max_output_tokens: Optional[int] = None,
    ) -> LLMResponseResult[T]:
        """Request structured interpretation output guaranteed to conform to response_schema.

        Must handle retries, refusals, and timeouts gracefully.
        """
        pass

    @abstractmethod
    async def explain_finding(
        self,
        finding: QualityIssue,
        context: Optional[Dict[str, Any]] = None,
    ) -> LLMResponseResult[FindingExplanation]:
        """Generate a grounded, contextual explanation for an individual finding.

        The explanation must be strictly grounded in the provided deterministic evidence.
        """
        pass

    @abstractmethod
    async def generate_remediation_plan(
        self,
        findings_digest: FindingsDigest,
        context: Optional[Dict[str, Any]] = None,
    ) -> LLMResponseResult[AIReportContent]:
        """Generate an advisory remediation plan and risk assessment from deterministic findings."""
        pass

    async def generate_analysis_report(
        self,
        findings_digest: FindingsDigest,
        context: Optional[Dict[str, Any]] = None,
    ) -> LLMResponseResult[AIReportContent]:
        """Conceptual alias for generate_remediation_plan."""
        return await self.generate_remediation_plan(findings_digest, context=context)
