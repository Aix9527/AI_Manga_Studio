"""
Worker — Job execution engine (Part 12)

Pool-based async worker that dequeues jobs from the priority queue,
executes them within DAG workflow context, handles checkpoints and retries.

Design:
- Workers pull from a shared JobQueue
- Each worker executes one job at a time
- Workers report progress via event bus
- Workers handle graceful shutdown
- Workers delegate execution to the WorkflowExecutor
"""

from __future__ import annotations

import asyncio
import logging
import signal
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from backend.orchestration.queue import JobQueue
from backend.orchestration.retry import RetryPolicy
from backend.orchestration.checkpoint import CheckpointManager
from backend.workflow.executor import WorkflowExecutor
from backend.events import event_bus, JobEvent

logger = logging.getLogger(__name__)


@dataclass
class WorkerConfig:
    """Worker pool configuration."""
    num_workers: int = 4
    poll_interval_seconds: float = 0.5
    graceful_shutdown_timeout: float = 30.0


@dataclass
class WorkerStats:
    """Per-worker statistics."""
    worker_id: str = ""
    jobs_completed: int = 0
    jobs_failed: int = 0
    current_job_id: str = ""
    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    last_active: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class Worker:
    """
    Individual worker that pulls jobs from queue and executes them.

    Each worker is an asyncio-based event loop that:
    1. Dequeues the next available job
    2. Resolves the DAG workflow for that job
    3. Executes nodes one at a time (or parallel where possible)
    4. Saves checkpoints between nodes
    5. Publishes progress events
    6. Handles failures and retries
    """

    def __init__(
        self,
        worker_id: str,
        queue: JobQueue,
        executor: WorkflowExecutor,
        checkpoint_manager: CheckpointManager,
        poll_interval: float = 0.5,
    ) -> None:
        self.worker_id = worker_id
        self._queue = queue
        self._executor = executor
        self._checkpoints = checkpoint_manager
        self._poll_interval = poll_interval
        self._running = False
        self._current_task: asyncio.Task | None = None
        self._stats = WorkerStats(worker_id=worker_id)

    @property
    def stats(self) -> WorkerStats:
        return self._stats

    async def start(self) -> None:
        """Start the worker loop."""
        self._running = True
        logger.info(f"Worker {self.worker_id} started")
        self._current_task = asyncio.create_task(self._loop())

    async def stop(self) -> None:
        """Gracefully stop the worker."""
        self._running = False
        if self._current_task:
            self._current_task.cancel()
            try:
                await self._current_task
            except asyncio.CancelledError:
                pass
        logger.info(f"Worker {self.worker_id} stopped. Stats: {self._stats}")

    async def _loop(self) -> None:
        """Main worker loop: dequeue -> execute -> repeat."""
        while self._running:
            try:
                job = await self._queue.dequeue()
                if job is None:
                    await asyncio.sleep(self._poll_interval)
                    continue

                self._stats.current_job_id = job.job_id
                self._stats.last_active = datetime.now(timezone.utc)

                await self._execute_job(job)

                self._stats.current_job_id = ""
                self._stats.last_active = datetime.now(timezone.utc)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Worker {self.worker_id} loop error: {e}", exc_info=True)
                await asyncio.sleep(1)

    async def _execute_job(self, job: Any) -> None:
        """Execute a single job through the workflow executor."""
        job_id = getattr(job, "job_id", str(job))

        # Publish started event
        await event_bus.publish(
            JobEvent(
                job_id=job_id,
                payload={"action": "started", "worker_id": self.worker_id},
            )
        )

        try:
            # Check for existing checkpoint to resume
            checkpoint = await self._checkpoints.load(job_id)
            if checkpoint:
                logger.info(f"Resuming job {job_id} from checkpoint: {checkpoint}")

            # Execute via the workflow executor
            result = await self._executor.execute(
                job=job,
                checkpoint=checkpoint,
                on_progress=lambda p: self._report_progress(job_id, p),
            )

            self._stats.jobs_completed += 1

            # Publish completed event
            await event_bus.publish(
                JobEvent(
                    job_id=job_id,
                    payload={"action": "completed", "result": result},
                )
            )

        except Exception as e:
            self._stats.jobs_failed += 1
            logger.error(f"Job {job_id} failed: {e}", exc_info=True)

            # Publish failed event
            await event_bus.publish(
                JobEvent(
                    job_id=job_id,
                    payload={"action": "failed", "error": str(e)},
                )
            )

            # Check retry policy
            retry_policy = RetryPolicy()
            should_retry = await retry_policy.should_retry(job, e)
            if should_retry:
                await self._queue.enqueue(job)
                logger.info(f"Job {job_id} re-queued for retry")

    async def _report_progress(self, job_id: str, progress: float) -> None:
        """Report job progress via event bus."""
        await event_bus.publish(
            JobEvent(
                job_id=job_id,
                payload={
                    "action": "progress",
                    "progress": progress,
                    "worker_id": self.worker_id,
                },
            )
        )


class WorkerPool:
    """
    Manages a pool of Worker instances.

    Provides:
    - Worker lifecycle management (start all / stop all)
    - Health monitoring
    - Graceful shutdown on SIGTERM/SIGINT
    """

    def __init__(
        self,
        config: WorkerConfig,
        queue: JobQueue,
        executor: WorkflowExecutor,
        checkpoint_manager: CheckpointManager,
    ) -> None:
        self._config = config
        self._queue = queue
        self._executor = executor
        self._checkpoints = checkpoint_manager
        self._workers: dict[str, Worker] = {}

    async def start(self) -> None:
        """Start all workers."""
        for i in range(self._config.num_workers):
            worker_id = f"worker-{i:03d}"
            worker = Worker(
                worker_id=worker_id,
                queue=self._queue,
                executor=self._executor,
                checkpoint_manager=self._checkpoints,
                poll_interval=self._config.poll_interval_seconds,
            )
            self._workers[worker_id] = worker
            await worker.start()

        logger.info(f"WorkerPool started with {len(self._workers)} workers")

        # Setup signal handlers for graceful shutdown
        for sig in (signal.SIGTERM, signal.SIGINT):
            try:
                asyncio.get_event_loop().add_signal_handler(sig, self._handle_shutdown)
            except NotImplementedError:
                pass  # Windows doesn't support add_signal_handler

    async def stop(self) -> None:
        """Gracefully stop all workers."""
        logger.info("Shutting down worker pool...")
        stop_tasks = [w.stop() for w in self._workers.values()]
        if stop_tasks:
            await asyncio.wait(stop_tasks, timeout=self._config.graceful_shutdown_timeout)
        self._workers.clear()
        logger.info("WorkerPool shut down")

    def _handle_shutdown(self) -> None:
        """Handle OS signal for graceful shutdown."""
        asyncio.create_task(self.stop())

    def get_stats(self) -> dict[str, Any]:
        """Get aggregated worker statistics."""
        return {
            "total_workers": len(self._workers),
            "workers": {
                wid: {
                    "completed": w.stats.jobs_completed,
                    "failed": w.stats.jobs_failed,
                    "current_job": w.stats.current_job_id,
                    "last_active": w.stats.last_active.isoformat(),
                }
                for wid, w in self._workers.items()
            },
        }

    def get_healthy_count(self) -> int:
        """Return number of workers not stuck."""
        now = datetime.now(timezone.utc)
        healthy = 0
        for w in self._workers.values():
            if (now - w.stats.last_active).total_seconds() < 60:
                healthy += 1
        return healthy
