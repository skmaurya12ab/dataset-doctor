"""Tests for AnalysisJobRunner contract and ThreadPoolJobRunner implementation."""

import asyncio
import time
import pytest
from app.services.job_runner import JobStatus, ThreadPoolJobRunner


def sample_successful_task(x: int, y: int) -> int:
    """Simple CPU task simulating deterministic computation."""
    time.sleep(0.05)
    return x + y


def sample_failing_task() -> None:
    """Task simulating an unhandled calculation exception."""
    raise ValueError("Calculation failed due to division by zero")


@pytest.mark.asyncio
async def test_job_runner_lifecycle_success() -> None:
    """Verify that a job transitions through PENDING -> RUNNING -> COMPLETED."""
    runner = ThreadPoolJobRunner(max_workers=2)
    try:
        job = await runner.submit_job("job-success-1", sample_successful_task, 15, 27)
        assert job.job_id == "job-success-1"
        assert job.status in (JobStatus.PENDING, JobStatus.RUNNING)

        # Poll status until finished
        for _ in range(20):
            await asyncio.sleep(0.02)
            status = await runner.get_job_status("job-success-1")
            if status and status.status == JobStatus.COMPLETED:
                break

        final_status = await runner.get_job_status("job-success-1")
        assert final_status is not None
        assert final_status.status == JobStatus.COMPLETED
        assert final_status.result == 42
        assert final_status.error_message is None
        assert final_status.started_at is not None
        assert final_status.completed_at is not None
    finally:
        await runner.shutdown(wait=True)


@pytest.mark.asyncio
async def test_job_runner_lifecycle_failure() -> None:
    """Verify that a failing task captures the exception and transitions to FAILED."""
    runner = ThreadPoolJobRunner(max_workers=2)
    try:
        await runner.submit_job("job-failure-1", sample_failing_task)

        for _ in range(20):
            await asyncio.sleep(0.02)
            status = await runner.get_job_status("job-failure-1")
            if status and status.status == JobStatus.FAILED:
                break

        final_status = await runner.get_job_status("job-failure-1")
        assert final_status is not None
        assert final_status.status == JobStatus.FAILED
        assert "division by zero" in (final_status.error_message or "")
    finally:
        await runner.shutdown(wait=True)


@pytest.mark.asyncio
async def test_job_runner_duplicate_rejection() -> None:
    """Verify that submitting an active job with an existing job_id raises ValueError."""
    runner = ThreadPoolJobRunner(max_workers=1)
    try:
        # Submit a slow task
        await runner.submit_job("duplicate-test-job", time.sleep, 0.2)

        with pytest.raises(ValueError, match="already active"):
            await runner.submit_job("duplicate-test-job", sample_successful_task, 1, 1)
    finally:
        await runner.shutdown(wait=True)
