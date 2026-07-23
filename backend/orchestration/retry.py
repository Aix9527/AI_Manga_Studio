"""
Retry & Rollback Strategies (Part 8 / Part 12)

Configurable retry policies with exponential backoff, jitter,
and rollback strategies for failed workflow nodes and jobs.
"""

from __future__ import annotations

import asyncio
import logging
import random
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Optional


logger = logging.getLogger(__name__)


class RetryDecision(Enum):
    """Outcome of a retry evaluation."""
    RETRY = "retry"
    SKIP = "skip"
    FAIL = "fail"
    FALLBACK = "fallback"


@dataclass
class RetryPolicy:
    """
    Configures retry behavior for jobs and workflow nodes.

    Supports exponential backoff with optional jitter to avoid
    thundering herd problems.
    """

    max_attempts: int = 3
    base_delay_seconds: float = 5.0
    backoff_multiplier: float = 2.0
    max_delay_seconds: float = 300.0
    jitter: bool = True
    retryable_exceptions: tuple[type[Exception], ...] = (Exception,)

    def compute_delay(self, attempt: int) -> float:
        """Calculate delay for the Nth retry attempt (1-based)."""
        delay = self.base_delay_seconds * (
            self.backoff_multiplier ** (attempt - 1)
        )
        delay = min(delay, self.max_delay_seconds)

        if self.jitter:
            delay = delay * (0.5 + random.random())

        return delay

    def should_retry(self, attempt: int, exception: Exception) -> RetryDecision:
        """Determine whether to retry based on attempt count and exception type."""
        if attempt >= self.max_attempts:
            return RetryDecision.FAIL

        if isinstance(exception, self.retryable_exceptions):
            return RetryDecision.RETRY

        return RetryDecision.FAIL


class RetryExecutor:
    """
    Executes an async callable with retry logic.

    Usage:
        executor = RetryExecutor(RetryPolicy(max_attempts=3))
        result = await executor.execute(my_async_func, arg1, arg2)
    """

    def __init__(self, policy: RetryPolicy) -> None:
        self.policy = policy

    async def execute(
        self,
        func: Callable[..., Any],
        *args: Any,
        **kwargs: Any,
    ) -> Any:
        """Execute func with retries. Raises last exception on exhaustion."""
        last_exception: Optional[Exception] = None

        for attempt in range(1, self.policy.max_attempts + 1):
            try:
                result = await func(*args, **kwargs)
                return result
            except Exception as exc:
                last_exception = exc
                decision = self.policy.should_retry(attempt, exc)

                if decision == RetryDecision.FAIL:
                    raise

                if decision == RetryDecision.SKIP:
                    logger.warning("Skipping retry for %s", func.__name__)
                    raise

                delay = self.policy.compute_delay(attempt)
                logger.warning(
                    "Retry %d/%d for %s in %.1fs: %s",
                    attempt,
                    self.policy.max_attempts,
                    func.__name__,
                    delay,
                    exc,
                )
                await asyncio.sleep(delay)

        if last_exception:
            raise last_exception


# ── Rollback ─────────────────────────────────────────────────────────────


class RollbackManager:
    """
    Manages compensation actions for failed workflows.

    Each node can register a rollback handler that is invoked
    in reverse topological order if the workflow fails.
    """

    def __init__(self) -> None:
        self._handlers: dict[str, Callable[..., Any]] = {}

    def register(self, node_id: str, handler: Callable[..., Any]) -> None:
        """Register a rollback handler for a node."""
        self._handlers[node_id] = handler

    async def rollback(
        self, completed_nodes: list[str], context: dict[str, Any]
    ) -> None:
        """
        Execute rollback handlers in reverse order.

        Each handler is invoked; failures in one handler do not
        prevent subsequent handlers from executing.
        """
        for node_id in reversed(completed_nodes):
            handler = self._handlers.get(node_id)
            if handler:
                try:
                    result = handler(context)
                    if asyncio.iscoroutine(result):
                        await result
                    logger.info("Rollback completed for node %s", node_id)
                except Exception as exc:
                    logger.error(
                        "Rollback failed for node %s: %s", node_id, exc
                    )
