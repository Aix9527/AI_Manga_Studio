"""
Orchestration Layer — System brain (Part 12)

Job lifecycle management: create, queue, dispatch, execute,
checkpoint, retry, rollback, lease, and schedule.

Components:
    job_manager.py  — Job CRUD and state machine
    queue.py        — Priority job queue
    worker.py       — Pool-based job execution workers
    checkpoint.py   — Checkpoint persistence for resume
    retry.py        — Retry with exponential backoff
    rollback.py     — Reverse-DAG compensation execution
    lease.py        — Distributed lease for exclusive job access
    scheduler.py    — Cron-like recurring task scheduler

All components communicate through the EventBus for
decoupled observability and progress reporting.
"""

from backend.orchestration.job_manager import JobManager
from backend.orchestration.queue import JobQueue
from backend.orchestration.worker import Worker, WorkerPool, WorkerConfig
from backend.orchestration.checkpoint import CheckpointManager
from backend.orchestration.retry import RetryPolicy
from backend.orchestration.rollback import RollbackManager, RollbackPlan, RollbackStatus
from backend.orchestration.lease import LeaseManager

__all__ = [
    "JobManager",
    "JobQueue",
    "Worker",
    "WorkerPool",
    "WorkerConfig",
    "CheckpointManager",
    "RetryPolicy",
    "RollbackManager",
    "RollbackPlan",
    "RollbackStatus",
    "LeaseManager",
]
