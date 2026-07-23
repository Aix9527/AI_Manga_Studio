"""
Rollback — Transactional rollback support (Part 12)

Supports rolling back workflow jobs when they fail or when
users request cancellation. Each workflow node can define
a compensation action. Rollback walks the execution DAG
in reverse, invoking compensation actions for each
completed node.

Key features:
- Reverse-DAG rollback traversal
- Per-node compensation actions
- Partial rollback support (only roll back failed node's dependencies)
- Audit trail for rollback operations
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Coroutine

logger = logging.getLogger(__name__)

CompensationFn = Callable[[dict[str, Any]], Coroutine[Any, Any, None]]


class RollbackStatus(Enum):
    """Status of a rollback operation."""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class RollbackEntry:
    """A single rollback step for a completed node."""
    node_id: str
    node_name: str = ""
    status: RollbackStatus = RollbackStatus.PENDING
    compensation_fn: CompensationFn | None = None
    node_output: dict[str, Any] = field(default_factory=dict)
    error: str = ""
    rolled_back_at: datetime | None = None


@dataclass
class RollbackPlan:
    """Complete rollback plan — the reverse-DAG execution order."""
    run_id: str
    job_id: str
    entries: list[RollbackEntry] = field(default_factory=list)
    status: RollbackStatus = RollbackStatus.PENDING
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    started_at: datetime | None = None
    completed_at: datetime | None = None


class RollbackManager:
    """
    Manages the rollback of failed or cancelled workflow runs.

    Registration:
        rm = RollbackManager()
        rm.register_compensation("image_gen", "cleanup_temp_files", cleanup_fn)
        rm.register_compensation("video_gen", "delete_generated_video", delete_fn)

    Execution:
        plan = await rm.plan_rollback(run_id, completed_nodes)
        await rm.execute(plan)
    """

    def __init__(self) -> None:
        # {node_type: {compensation_name: compensation_fn}}
        self._compensations: dict[str, dict[str, CompensationFn]] = {}
        # Audit trail
        self._history: list[RollbackPlan] = []

    def register_compensation(
        self,
        node_type: str,
        compensation_name: str,
        fn: CompensationFn,
    ) -> None:
        """Register a compensation action for a node type."""
        if node_type not in self._compensations:
            self._compensations[node_type] = {}
        self._compensations[node_type][compensation_name] = fn
        logger.debug(
            f"Registered compensation '{compensation_name}' for node type '{node_type}'"
        )

    def unregister_compensation(self, node_type: str, compensation_name: str) -> bool:
        """Remove a compensation action."""
        if node_type in self._compensations:
            return self._compensations[node_type].pop(compensation_name, None) is not None
        return False

    async def plan_rollback(
        self,
        run_id: str,
        job_id: str,
        completed_nodes: list[dict[str, Any]],
        failed_node_id: str = "",
    ) -> RollbackPlan:
        """
        Generate a rollback plan from completed nodes.

        Args:
            run_id: The workflow run ID.
            job_id: The associated job ID.
            completed_nodes: List of completed nodes (in DAG order).
            failed_node_id: Optional ID of the node that failed (if any).

        Returns:
            A RollbackPlan with entries in reverse execution order.
        """
        plan = RollbackPlan(run_id=run_id, job_id=job_id)

        # Reverse the execution order
        reversed_nodes = list(reversed(completed_nodes))

        for node in reversed_nodes:
            node_id = node.get("node_id", "unknown")
            node_type = node.get("node_type", "")
            node_name = node.get("name", node_type)

            # Check if we have compensations for this node type
            compensations = self._compensations.get(node_type, {})

            entry = RollbackEntry(
                node_id=node_id,
                node_name=node_name,
                node_output=node.get("output", {}),
                compensation_fn=list(compensations.values())[0] if compensations else None,
                status=RollbackStatus.PENDING,
            )

            if not compensations:
                entry.status = RollbackStatus.SKIPPED

            plan.entries.append(entry)

        # If a specific node failed, we only roll back up to (and including) its upstream dependencies
        if failed_node_id:
            # Find the failed node's index and trim
            for i, entry in enumerate(plan.entries):
                if entry.node_id == failed_node_id:
                    plan.entries = plan.entries[i:]  # Keep from failed node onwards
                    break

        logger.info(
            f"Rollback plan created: {len(plan.entries)} entries for run {run_id}"
        )
        return plan

    async def execute(self, plan: RollbackPlan) -> RollbackPlan:
        """
        Execute a rollback plan.

        Each entry's compensation_fn is called with its node_output.
        Errors in one compensation do not block subsequent entries.
        """
        plan.status = RollbackStatus.IN_PROGRESS
        plan.started_at = datetime.now(timezone.utc)

        for entry in plan.entries:
            if entry.status == RollbackStatus.SKIPPED:
                continue

            if entry.compensation_fn is None:
                entry.status = RollbackStatus.SKIPPED
                continue

            try:
                await entry.compensation_fn(entry.node_output)
                entry.status = RollbackStatus.COMPLETED
                entry.rolled_back_at = datetime.now(timezone.utc)
                logger.info(f"Rolled back node '{entry.node_name}' ({entry.node_id})")
            except Exception as e:
                entry.status = RollbackStatus.FAILED
                entry.error = str(e)
                logger.error(
                    f"Rollback failed for node '{entry.node_name}': {e}",
                    exc_info=True,
                )
                # Continue with next entry — don't let one failure block the rest

        # Determine overall status
        any_failed = any(e.status == RollbackStatus.FAILED for e in plan.entries)
        plan.status = RollbackStatus.FAILED if any_failed else RollbackStatus.COMPLETED
        plan.completed_at = datetime.now(timezone.utc)

        # Archive
        self._history.append(plan)

        logger.info(
            f"Rollback {plan.status.value}: {plan.run_id} "
            f"({sum(1 for e in plan.entries if e.status == RollbackStatus.COMPLETED)} "
            f"completed, {sum(1 for e in plan.entries if e.status == RollbackStatus.FAILED)} failed)"
        )

        return plan

    def get_history(self, run_id: str = "") -> list[RollbackPlan]:
        """Get rollback history, optionally filtered by run_id."""
        if run_id:
            return [p for p in self._history if p.run_id == run_id]
        return list(self._history)
