"""
Job Scheduler (Part 8 / Part 12)

Provides cron-like scheduling for recurring workflow jobs:
- Scheduled project exports
- Periodic asset cleanup
- Batch generation pipelines
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Callable, Optional

from backend.orchestration.job_manager import JobManager


logger = logging.getLogger(__name__)


@dataclass
class ScheduledTask:
    """A task that runs on a schedule."""

    task_id: str
    name: str
    cron_expression: str = ""  # Simple: "every_1h", "daily_03:00"
    interval_seconds: int = 3600
    handler: Optional[Callable[..., Any]] = None
    enabled: bool = True
    last_run: Optional[datetime] = None
    next_run: Optional[datetime] = None


class TaskScheduler:
    """
    Lightweight in-process task scheduler.

    Supports interval-based and cron-like scheduling.
    Runs in an asyncio background task.
    """

    def __init__(self) -> None:
        self._tasks: dict[str, ScheduledTask] = {}
        self._running: bool = False
        self._task: Optional[asyncio.Task] = None

    def register(self, task: ScheduledTask) -> None:
        """Register a scheduled task."""
        task.next_run = datetime.now() + timedelta(
            seconds=task.interval_seconds
        )
        self._tasks[task.task_id] = task
        logger.info(
            "Scheduled task '%s' registered (interval=%ds)",
            task.name,
            task.interval_seconds,
        )

    def unregister(self, task_id: str) -> None:
        """Remove a scheduled task."""
        self._tasks.pop(task_id, None)

    async def start(self) -> None:
        """Start the scheduler background loop."""
        self._running = True
        self._task = asyncio.create_task(self._loop())
        logger.info("TaskScheduler started (%d tasks)", len(self._tasks))

    async def shutdown(self) -> None:
        """Stop the scheduler gracefully."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("TaskScheduler shut down")

    async def _loop(self) -> None:
        """Main scheduler loop: check every second for due tasks."""
        while self._running:
            now = datetime.now()

            for task in list(self._tasks.values()):
                if not task.enabled:
                    continue
                if task.next_run and now >= task.next_run:
                    asyncio.create_task(self._run_task(task))

            await asyncio.sleep(1)

    async def _run_task(self, task: ScheduledTask) -> None:
        """Execute a single scheduled task."""
        task.last_run = datetime.now()
        task.next_run = task.last_run + timedelta(
            seconds=task.interval_seconds
        )

        try:
            if task.handler:
                result = task.handler()
                if asyncio.iscoroutine(result):
                    await result
                logger.debug("Task '%s' completed", task.name)
        except Exception as exc:
            logger.error("Task '%s' failed: %s", task.name, exc)
