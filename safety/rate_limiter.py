"""
Rate Limiter - Prevent runaway operations
"""

from datetime import datetime, timedelta
from collections import defaultdict
from typing import Optional
import threading


class RateLimiter:
    """
    Limits the rate of operations to prevent runaway behavior.

    Tracks operations per hour and blocks when limits are exceeded.
    """

    # Default limits per hour
    DEFAULT_LIMITS = {
        "claude_query": 100,
        "git_commit": 20,
        "file_write": 50,
        "docker_deploy": 5,
        "pr_create": 10,
        "file_read": 500,
        "test_run": 20,
    }

    def __init__(self, limits: Optional[dict] = None):
        self.limits = {**self.DEFAULT_LIMITS, **(limits or {})}
        self._counts: dict[str, list[datetime]] = defaultdict(list)
        self._lock = threading.Lock()

    def _cleanup_old(self, operation: str):
        """Remove timestamps older than 1 hour."""
        cutoff = datetime.now() - timedelta(hours=1)
        self._counts[operation] = [ts for ts in self._counts[operation] if ts > cutoff]

    def check(self, operation: str) -> bool:
        """
        Check if an operation is allowed.

        Args:
            operation: The operation type (e.g., "claude_query", "git_commit")

        Returns:
            True if allowed, False if rate limited
        """
        with self._lock:
            self._cleanup_old(operation)
            limit = self.limits.get(operation, 100)
            return len(self._counts[operation]) < limit

    def record(self, operation: str) -> bool:
        """
        Record an operation and return whether it was allowed.

        Args:
            operation: The operation type

        Returns:
            True if operation was recorded, False if rate limited
        """
        with self._lock:
            self._cleanup_old(operation)
            limit = self.limits.get(operation, 100)

            if len(self._counts[operation]) >= limit:
                return False

            self._counts[operation].append(datetime.now())
            return True

    def get_remaining(self, operation: str) -> int:
        """Get remaining allowed operations for this hour."""
        with self._lock:
            self._cleanup_old(operation)
            limit = self.limits.get(operation, 100)
            return max(0, limit - len(self._counts[operation]))

    def get_wait_time(self, operation: str) -> Optional[float]:
        """
        Get seconds to wait before operation is allowed.

        Returns:
            Seconds to wait, or None if operation is allowed now
        """
        with self._lock:
            self._cleanup_old(operation)
            limit = self.limits.get(operation, 100)

            if len(self._counts[operation]) < limit:
                return None

            # Find the oldest timestamp that will expire
            oldest = min(self._counts[operation])
            wait_until = oldest + timedelta(hours=1)
            wait_seconds = (wait_until - datetime.now()).total_seconds()

            return max(0, wait_seconds)

    def get_stats(self) -> dict:
        """Get current rate limit statistics."""
        with self._lock:
            stats = {}
            for operation in self.limits:
                self._cleanup_old(operation)
                stats[operation] = {
                    "used": len(self._counts[operation]),
                    "limit": self.limits[operation],
                    "remaining": self.get_remaining(operation),
                }
            return stats

    def reset(self, operation: Optional[str] = None):
        """Reset rate limit counters."""
        with self._lock:
            if operation:
                self._counts[operation] = []
            else:
                self._counts.clear()


class RateLimitExceeded(Exception):
    """Raised when rate limit is exceeded."""

    def __init__(self, operation: str, wait_seconds: float):
        self.operation = operation
        self.wait_seconds = wait_seconds
        super().__init__(f"Rate limit exceeded for {operation}. " f"Wait {wait_seconds:.0f} seconds.")
