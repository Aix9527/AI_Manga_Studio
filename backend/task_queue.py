"""
AI Manga Studio Pro V1.0 — Task Queue

Redis-backed asynchronous task queue for ComfyUI job submission,
GPU monitoring, and automatic work distribution.

Supports:
- Priority-based job submission
- GPU idle detection and auto-execution
- Job status tracking (pending → running → done / failed)
- Concurrent job limiting based on VRAM availability
- Job cancellation and retry
"""

from __future__ import annotations

import json
import threading
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

from loguru import logger

from backend.config import get_config


# ============================================================
# Enums
# ============================================================

class TaskStatus(str, Enum):
    pending = "pending"
    running = "running"
    done = "done"
    failed = "failed"
    cancelled = "cancelled"


class TaskPriority(int, Enum):
    low = 0
    normal = 5
    high = 10
    critical = 20


# ============================================================
# Data Classes
# ============================================================

@dataclass
class GPUMetrics:
    """GPU hardware metrics."""
    gpu_name: str = ""
    vram_total_mb: int = 0
    vram_used_mb: int = 0
    vram_free_mb: int = 0
    utilization_pct: float = 0.0
    temperature_c: float = 0.0
    power_watts: float = 0.0
    is_idle: bool = True


@dataclass
class Task:
    """A single task in the queue."""
    task_id: str = ""
    task_type: str = ""  # e.g., "txt2img", "img2img", "i2v"
    priority: TaskPriority = TaskPriority.normal
    status: TaskStatus = TaskStatus.pending
    payload: Dict[str, Any] = field(default_factory=dict)
    result: Optional[Dict[str, Any]] = None
    error_message: str = ""
    created_at: float = 0.0
    started_at: float = 0.0
    completed_at: float = 0.0
    retries: int = 0
    max_retries: int = 3
    callback: Optional[Callable] = None


# ============================================================
# Task Queue Engine
# ============================================================

