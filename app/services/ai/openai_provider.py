"""OpenAI modern Responses API provider with structured Pydantic outputs, retries, and token accounting."""

import asyncio
import logging
from typing import Any, Dict, Optional, Type, TypeVar
import openai
from pydantic import BaseModel, ValidationError

from app.core.config import Settings, get_settings
from app.models.analysis import QualityIssue
from app.schemas.ai import AIReportContent, FindingExplanation
from app.services.ai.findings_digest import FindingsDigest
from app.services.ai.prompts.finding_explanation import build_finding_explanation_prompts
from app.services.ai.prompts.remediation_plan import build_remediation_plan_prompts
from app.services.ai_provider import BaseLLMProvider, LLMResponseResult, LLMUsage

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)

# Retryable exception classes for transient network and service issues
RETRYABLE_EXCEPTIONS = (
    openai.APITimeoutError,
    openai.APIConnectionError,
    openai.RateLimitError,
    openai.InternalServerError,
)


class OpenAIResponsesProvider(BaseLLMProvider):
    """Production provider using the modern OpenAI Responses API with structured Pydantic output."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        timeout_seconds: Optional[float] = None,
        max_retries: Optional[int] = None,
        retry_backoff: Optional[float] = None,
        max_output_tokens: Optional[int] = None,
        client: Optional[openai.AsyncOpenAI] = None,
    ):
        settings: Settings = get_settings()
        self._api_key = api_key or settings.openai_api_key
        self._model = model or settings.openai_model
        self._timeout_seconds = timeout_seconds if timeout_seconds is not None else settings.openai_timeout_seconds
        self._max_retries = max_retries if max_retries is not None else settings.openai_max_retries
        self._retry_backoff = retry_backoff if retry_backoff is not None else settings.openai_retry_backoff
        self._max_output_tokens = max_output_tokens if max_output_tokens is not None else settings.openai_max_output_tokens

        if client is not None:
            self._client = client
        elif self._api_key:
            self._client = openai.AsyncOpenAI(
                api_key=self._api_key,
                timeout=self._timeout_seconds,
            )
        else:
            self._client = None

    @property
    def provider_name(self) -> str:
        return "openai-responses"

    @property
    def model_name(self) -> str:
        return self._model

    def _extract_refusal_or_error(self, response: Any) -> Optional[str]:
        """Extract refusal text if the model refused the request."""
        # 1. Check response-level status
        if getattr(response, "status", None) in ("incomplete", "failed", "refused"):
            incomplete = getattr(response, "incomplete_details", None)
            if incomplete:
                return f"Response incomplete: {getattr(incomplete, 'reason', 'unknown')}"

        # 2. Inspect output messages and content items
        output_items = getattr(response, "output", []) or []
        for item in output_items:
            if getattr(item, "type", None) == "message":
                contents = getattr(item, "content", []) or []
                for content in contents:
                    c_type = getattr(content, "type", None)
                    if c_type == "refusal":
                        return getattr(content, "refusal", "Model refused request")
        return None

    async def generate_structured(
        self,
        system_prompt: str,
        user_prompt: str,
        response_schema: Type[T],
        temperature: float = 0.1,
        max_output_tokens: Optional[int] = None,
    ) -> LLMResponseResult[T]:
        """Request structured interpretation output via OpenAI Responses API with retries."""
        if not self._client:
            return LLMResponseResult[T](
                is_error=True,
                error_message="OpenAI API key is not configured",
                model=self._model,
            )

        output_tokens = max_output_tokens or self._max_output_tokens
        attempt = 0
        last_exception: Optional[Exception] = None

        while attempt <= self._max_retries:
            attempt += 1
            try:
                logger.info(
                    "Submitting request to OpenAI Responses API (model: %s, schema: %s, attempt: %d/%d)",
                    self._model,
                    response_schema.__name__,
                    attempt,
                    self._max_retries + 1,
                )

                # Execute using modern Responses API parse method
                response = await self._client.responses.parse(
                    model=self._model,
                    instructions=system_prompt,
                    input=user_prompt,
                    text_format=response_schema,
                    temperature=temperature,
                    max_output_tokens=output_tokens,
                )

                # Extract token usage
                usage = LLMUsage()
                if hasattr(response, "usage") and response.usage:
                    usage = LLMUsage(
                        prompt_tokens=getattr(response.usage, "input_tokens", 0),
                        completion_tokens=getattr(response.usage, "output_tokens", 0),
                        total_tokens=getattr(response.usage, "total_tokens", 0),
                    )

                # Extract raw output text safely
                raw_text_val = getattr(response, "output_text", None)
                raw_text: Optional[str] = (
                    raw_text_val
                    if isinstance(raw_text_val, str)
                    else (str(raw_text_val) if raw_text_val is not None and type(raw_text_val).__name__ != "MagicMock" else None)
                )

                # Check for explicit refusal or incomplete status
                refusal_msg = self._extract_refusal_or_error(response)
                if refusal_msg:
                    logger.warning("OpenAI model refused request: %s", refusal_msg)
                    return LLMResponseResult[T](
                        refusal=refusal_msg,
                        raw_content=raw_text,
                        usage=usage,
                        model=self._model,
                    )

                # Extract parsed output
                parsed_model: Optional[T] = getattr(response, "output_parsed", None)

                # Fallback manual validation if output_parsed is None but output_text is present
                if parsed_model is None and raw_text:
                    try:
                        parsed_model = response_schema.model_validate_json(raw_text)
                    except ValidationError as val_err:
                        logger.error("Structured validation error on raw response text: %s", val_err)
                        return LLMResponseResult[T](
                            is_error=True,
                            error_message=f"Output schema validation failed: {str(val_err)}",
                            raw_content=raw_text,
                            usage=usage,
                            model=self._model,
                        )

                if parsed_model is None:
                    return LLMResponseResult[T](
                        is_error=True,
                        error_message="OpenAI returned empty or unparseable structured output",
                        raw_content=raw_text,
                        usage=usage,
                        model=self._model,
                    )

                return LLMResponseResult[T](
                    parsed=parsed_model,
                    raw_content=raw_text,
                    usage=usage,
                    model=self._model,
                )

            except RETRYABLE_EXCEPTIONS as exc:
                last_exception = exc
                logger.warning(
                    "Transient OpenAI API error on attempt %d: %s. Will retry...",
                    attempt,
                    type(exc).__name__,
                )
                if attempt <= self._max_retries:
                    backoff_delay = self._retry_backoff * (2 ** (attempt - 1))
                    await asyncio.sleep(backoff_delay)
                else:
                    break

            except openai.APIStatusError as exc:
                # Retry on 5xx status codes
                if exc.status_code in (500, 502, 503, 504) and attempt <= self._max_retries:
                    last_exception = exc
                    logger.warning(
                        "OpenAI status %d on attempt %d. Will retry...",
                        exc.status_code,
                        attempt,
                    )
                    backoff_delay = self._retry_backoff * (2 ** (attempt - 1))
                    await asyncio.sleep(backoff_delay)
                else:
                    # Non-retryable status (400, 401, 403, 404, 422, etc.)
                    logger.error("Non-retryable OpenAI APIStatusError (%d): %s", exc.status_code, exc.message)
                    return LLMResponseResult[T](
                        is_error=True,
                        error_message=f"OpenAI error {exc.status_code}: {exc.message}",
                        model=self._model,
                    )

            except Exception as exc:
                # Unknown / unretryable fatal error
                logger.error("Unexpected fatal error communicating with OpenAI: %s", exc, exc_info=True)
                return LLMResponseResult[T](
                    is_error=True,
                    error_message=f"Unexpected error: {str(exc)}",
                    model=self._model,
                )

        # Retries exhausted
        err_msg = f"OpenAI request failed after {self._max_retries + 1} attempts: {str(last_exception)}"
        logger.error(err_msg)
        return LLMResponseResult[T](
            is_error=True,
            error_message=err_msg,
            model=self._model,
        )

    async def explain_finding(
        self,
        finding: QualityIssue,
        context: Optional[Dict[str, Any]] = None,
    ) -> LLMResponseResult[FindingExplanation]:
        sys_prompt, user_prompt = build_finding_explanation_prompts(finding, context)
        return await self.generate_structured(
            system_prompt=sys_prompt,
            user_prompt=user_prompt,
            response_schema=FindingExplanation,
        )

    async def generate_remediation_plan(
        self,
        findings_digest: FindingsDigest,
        context: Optional[Dict[str, Any]] = None,
    ) -> LLMResponseResult[AIReportContent]:
        sys_prompt, user_prompt = build_remediation_plan_prompts(findings_digest, context)
        return await self.generate_structured(
            system_prompt=sys_prompt,
            user_prompt=user_prompt,
            response_schema=AIReportContent,
        )
