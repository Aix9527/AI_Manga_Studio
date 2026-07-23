"""
Worker Lease Manager (Part 8 / Part 12)

Distributed lease mechanism to ensure exactly-once processing
of jobs across multiple worker instances. Uses database-backed
leases with periodic heartbeat renewal.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Optional
from uuid import uuid4


logger = logging.getLogger(__name__)


@dataclass
class Lease:
    """Represents an exclusive lock on a job for a worker."""

    lease_id: str = field(default_factory=lambda: str(uuid4()))
    job_id: str = ""
    worker_id: str = ""
    acquired_at: float = field(default_factory=time.time)
    expires_at: float = 0.0
    heartbeat_interval: int = 30  # seconds


class LeaseManager:
    """
    Manages distributed leases for job processing.

    MVP: In-memory lease tracking
    Production: Database-backed with heartbeat updates

    Ensures:
    - Only one worker processes a job at a time
    - Expired leases are released for re-claiming
    - Heartbeat renewal keeps long-running jobs alive
    """

    def __init__(self) -> None:
        self._leases: dict[str, Lease] = {}  # job_id -> Lease
        self._heartbeat_tasks: dict[str, asyncio.Task] = {}
        self._lock = asyncio.Lock()

    async def acquire(
        self,
        job_id: str,
        worker_id: str,
        timeout_seconds: int = 300,
    ) -> Optional[Lease]:
        """
        Attempt to acquire a lease on a job.

        Returns the Lease if acquired, None if already leased.
        Leases auto-expire after timeout_seconds.
        """
        async with self._lock:
            # Check existing lease
            existing = self._leases.get(job_id)
            if existing and existing.expires_at > time.time():
                logger.debug(
                    "Job %s already leased by worker %s",
                    job_id,
                    existing.worker_id,
                )
                return None

            # Acquire new lease
            lease = Lease(
                job_id=job_id,
                worker_id=worker_id,
                acquired_at=time.time(),
                expires_at=time.time() + timeout_seconds,
            )
            self._leases[job_id] = lease

            # Start heartbeat
            self._heartbeat_tasks[job_id] = asyncio.create_task(
                self._heartbeat(job_id, lease.heartbeat_interval, timeout_seconds)
            )

            logger.debug("Lease acquired: job=%s worker=%s", job_id, worker_id)
            return lease

    async def release(self, job_id: str) -> None:
        """Release a lease on a job."""
        async with self._lock:
            self._leases.pop(job_id, None)
            task = self._heartbeat_tasks.pop(job_id, None)
            if task:
                task.cancel()
            logger.debug("Lease released: job=%s", job_id)

    async def renew(self, job_id: str, extension_seconds: int = 300) -> bool:
        """Extend a lease. Returns True if successful."""
        async with self._lock:
            lease = self._leases.get(job_id)
            if not lease:
                return False
            lease.expires_at = time.time() + extension_seconds
            return True

    async def _heartbeat(
        self, job_id: str, interval: int, timeout: int
    ) -> None:
        """Periodically renew the lease."""
        try:
            while True:
                await asyncio.sleep(interval)
                ok = await self.renew(job_id, timeout)
                if not ok:
                    break
        except asyncio.CancelledError:
            pass

    async def cleanup_expired(self) -> int:
        """Remove all expired leases. Returns count of cleaned leases."""
        now = time.time()
        async with self._lock:
            expired = [
                jid
                for jid, lease in self._leases.items()
                if lease.expires_at < now
            ]
            for jid in expired:
                self._leases.pop(jid)
                task = self._heartbeat_tasks.pop(jid, None)
                if task:
                    task.cancel()
            if expired:
                logger.info("Cleaned %d expired leases", len(expired))
            return len(expired)
