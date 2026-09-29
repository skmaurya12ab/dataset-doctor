"""Analysis job runner abstraction and V1 ThreadPool implementation.

ARCHITECTURAL NOTES:
1. V1 uses an in-process ThreadPoolExecutor to prevent blocking FastAPI's event loop.
2. The AnalysisJobRunner interface decouples the web layer from the worker runtime.
3. Migrating to an external queue (Celery, ARQ, Redis) in V2 only requires implementing
   a new subclass of AnalysisJobRunner, with ZERO changes to API routes or analyzer code.
4. THREAD ISOLATION: Worker threads must NEVER share request-scoped AsyncSessions.
"""

from abc import ABC, abstractmethod
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
import threading
from typing import Any, Callable, Dict, Optional
from app.core.logging import get_logger

logger = get_logger(__name__)


class JobStatus(str, Enum):
    """Lifecycle status of a background analysis job."""

    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


@dataclass
class JobInfo:
    """Metadata tracking the execution state of an analysis job."""

    job_id: str
    status: JobStatus = JobStatus.PENDING
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    error_message: Optional[str] = None
    result: Optional[Any] = None


class AnalysisJobRunner(ABC):
    """Abstract interface defining the background job runner contract."""

    @abstractmethod
    async def submit_job(
        self,
        job_id: str,
        target_fn: Callable[..., Any],
        *args: Any,
        **kwargs: Any,
    ) -> JobInfo:
        """Submit a background job for asynchronous execution."""
        pass

    @abstractmethod
    async def get_job_status(self, job_id: str) -> Optional[JobInfo]:
        """Query the current state and results of a submitted job."""
        pass

    @abstractmethod
    async def cancel_job(self, job_id: str) -> bool:
        """Attempt to cancel a pending job."""
        pass

    @abstractmethod
    async def shutdown(self, wait: bool = True) -> None:
        """Gracefully release worker pool resources."""
        pass


class ThreadPoolJobRunner(AnalysisJobRunner):
    """V1 in-process background job runner using Python's ThreadPoolExecutor."""

    def __init__(self, max_workers: int = 4):
        self.max_workers = max_workers
        self._executor = ThreadPoolExecutor(
            max_workers=max_workers,
            thread_name_prefix="analysis-worker-",
        )
        self._jobs: Dict[str, JobInfo] = {}
        self._futures: Dict[str, Future] = {}
        self._lock = threading.Lock()
        logger.info("Initialized ThreadPoolJobRunner with %d workers", max_workers)

    def _execute_wrapper(
        self,
        job_id: str,
        target_fn: Callable[..., Any],
        *args: Any,
        **kwargs: Any,
    ) -> None:
        """Wrapper executed inside the worker thread to record lifecycle transitions."""
        with self._lock:
            job = self._jobs.get(job_id)
            if not job or job.status == JobStatus.CANCELLED:
                return
            job.status = JobStatus.RUNNING
            job.started_at = datetime.now(timezone.utc)

        logger.info("Job %s started execution in worker thread", job_id)

        try:
            res = target_fn(*args, **kwargs)
            with self._lock:
                job.status = JobStatus.COMPLETED
                job.completed_at = datetime.now(timezone.utc)
                job.result = res
            logger.info("Job %s completed successfully", job_id)
        except Exception as exc:
            logger.exception("Job %s failed with exception: %s", job_id, str(exc))
            with self._lock:
                job.status = JobStatus.FAILED
                job.completed_at = datetime.now(timezone.utc)
                job.error_message = str(exc)

    async def submit_job(
        self,
        job_id: str,
        target_fn: Callable[..., Any],
        *args: Any,
        **kwargs: Any,
    ) -> JobInfo:
        with self._lock:
            if job_id in self._jobs and self._jobs[job_id].status in (
                JobStatus.PENDING,
                JobStatus.RUNNING,
            ):
                raise ValueError(f"Job with id '{job_id}' is already active.")

            job = JobInfo(job_id=job_id, status=JobStatus.PENDING)
            self._jobs[job_id] = job

            future = self._executor.submit(
                self._execute_wrapper,
                job_id,
                target_fn,
                *args,
                **kwargs,
            )
            self._futures[job_id] = future

        return job

    async def get_job_status(self, job_id: str) -> Optional[JobInfo]:
        with self._lock:
            job = self._jobs.get(job_id)
            if not job:
                return None
            return JobInfo(
                job_id=job.job_id,
                status=job.status,
                created_at=job.created_at,
                started_at=job.started_at,
                completed_at=job.completed_at,
                error_message=job.error_message,
                result=job.result,
            )

    async def cancel_job(self, job_id: str) -> bool:
        with self._lock:
            future = self._futures.get(job_id)
            job = self._jobs.get(job_id)
            if not future or not job:
                return False

            if future.cancel():
                job.status = JobStatus.CANCELLED
                job.completed_at = datetime.now(timezone.utc)
                logger.info("Job %s was cancelled before execution started", job_id)
                return True
            return False

    async def shutdown(self, wait: bool = True) -> None:
        logger.info("Shutting down ThreadPoolJobRunner executor...")
        self._executor.shutdown(wait=wait, cancel_futures=True)
