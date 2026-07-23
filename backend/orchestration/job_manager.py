"""
Orchestration — Job Manager (Part 8 + Part 12)

Central orchestrator that creates, queues, dispatches, and tracks
long-running workflow jobs. Integrates with the EventBus for
real-time status updates and the WorkflowCompiler/Executor for
pipeline execution.

Implements: Create → Queue → Dispatch → Execute → Retry/Resume/Rollback
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional
from uuid import uuid4

from backend.events import EventBus, DomainEvent, EventCategory
from backend.workflow.graph import WorkflowDefinition
from backend.workflow.compiler import WorkflowCompiler
from backend.workflow.executor import WorkflowExecutor, WorkflowRun
from backend.workflow.checkpoint import CheckpointManager
from backend.agents.base_agent import AgentRegistry


logger = logging.getLogger(__name__)


class JobStatus(Enum):
    """Lifecycle status of an orchestration job."""
    PENDING = "pending"
    QUEUED = "queued"
    DISPATCHED = "dispatched"
    RUNNING = "running"
    RETRYING = "retrying"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    ROLLING_BACK = "rolling_back"
    ROLLED_BACK = "rolled_back"


@dataclass
class Job:
    """Represents a single orchestration job (one workflow run)."""

    job_id: str = field(default_factory=lambda: str(uuid4()))
    project_id: str = ""
    workflow_name: str = ""
    workflow_version: str = "1.0.0"
    status: JobStatus = JobStatus.PENDING
    priority: int = 0
    input_data: dict[str, Any] = field(default_factory=dict)
    output_data: dict[str, Any] = field(default_factory=dict)
    workflow_run_id: Optional[str] = None
    error: Optional[str] = None
    retry_count: int = 0
    max_retries: int = 3
    created_at: float = field(default_factory=time.time)
    started_at: Optional[float] = None
    completed_at: Optional[float] = None
    tags: list[str] = field(default_factory=list)


class JobManager:
    """
    Orchestration layer — the "brain" of the system.

    Manages the lifecycle of Jobs that wrap Workflow executions.
    """

    def __init__(
        self,
        event_bus: EventBus,
        compiler: WorkflowCompiler,
        registry: Optional[AgentRegistry] = None,
        max_concurrency: int = 4,
    ) -> None:
        self.event_bus = event_bus
        self.compiler = compiler
        self.registry = registry or AgentRegistry()
        self.max_concurrency = max_concurrency

        self._executor: Optional[WorkflowExecutor] = None
        self._checkpoints: Optional[CheckpointManager] = None
        self._queue: asyncio.Queue[Job] = asyncio.Queue()
        self._jobs: dict[str, Job] = {}
        self._active_count: int = 0
        self._worker_task: Optional[asyncio.Task] = None
        self._running: bool = False

    async def start(self) -> None:
        """Start the job manager and background worker."""
        self._running = True
        self._executor = WorkflowExecutor(self.registry)

        from pathlib import Path

        self._checkpoints = CheckpointManager(
            Path("data/checkpoints")
        )

        self._worker_task = asyncio.create_task(self._worker_loop())
        logger.info("JobManager started (concurrency=%d)", self.max_concurrency)

    async def shutdown(self) -> None:
        """Graceful shutdown: drain queue, cancel worker."""
        self._running = False
        if self._worker_task:
            self._worker_task.cancel()
            try:
                await self._worker_task
            except asyncio.CancelledError:
                pass
        logger.info("JobManager shut down")

    async def submit(
        self,
        workflow: WorkflowDefinition,
        project_id: str,
        input_data: dict[str, Any],
        priority: int = 0,
    ) -> Job:
        """
        Compile a workflow, create a Job, and enqueue it.

        Returns the Job for tracking. The caller can poll or listen
        to events for status changes.
        """
        # Compile (validate)
        await self.compiler.compile(workflow)

        job = Job(
            project_id=project_id,
            workflow_name=workflow.name,
            workflow_version=workflow.version,
            input_data=input_data,
            priority=priority,
        )
        self._jobs[job.job_id] = job

        # Enqueue
        await self._queue.put(job)
        job.status = JobStatus.QUEUED

        await self.event_bus.publish(
            DomainEvent(
                event_type="job.queued",
                category=EventCategory.JOB,
                aggregate_id=job.job_id,
                payload={"project_id": project_id},
            )
        )

        logger.info("Job %s queued: %s", job.job_id, workflow.name)
        return job

    async def get_job(self, job_id: str) -> Optional[Job]:
        """Retrieve a job by ID."""
        return self._jobs.get(job_id)

    async def cancel_job(self, job_id: str) -> bool:
        """Cancel a queued or running job."""
        job = self._jobs.get(job_id)
        if not job:
            return False

        if job.status in (JobStatus.PENDING, JobStatus.QUEUED):
            job.status = JobStatus.CANCELLED
            return True

        if job.status == JobStatus.RUNNING and self._executor:
            if job.workflow_run_id:
                await self._executor.cancel(job.workflow_run_id)
            job.status = JobStatus.CANCELLED
            return True

        return False

    async def resume_job(self, job_id: str) -> Optional[Job]:
        """Attempt to resume a failed job from checkpoint."""
        job = self._jobs.get(job_id)
        if not job or job.status != JobStatus.FAILED:
            return None

        job.status = JobStatus.RETRYING
        await self._queue.put(job)
        return job

    # ── Worker Loop ────────────────────────────────────────────

    async def _worker_loop(self) -> None:
        """Background worker that dequeues and executes jobs."""
        while self._running:
            try:
                job = await asyncio.wait_for(
                    self._queue.get(), timeout=1.0
                )
                asyncio.create_task(self._execute_job(job))
            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                break

    async def _execute_job(self, job: Job) -> None:
        """Execute a single job: dispatch, run workflow, handle outcomes."""
        job.status = JobStatus.DISPATCHED
        job.started_at = time.time()
        self._active_count += 1

        try:
            # Build workflow definition from stored config
            workflow = self._build_workflow(job)

            job.status = JobStatus.RUNNING
            job.workflow_run_id = str(uuid4())

            # Execute
            assert self._executor is not None
            run = await self._executor.execute(
                workflow=workflow,
                project_id=job.project_id,
                input_data=job.input_data,
                run_id=job.workflow_run_id,
            )

            # Save checkpoint on completion
            if self._checkpoints:
                await self._checkpoints.save(run)

            job.output_data = run.context
            job.status = JobStatus.COMPLETED

            await self.event_bus.publish(
                DomainEvent(
                    event_type="job.completed",
                    category=EventCategory.JOB,
                    aggregate_id=job.job_id,
                    payload=job.output_data,
                )
            )

        except Exception as exc:
            job.error = str(exc)
            job.retry_count += 1

            if job.retry_count < job.max_retries:
                job.status = JobStatus.RETRYING
                await self._queue.put(job)
                logger.warning(
                    "Job %s failed, retrying (%d/%d)",
                    job.job_id,
                    job.retry_count,
                    job.max_retries,
                )
            else:
                job.status = JobStatus.FAILED
                await self.event_bus.publish(
                    DomainEvent(
                        event_type="job.failed",
                        category=EventCategory.JOB,
                        aggregate_id=job.job_id,
                        payload={"error": job.error},
                    )
                )
                logger.error("Job %s failed permanently: %s", job.job_id, exc)

        finally:
            job.completed_at = time.time()
            self._active_count -= 1

    def _build_workflow(self, job: Job) -> WorkflowDefinition:
        """
        Build a WorkflowDefinition for this job.

        In production this would load from a persisted workflow
        registry or template. For MVP, builds from job metadata.
        """
        from backend.workflow.graph import (
            WorkflowNode,
            WorkflowEdge,
            NodeType,
            EdgeType,
        )

        # Default MVP pipeline: Novel → StoryParser → Character → Storyboard → Image → Video
        return WorkflowDefinition(
            name=job.workflow_name,
            version=job.workflow_version,
            nodes=[
                WorkflowNode(
                    node_id="novel_input",
                    name="Novel Input",
                    node_type=NodeType.TRANSFORM,
                    output_key="novel",
                ),
                WorkflowNode(
                    node_id="story_parser",
                    name="Story Parser",
                    node_type=NodeType.AGENT,
                    agent_type="story",
                    output_key="parsed_story",
                ),
                WorkflowNode(
                    node_id="character_agent",
                    name="Character Agent",
                    node_type=NodeType.AGENT,
                    agent_type="character",
                    output_key="characters",
                ),
                WorkflowNode(
                    node_id="storyboard",
                    name="Storyboard",
                    node_type=NodeType.AGENT,
                    agent_type="storyboard",
                    output_key="storyboard",
                ),
                WorkflowNode(
                    node_id="image_generation",
                    name="Image Generation",
                    node_type=NodeType.AGENT,
                    agent_type="prompt",
                    output_key="images",
                ),
                WorkflowNode(
                    node_id="video_generation",
                    name="Video Generation",
                    node_type=NodeType.AGENT,
                    agent_type="video",
                    output_key="videos",
                ),
            ],
            edges=[
                WorkflowEdge(
                    source_node_id="novel_input",
                    target_node_id="story_parser",
                    edge_type=EdgeType.DATA_FLOW,
                ),
                WorkflowEdge(
                    source_node_id="story_parser",
                    target_node_id="character_agent",
                    edge_type=EdgeType.DATA_FLOW,
                ),
                WorkflowEdge(
                    source_node_id="character_agent",
                    target_node_id="storyboard",
                    edge_type=EdgeType.DATA_FLOW,
                ),
                WorkflowEdge(
                    source_node_id="storyboard",
                    target_node_id="image_generation",
                    edge_type=EdgeType.DATA_FLOW,
                ),
                WorkflowEdge(
                    source_node_id="image_generation",
                    target_node_id="video_generation",
                    edge_type=EdgeType.DATA_FLOW,
                ),
            ],
            entry_node_id="novel_input",
            exit_node_id="video_generation",
        )
