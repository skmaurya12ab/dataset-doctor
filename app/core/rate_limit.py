"""Rate limiting and abuse prevention mechanisms."""

from collections import defaultdict
from datetime import datetime, timezone
import threading
import time
from typing import Dict, List, Tuple
from fastapi import HTTPException, status


class SlidingWindowRateLimiter:
    """Thread-safe sliding-window rate limiter for abuse prevention."""

    def __init__(self):
        # key -> list of float timestamps
        self._events: Dict[str, List[float]] = defaultdict(list)
        self._lock = threading.Lock()

    def check_rate_limit(self, key: str, max_requests: int, window_seconds: int) -> Tuple[bool, int]:
        """Check if request is within limits.

        Returns:
            (allowed: bool, remaining_seconds_to_retry: int)
        """
        now = time.time()
        window_start = now - window_seconds

        with self._lock:
            # Filter out timestamps outside the sliding window
            timestamps = self._events[key]
            valid_timestamps = [t for t in timestamps if t > window_start]
            self._events[key] = valid_timestamps

            if len(valid_timestamps) >= max_requests:
                earliest = valid_timestamps[0]
                retry_after = int(earliest + window_seconds - now) + 1
                return False, max(1, retry_after)

            valid_timestamps.append(now)
            return True, 0

    def enforce(self, key: str, max_requests: int, window_seconds: int, action_name: str = "Request") -> None:
        """Enforce rate limit, raising HTTP 429 if threshold is exceeded."""
        allowed, retry_after = self.check_rate_limit(key, max_requests, window_seconds)
        if not allowed:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"{action_name} limit exceeded. Please try again in {retry_after} seconds.",
                headers={"Retry-After": str(retry_after)},
            )

    def reset(self) -> None:
        """Clear all recorded rate limit windows (useful for test isolation)."""
        with self._lock:
            self._events.clear()


# Global rate limiter singleton
rate_limiter = SlidingWindowRateLimiter()
