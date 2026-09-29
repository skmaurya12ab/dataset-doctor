"""AI interpretation provider abstraction.

CRITICAL ARCHITECTURAL CONSTRAINTS:
1. Vendor Neutrality: Decouples domain logic from OpenAI or any specific model vendor SDK.
2. Failure Resilience: AI output is never assumed to be 100% correct.
   Providers must surface refusal metadata, token counts, and structured error indicators.
3. Factual Grounding: The provider must only interpret deterministic findings;
   it is strictly prohibited from generating fake or synthetic numerical dataset statistics.
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, Generic, Optional, Type, TypeVar
from pydantic import BaseModel, Field
from app.engine.base import QualityIssue

T = TypeVar("T", bound=BaseModel)


class LLMUsage(BaseModel):
    """Token consumption metrics for auditing and rate-limit tracking."""

    prompt_tokens: int = Field(default=0, ge=0)
    completion_tokens: int = int(0)
    total_tokens: int = Field(default=0, ge=0)


class LLMResponseResult(BaseModel, Generic[T]):
    """Standardized response container returned by all LLM providers."""

    parsed: Optional[T] = None
    raw_content: Optional[str] = None
    refusal: Optional[str] = None
    is_error: bool = False
    error_message: Optional[str] = None
    usage: LLMUsage = Field(default_factory=LLMUsage)
    model: str = ""


class FindingExplanation(BaseModel):
    """Structured explanation of an individual data-quality finding."""

    issue_id: str
    title: str
    conceptual_explanation: str = Field(
        description="Clear, non-mathematical explanation of what this issue represents."
    )
    ml_impact: str = Field(
        description="Specific consequences of this issue on ML model training and validation."
    )
    industry_remediation_options: str = Field(
        description="Standard machine-learning engineering and data-cleaning practices to address it."
    )


class BaseLLMProvider(ABC):
    """Abstract interface defining the AI interpretation provider boundary."""

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Name of the underlying provider (e.g. 'openai-responses', 'anthropic')."""
        pass

    @abstractmethod
    async def generate_structured(
        self,
        system_prompt: str,
        user_prompt: str,
        response_schema: Type[T],
        temperature: float = 0.1,
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
        
        The explanation must be strictly grounded in the provided evidence.
        """
        pass
