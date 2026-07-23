"""
Priority Job Queue (Part 8 / Part 12)

A priority-aware async job queue that supports:
- Priority ordering (higher priority first)
- FIFO within same priority
- Capacity limits
- Visibility timeout (lease)
- Dead letter queue for poison messages
"""

from __future__ import annotations

import asyncio
import heapq
import logging
import time
from dataclasses import dataclass, field
from typing import Optional

from backend.orchestration.job_manager import Job, JobStatus


logger = logging.getLogger(__name__)


@dataclass(order=True)
class _PrioritizedJob:
    """Heap-friendly wrapper: negative priority for max-heap behavior."""
    neg_priority: int
    enqueued_at: float = field(compare=True)
    job: Job = field(compare=False)


class JobQueue:
    """
    Priority job queue backed by a heap.

    Supports:
    - Enqueue with priority
    - Dequeue (FIFO within same priority)
    - Peek without removal
    - Lease-based visibility timeout
    - Dead letter queue for jobs that exceed max retries
    """

    def __init__(self, max_size: int = 10000) -> None:
        self._heap: list[_PrioritizedJob] = []
        self._lock = asyncio.Lock()
        self._max_size = max_size
        self._leased: dict[str, float] = {}  # job_id -> lease expiry
        self._dlq: list[Job] = []

    async def enqueue(self, job: Job) -> None:
        """Add a job to the queue with its configured priority."""
        async with self._lock:
            if len(self._heap) >= self._max_size:
                raise QueueFullError(f"Queue at capacity ({self._max_size})")

            wrapped = _PrioritizedJob(
                neg_priority=-job.priority,
                enqueued_at=time.time(),
                job=job,
            )
            heapq.heappush(self._heap, wrapped)
            job.status = JobStatus.QUEUED
            logger.debug("Job %s enqueued (priority=%d)", job.job_id, job.priority)

    async def dequeue(self) -> Optional[Job]:
        """Remove and return the next job (highest priority, earliest)."""
        async with self._lock:
            now = time.time()

            # Expire stale leases
            expired = [
                jid
                for jid, expiry in self._leased.items()
                if expiry < now
            ]
            for jid in expired:
                del self._leased[jid]

            while self._heap:
                wrapped = heapq.heappop(self._heap)
                if wrapped.job.job_id not in self._leased:
                    return wrapped.job
                # Re-enqueue leased jobs (shouldn't happen normally)
                heapq.heappush(self._heap, wrapped)

            return None

    async def peek(self) -> Optional[Job]:
        """Return the next job without removing it."""
        async with self._lock:
            if self._heap:
                return self._heap[0].job
            return None

    async def lease(self, job_id: str, timeout_seconds: int = 300) -> bool:
        """Acquire a lease on a job (visibility timeout)."""
        async with self._lock:
            if job_id in self._leased:
                if self._leased[job_id] > time.time():
                    return False  # Already leased
            self._leased[job_id] = time.time() + timeout_seconds
            return True

    async def release_lease(self, job_id: str) -> None:
        """Release the lease on a job."""
        async with self._lock:
            self._leased.pop(job_id, None)

    async def move_to_dlq(self, job: Job) -> None:
        """Move a poison job to the dead letter queue."""
        async with self._lock:
            self._dlq.append(job)
            logger.warning(
                "Job %s moved to DLQ after %d retries",
                job.job_id,
                job.retry_count,
            )

    async def drain_dlq(self) -> list[Job]:
        """Retrieve and clear the dead letter queue."""
        async with self._lock:
            jobs = self._dlq[:]
            self._dlq.clear()
            return jobs

    @property
    async def size(self) -> int:
        async with self._lock:
            return len(self._heap)

    @property
    async def is_empty(self) -> bool:
        return await self.size == 0


class QueueFullError(Exception):
    """Raised when the job queue has reached max capacity."""
    pass
