"""
Workflow Checkpoint & Resume System (Part 12)

Provides durable checkpointing so long-running workflows can
survive process restarts. Records each node's completion state
and allows resumption from the last successful checkpoint.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional
from uuid import uuid4

from backend.workflow.graph import WorkflowDefinition
from backend.workflow.executor import NodeExecution, WorkflowRun


logger = logging.getLogger(__name__)


@dataclass
class Checkpoint:
    """Serializable snapshot of a workflow run state."""

    run_id: str
    workflow_id: str
    version: str
    project_id: str
    completed_nodes: list[str] = field(default_factory=list)
    node_results: dict[str, dict[str, Any]] = field(default_factory=dict)
    context: dict[str, Any] = field(default_factory=dict)
    status: str = "running"


class CheckpointManager:
    """
    Manages persistence and restoration of workflow checkpoints.

    Uses file-based storage for MVP (migrate to database later).
    Each checkpoint is written atomically.
    """

    def __init__(self, base_dir: Path) -> None:
        self.base_dir = base_dir
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def _path(self, run_id: str) -> Path:
        return self.base_dir / f"{run_id}.checkpoint.json"

    async def save(self, run: WorkflowRun) -> None:
        """Save current workflow run state as a checkpoint."""
        checkpoint = Checkpoint(
            run_id=run.run_id,
            workflow_id=run.workflow.workflow_id,
            version=run.workflow.version,
            project_id=run.project_id,
            completed_nodes=[
                nid
                for nid, ex in run.node_executions.items()
                if ex.status == "completed"
            ],
            node_results={
                nid: {"output": ex.result.output if ex.result else {}}
                for nid, ex in run.node_executions.items()
                if ex.status == "completed" and ex.result
            },
            context=run.context,
            status=run.status,
        )

        tmp_path = self._path(run.run_id).with_suffix(".tmp")
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(checkpoint.__dict__, f, indent=2, default=str)
        tmp_path.replace(self._path(run.run_id))

        logger.debug("Checkpoint saved: %s", run.run_id)

    async def load(self, run_id: str) -> Optional[Checkpoint]:
        """Load the latest checkpoint for a workflow run."""
        path = self._path(run_id)
        if not path.exists():
            return None

        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return Checkpoint(**data)

    async def resume(
        self,
        run_id: str,
        workflow: WorkflowDefinition,
    ) -> Optional[WorkflowRun]:
        """
        Attempt to resume a workflow from its last checkpoint.

        Returns a partially-populated WorkflowRun with completed
        nodes marked, ready for the executor to continue.
        """
        checkpoint = await self.load(run_id)
        if not checkpoint:
            return None

        if checkpoint.status == "completed":
            logger.info("Workflow %s already completed", run_id)
            return None

        run = WorkflowRun(
            run_id=run_id,
            workflow=workflow,
            project_id=checkpoint.project_id,
            context=checkpoint.context,
        )

        # Restore completed node states
        for node_id in checkpoint.completed_nodes:
            exec_rec = NodeExecution(
                node_id=node_id, status="completed"
            )
            result_data = checkpoint.node_results.get(node_id, {})
            from backend.agents.base_agent import (
                AgentResult,
                AgentStatus,
            )

            exec_rec.result = AgentResult(
                agent_id=node_id,
                agent_type="restored",
                status=AgentStatus.COMPLETED,
                output=result_data.get("output", {}),
            )
            run.node_executions[node_id] = exec_rec

        logger.info(
            "Resumed workflow %s from checkpoint (%d nodes completed)",
            run_id,
            len(checkpoint.completed_nodes),
        )
        return run

    async def delete(self, run_id: str) -> None:
        """Remove checkpoint after successful completion."""
        path = self._path(run_id)
        if path.exists():
            path.unlink()
