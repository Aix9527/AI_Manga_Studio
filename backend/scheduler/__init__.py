"""
Scheduler — Cron-based task scheduling (Part 8)

Manages recurring tasks such as:
- Cache cleanup
- Health checks
- Index rebuilds
- Stale job cleanup
- Provider status polling
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Callable, Coroutine

logger = logging.getLogger(__name__)


class ScheduleInterval(Enum):
    """Schedule interval types."""
    MINUTE = "minute"
    HOUR = "hour"
    DAY = "day"
    WEEK = "week"
    CUSTOM = "custom"


@dataclass
class ScheduledTask:
    """A single scheduled task definition."""
    name: str
    interval: ScheduleInterval = ScheduleInterval.HOUR
    interval_value: int = 1
    handler: Callable[..., Coroutine[Any, Any, None]] | None = None
    enabled: bool = True
    last_run: datetime | None = None
    next_run: datetime | None = None
    run_count: int = 0
    error_count: int = 0


class Scheduler:
    """
    Lightweight task scheduler with asyncio.

    Supports:
    - Fixed-interval scheduling
    - Manual triggering
    - Error isolation (one failing task doesn't crash scheduler)
    - Task statistics tracking
    """

    def __init__(self) -> None:
        self._tasks: dict[str, ScheduledTask] = {}
        self._running: bool = False
        self._main_task: asyncio.Task | None = None

    def register(
        self,
        name: str,
        handler: Callable[..., Coroutine[Any, Any, None]],
        interval: ScheduleInterval = ScheduleInterval.HOUR,
        interval_value: int = 1,
    ) -> ScheduledTask:
        """Register a new scheduled task."""
        task = ScheduledTask(
            name=name,
            interval=interval,
            interval_value=interval_value,
            handler=handler,
            next_run=datetime.now(),
        )
        self._tasks[name] = task
        logger.info(f"Registered scheduled task: {name}")
        return task

    def unregister(self, name: str) -> bool:
        """Remove a scheduled task."""
        if name in self._tasks:
            del self._tasks[name]
            return True
        return False

    async def start(self) -> None:
        """Start the scheduler loop."""
        if self._running:
            return
        self._running = True
        self._main_task = asyncio.create_task(self._loop())
        logger.info("Scheduler started")

    async def stop(self) -> None:
        """Stop the scheduler loop."""
        self._running = False
        if self._main_task:
            self._main_task.cancel()
            try:
                await self._main_task
            except asyncio.CancelledError:
                pass
        logger.info("Scheduler stopped")

    async def trigger(self, name: str) -> bool:
        """Manually trigger a scheduled task."""
        task = self._tasks.get(name)
        if not task or not task.handler:
            return False
        await self._run_task(task)
        return True

    async def _loop(self) -> None:
        """Main scheduler loop."""
        while self._running:
            now = datetime.now()
            for task in self._tasks.values():
                if not task.enabled or not task.handler:
                    continue
                if task.next_run and now >= task.next_run:
                    await self._run_task(task)
                    # Schedule next run
                    task.next_run = self._calculate_next_run(task)

            await asyncio.sleep(10)  # Check every 10 seconds

    async def _run_task(self, task: ScheduledTask) -> None:
        """Execute a single task with error handling."""
        if not task.handler:
            return
        try:
            await task.handler()
            task.last_run = datetime.now()
            task.run_count += 1
        except Exception as e:
            task.error_count += 1
            logger.error(f"Scheduled task '{task.name}' failed: {e}", exc_info=True)

    @staticmethod
    def _calculate_next_run(task: ScheduledTask) -> datetime:
        """Calculate the next run time."""
        now = datetime.now()
        if task.interval == ScheduleInterval.MINUTE:
            return now + timedelta(minutes=task.interval_value)
        elif task.interval == ScheduleInterval.HOUR:
            return now + timedelta(hours=task.interval_value)
        elif task.interval == ScheduleInterval.DAY:
            return now + timedelta(days=task.interval_value)
        elif task.interval == ScheduleInterval.WEEK:
            return now + timedelta(weeks=task.interval_value)
        return now + timedelta(hours=1)

    def get_stats(self) -> dict[str, Any]:
        """Get scheduler statistics."""
        return {
            "running": self._running,
            "task_count": len(self._tasks),
            "tasks": {
                name: {
                    "enabled": t.enabled,
                    "run_count": t.run_count,
                    "error_count": t.error_count,
                    "last_run": t.last_run.isoformat() if t.last_run else None,
                    "next_run": t.next_run.isoformat() if t.next_run else None,
                }
                for name, t in self._tasks.items()
            },
        }