class TaskQueue:
    """In-memory priority task queue with GPU awareness.

    Production deployment uses Redis for persistence and
    multi-worker coordination. This in-memory implementation
    serves as the core logic for single-machine operation.
    """

    MAX_CONCURRENT_TASKS: int = 2  # Max simultaneous ComfyUI jobs

    def __init__(
        self,
        redis_url: str = "",
        max_concurrent: int = 2,
        poll_interval: float = 1.0,
        gpu_idle_threshold: float = 10.0,
    ) -> None:
        """Initialize the task queue.

        Args:
            redis_url: Redis connection URL (empty = in-memory mode).
            max_concurrent: Maximum concurrent tasks.
            poll_interval: Polling interval in seconds.
            gpu_idle_threshold: GPU utilization % below which GPU is "idle".
        """
        self.redis_url = redis_url
        self.max_concurrent = max_concurrent
        self.poll_interval = poll_interval
        self.gpu_idle_threshold = gpu_idle_threshold

        # In-memory storage
        self._queue: List[Task] = []
        self._history: Dict[str, Task] = {}
        self._lock = threading.Lock()

        # Worker thread
        self._worker: Optional[threading.Thread] = None
        self._running = False

        # Redis client (lazy init)
        self._redis = None

        # Metrics
        self.gpu_metrics = GPUMetrics()

        # Callbacks
        self._on_task_start: Optional[Callable] = None
        self._on_task_complete: Optional[Callable] = None

        logger.info(f"TaskQueue: Initialized (concurrent={max_concurrent}, in_memory={not bool(redis_url)})")

    # ----------------------------------------------------------
    # Public API
    # ----------------------------------------------------------

    def submit(
        self,
        task_type: str,
        payload: Dict[str, Any],
        priority: TaskPriority = TaskPriority.normal,
        callback: Optional[Callable] = None,
    ) -> Task:
        """Submit a task to the queue.

        Args:
            task_type: Type of task (txt2img, img2img, i2v, etc.).
            payload: Task parameters.
            priority: Task priority.
            callback: Optional callback on completion.

        Returns:
            The created Task object.
        """
        task = Task(
            task_id=str(uuid.uuid4())[:12],
            task_type=task_type,
            priority=priority,
            status=TaskStatus.pending,
            payload=payload,
            callback=callback,
            created_at=time.time(),
        )

        with self._lock:
            self._queue.append(task)
            # Sort by priority (descending)
            self._queue.sort(key=lambda t: t.priority.value, reverse=True)

        logger.info(f"TaskQueue: Submitted '{task_type}' (id={task.task_id}, priority={priority.name})")
        return task

    def start(self) -> None:
        """Start the worker thread."""
        if self._running:
            logger.warning("TaskQueue: Worker already running")
            return

        self._running = True
        self._worker = threading.Thread(target=self._worker_loop, daemon=True)
        self._worker.start()
        logger.info("TaskQueue: Worker started")

    def stop(self, wait: bool = True) -> None:
        """Stop the worker thread.

        Args:
            wait: Whether to wait for running tasks to finish.
        """
        self._running = False
        if self._worker and wait:
            self._worker.join(timeout=30)
        logger.info("TaskQueue: Worker stopped")

    def cancel(self, task_id: str) -> bool:
        """Cancel a pending task.

        Args:
            task_id: Task ID.

        Returns:
            True if cancelled, False if not found.
        """
        with self._lock:
            for task in self._queue:
                if task.task_id == task_id and task.status == TaskStatus.pending:
                    task.status = TaskStatus.cancelled
                    self._queue.remove(task)
                    self._history[task_id] = task
                    logger.info(f"TaskQueue: Cancelled task {task_id}")
                    return True
        return False

    def get_task(self, task_id: str) -> Optional[Task]:
        """Get a task by ID.

        Args:
            task_id: Task ID.

        Returns:
            Task or None.
        """
        with self._lock:
            for task in self._queue:
                if task.task_id == task_id:
                    return task
        return self._history.get(task_id)

    def get_queue_status(self) -> Dict[str, Any]:
        """Get current queue status.

        Returns:
            Dict with queue stats.
        """
        with self._lock:
            pending = sum(1 for t in self._queue if t.status == TaskStatus.pending)
            running = sum(1 for t in self._queue if t.status == TaskStatus.running)
            done = sum(1 for t in self._history.values() if t.status == TaskStatus.done)
            failed = sum(1 for t in self._history.values() if t.status == TaskStatus.failed)

        return {
            "pending": pending,
            "running": running,
            "done": done,
            "failed": failed,
            "gpu_idle": self.gpu_metrics.is_idle,
            "gpu_utilization": self.gpu_metrics.utilization_pct,
            "vram_free_mb": self.gpu_metrics.vram_free_mb,
        }

    def register_callbacks(
        self,
        on_task_start: Optional[Callable] = None,
        on_task_complete: Optional[Callable] = None,
    ) -> None:
        """Register callbacks for task lifecycle events.

        Args:
            on_task_start: Callback(Task).
            on_task_complete: Callback(Task).
        """
        self._on_task_start = on_task_start
        self._on_task_complete = on_task_complete

    # ----------------------------------------------------------
    # GPU Monitoring
    # ----------------------------------------------------------

    def update_gpu_metrics(self) -> GPUMetrics:
        """Query GPU hardware and update metrics.

        Returns:
            Updated GPUMetrics.
        """
        try:
            metrics = self._query_gpu_nvidia_smi()
            if metrics:
                self.gpu_metrics = metrics
            else:
                # Fallback: assume idle with unknown VRAM
                self.gpu_metrics.is_idle = True
        except Exception as e:
            logger.debug(f"TaskQueue: GPU query failed: {e}")
            self.gpu_metrics.is_idle = True  # Assume idle on failure

        return self.gpu_metrics

    def is_gpu_idle(self) -> bool:
        """Check if GPU is idle enough to accept new tasks.

        Returns:
            True if GPU is idle.
        """
        self.update_gpu_metrics()
        return (
            self.gpu_metrics.utilization_pct < self.gpu_idle_threshold
            and self.gpu_metrics.vram_free_mb > 2048  # at least 2GB free
        )

    # ----------------------------------------------------------
    # Worker Loop
    # ----------------------------------------------------------

    def _worker_loop(self) -> None:
        """Main worker loop: poll GPU, dispatch tasks."""
        logger.info("TaskQueue: Worker loop started")

        while self._running:
            try:
                # Update GPU status
                self.update_gpu_metrics()

                # Check for tasks that can run
                active_count = self._count_running()
                if active_count < self.max_concurrent and self.is_gpu_idle():
                    self._dispatch_next()

                time.sleep(self.poll_interval)

            except Exception as e:
                logger.error(f"TaskQueue: Worker loop error: {e}")
                time.sleep(self.poll_interval)

    def _count_running(self) -> int:
        """Count currently running tasks.

        Returns:
            Number of running tasks.
        """
        with self._lock:
            return sum(1 for t in self._queue if t.status == TaskStatus.running)

    def _dispatch_next(self) -> None:
        """Dispatch the next pending task."""
        with self._lock:
            pending = [t for t in self._queue if t.status == TaskStatus.pending]
            if not pending:
                return

            # Pick highest priority pending task
            task = pending[0]
            task.status = TaskStatus.running
            task.started_at = time.time()

        if self._on_task_start:
            self._on_task_start(task)

        logger.info(f"TaskQueue: Dispatching task {task.task_id} ({task.task_type})")

        # Process in background thread
        thread = threading.Thread(
            target=self._execute_task,
            args=(task,),
            daemon=True,
        )
        thread.start()

    def _execute_task(self, task: Task) -> None:
        """Execute a task.

        In production, this would connect to ComfyUI via API.
        For now, it's a stub that simulates execution.

        Args:
            task: The task to execute.
        """
        try:
            # Simulate task execution
            # In production: self.comfyui_client.submit_workflow(task.payload)
            logger.info(f"TaskQueue: Executing task {task.task_id}...")
            time.sleep(0.5)  # Simulated work

            task.status = TaskStatus.done
            task.result = {"output": f"Task {task.task_id} completed"}
            task.completed_at = time.time()

            logger.info(f"TaskQueue: Task {task.task_id} done")

        except Exception as e:
            task.status = TaskStatus.failed
            task.error_message = str(e)
            task.completed_at = time.time()
            logger.error(f"TaskQueue: Task {task.task_id} failed: {e}")

        finally:
            with self._lock:
                if task in self._queue:
                    self._queue.remove(task)
                self._history[task.task_id] = task

            if self._on_task_complete:
                self._on_task_complete(task)

            if task.callback:
                try:
                    task.callback(task)
                except Exception as cb_err:
                    logger.error(f"TaskQueue: Callback error for {task.task_id}: {cb_err}")

    # ----------------------------------------------------------
    # GPU Query (NVIDIA SMI)
    # ----------------------------------------------------------

    def _query_gpu_nvidia_smi(self) -> Optional[GPUMetrics]:
        """Query GPU metrics using nvidia-smi.

        Returns:
            GPUMetrics or None if nvidia-smi unavailable.
        """
        import subprocess

        try:
            result = subprocess.run(
                [
                    "nvidia-smi",
                    "--query-gpu=name,memory.total,memory.used,memory.free,utilization.gpu,temperature.gpu,power.draw",
                    "--format=csv,noheader,nounits",
                ],
                capture_output=True,
                text=True,
                timeout=10,
            )

            if result.returncode != 0:
                return None

            line = result.stdout.strip().split(",")
            if len(line) < 7:
                return None

            return GPUMetrics(
                gpu_name=line[0].strip(),
                vram_total_mb=int(float(line[1].strip())),
                vram_used_mb=int(float(line[2].strip())),
                vram_free_mb=int(float(line[3].strip())),
                utilization_pct=float(line[4].strip()),
                temperature_c=float(line[5].strip()),
                power_watts=float(line[6].strip()),
                is_idle=float(line[4].strip()) < self.gpu_idle_threshold,
            )
        except (FileNotFoundError, subprocess.TimeoutExpired, ValueError):
            return None
