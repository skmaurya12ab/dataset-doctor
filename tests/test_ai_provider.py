"""Unit and resilience tests for BaseLLMProvider, MockLLMProvider, and OpenAIResponsesProvider."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
import pytest
import openai

from app.models.analysis import QualityIssue
from app.schemas.ai import AIReportContent, FindingExplanation
from app.services.ai.findings_digest import FindingsDigest
from app.services.ai.mock_provider import MockLLMProvider
from app.services.ai.openai_provider import OpenAIResponsesProvider


@pytest.fixture
def sample_quality_issue() -> QualityIssue:
    return QualityIssue(
        module="missing_analyzer",
        analyzer_version="1.0.0",
        category="MISSING_VALUES",
        severity="HIGH",
        column_name="income",
        title="High missing rate in income",
        description="income column is missing 27.4% of values.",
        evidence={"missing_percentage": 27.4, "null_count": 274},
        remediation_hint="Impute with median income",
    )


@pytest.fixture
def sample_findings_digest() -> FindingsDigest:
    return FindingsDigest(
        dataset_metadata={"name": "test.csv", "row_count": 1000, "column_count": 5},
        summary_metrics={"null_rate": 0.05},
        total_issues=1,
        included_issues=1,
        priority_issues=[],
    )


# ---------------------------------------------------------------------------
# MockLLMProvider Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_mock_provider_explain_finding(sample_quality_issue: QualityIssue):
    """Test MockLLMProvider successful grounded finding explanation."""
    provider = MockLLMProvider()
    result = await provider.explain_finding(sample_quality_issue)

    assert result.is_error is False
    assert result.refusal is None
    assert result.parsed is not None
    assert isinstance(result.parsed, FindingExplanation)
    assert len(result.parsed.recommended_actions) > 0
    assert result.usage.total_tokens > 0
    assert len(provider.call_history) == 1


@pytest.mark.asyncio
async def test_mock_provider_generate_remediation_plan(sample_findings_digest: FindingsDigest):
    """Test MockLLMProvider successful remediation plan generation."""
    provider = MockLLMProvider()
    result = await provider.generate_remediation_plan(sample_findings_digest)

    assert result.is_error is False
    assert result.parsed is not None
    assert isinstance(result.parsed, AIReportContent)
    assert len(result.parsed.risk_assessment) > 0
    assert len(result.parsed.transformation_specs) > 0


@pytest.mark.asyncio
async def test_mock_provider_simulate_refusal(sample_quality_issue: QualityIssue):
    """Test MockLLMProvider refusal simulation."""
    provider = MockLLMProvider(simulate_refusal="I cannot evaluate this finding due to policy constraints.")
    result = await provider.explain_finding(sample_quality_issue)

    assert result.parsed is None
    assert result.refusal == "I cannot evaluate this finding due to policy constraints."


@pytest.mark.asyncio
async def test_mock_provider_simulate_timeout(sample_quality_issue: QualityIssue):
    """Test MockLLMProvider timeout simulation."""
    provider = MockLLMProvider(simulate_timeout=True)
    with pytest.raises(asyncio.TimeoutError):
        await provider.explain_finding(sample_quality_issue)


@pytest.mark.asyncio
async def test_mock_provider_simulate_transient_failure_recovery(sample_quality_issue: QualityIssue):
    """Test MockLLMProvider simulating transient failure then success."""
    provider = MockLLMProvider(fail_first_n_calls=1)

    # First call fails
    result1 = await provider.explain_finding(sample_quality_issue)
    assert result1.is_error is True
    assert "rate limit" in result1.error_message.lower()

    # Second call succeeds
    result2 = await provider.explain_finding(sample_quality_issue)
    assert result2.is_error is False
    assert result2.parsed is not None


# ---------------------------------------------------------------------------
# OpenAIResponsesProvider Tests (Mocked SDK responses)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_openai_provider_missing_api_key():
    """Verify provider returns structured error when API key is missing."""
    provider = OpenAIResponsesProvider(api_key=None, client=None)
    result = await provider.generate_structured(
        system_prompt="sys",
        user_prompt="usr",
        response_schema=FindingExplanation,
    )
    assert result.is_error is True
    assert "API key is not configured" in result.error_message


@pytest.mark.asyncio
async def test_openai_provider_success_flow():
    """Verify OpenAI Responses API successful parsed output flow."""
    mock_client = MagicMock()
    mock_responses = MagicMock()
    mock_client.responses = mock_responses

    expected_output = FindingExplanation(
        explanation="Missing values in feature",
        why_it_matters="Reduces precision",
        practical_impact="Biases model",
        recommended_actions=["Impute with median"],
        limitations=["Assumes MAR"],
    )

    mock_response = MagicMock()
    mock_response.status = "completed"
    mock_response.output_parsed = expected_output
    mock_response.output_text = expected_output.model_dump_json()
    mock_response.usage = MagicMock(input_tokens=150, output_tokens=80, total_tokens=230)
    mock_response.output = []

    mock_responses.parse = AsyncMock(return_value=mock_response)

    provider = OpenAIResponsesProvider(
        api_key="sk-test-mock-key-never-logged",
        model="gpt-4o-2024-08-06",
        client=mock_client,
    )

    result = await provider.generate_structured(
        system_prompt="sys",
        user_prompt="usr",
        response_schema=FindingExplanation,
    )

    assert result.is_error is False
    assert result.parsed == expected_output
    assert result.usage.prompt_tokens == 150
    assert result.usage.completion_tokens == 80
    assert result.usage.total_tokens == 230
    assert result.model == "gpt-4o-2024-08-06"


@pytest.mark.asyncio
async def test_openai_provider_refusal_handling():
    """Verify OpenAI Responses API refusal is properly captured."""
    mock_client = MagicMock()
    mock_responses = MagicMock()
    mock_client.responses = mock_responses

    # Construct mock refusal output
    mock_content = MagicMock()
    mock_content.type = "refusal"
    mock_content.refusal = "Adversarial request rejected"

    mock_msg = MagicMock()
    mock_msg.type = "message"
    mock_msg.content = [mock_content]

    mock_response = MagicMock()
    mock_response.status = "completed"
    mock_response.output_parsed = None
    mock_response.output = [mock_msg]
    mock_response.usage = MagicMock(input_tokens=50, output_tokens=10, total_tokens=60)

    mock_responses.parse = AsyncMock(return_value=mock_response)

    provider = OpenAIResponsesProvider(
        api_key="sk-test-mock-key",
        client=mock_client,
    )

    result = await provider.generate_structured(
        system_prompt="sys",
        user_prompt="usr",
        response_schema=FindingExplanation,
    )

    assert result.parsed is None
    assert result.refusal == "Adversarial request rejected"


@pytest.mark.asyncio
async def test_openai_provider_retry_on_rate_limit():
    """Verify OpenAI provider retries transient rate limits with exponential backoff."""
    mock_client = MagicMock()
    mock_responses = MagicMock()
    mock_client.responses = mock_responses

    # Create dummy rate limit response object for exception
    fake_response = MagicMock()
    fake_response.status_code = 429
    fake_response.headers = {}

    rate_limit_err = openai.RateLimitError(
        message="Rate limit exceeded",
        response=fake_response,
        body=None,
    )

    expected_output = FindingExplanation(
        explanation="Recovered after rate limit",
        why_it_matters="Data quality",
        practical_impact="None",
        recommended_actions=["Retry logic works"],
        limitations=[],
    )
    mock_success = MagicMock(
        status="completed",
        output_parsed=expected_output,
        output_text=expected_output.model_dump_json(),
        usage=MagicMock(input_tokens=10, output_tokens=10, total_tokens=20),
        output=[],
    )

    # First call raises RateLimitError, second succeeds
    mock_responses.parse = AsyncMock(side_effect=[rate_limit_err, mock_success])

    provider = OpenAIResponsesProvider(
        api_key="sk-test",
        max_retries=2,
        retry_backoff=0.01,  # Fast backoff for test
        client=mock_client,
    )

    result = await provider.generate_structured(
        system_prompt="sys",
        user_prompt="usr",
        response_schema=FindingExplanation,
    )

    assert result.is_error is False
    assert result.parsed == expected_output
    assert mock_responses.parse.call_count == 2


@pytest.mark.asyncio
async def test_openai_provider_non_retryable_bad_request():
    """Verify non-retryable 400 BadRequestError fails immediately without retry."""
    mock_client = MagicMock()
    mock_responses = MagicMock()
    mock_client.responses = mock_responses

    fake_response = MagicMock(status_code=400)
    bad_req_err = openai.BadRequestError(
        message="Invalid model parameter format",
        response=fake_response,
        body=None,
    )
    mock_responses.parse = AsyncMock(side_effect=bad_req_err)

    provider = OpenAIResponsesProvider(
        api_key="sk-test",
        max_retries=3,
        retry_backoff=0.01,
        client=mock_client,
    )

    result = await provider.generate_structured(
        system_prompt="sys",
        user_prompt="usr",
        response_schema=FindingExplanation,
    )

    assert result.is_error is True
    assert "OpenAI error 400" in result.error_message
    assert mock_responses.parse.call_count == 1  # No retries for 400!
