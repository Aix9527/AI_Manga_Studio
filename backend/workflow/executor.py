"""
Workflow Executor — DAG runtime execution engine (Part 12)

Drives the execution of a compiled workflow DAG. Manages node
lifecycle, handles parallel fan-out/fan-in, retries, error handling,
and produces a complete execution trace.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Optional
from uuid import uuid4

from backend.workflow.graph import (
    WorkflowDefinition,
    WorkflowNode,
    WorkflowEdge,
    NodeStatus,
    NodeType,
    EdgeType,
    RetryPolicy,
    QualityGate,
)
from backend.agents.base_agent import AgentRegistry, AgentContext, AgentResult


logger = logging.getLogger(__name__)


@dataclass
class NodeExecution:
    """Record of a single node's execution."""
    execution_id: str = field(default_factory=lambda: str(uuid4()))
    node_id: str = ""
    status: NodeStatus = NodeStatus.PENDING
    started_at: Optional[float] = None
    completed_at: Optional[float] = None
    attempt: int = 0
    result: Optional[AgentResult] = None
    error: Optional[str] = None


@dataclass
class WorkflowRun:
    """
    A single execution run of a workflow definition.

    Tracks the state of every node, manages the output context
    that flows from upstream to downstream nodes.
    """

    run_id: str = field(default_factory=lambda: str(uuid4()))
    workflow: WorkflowDefinition = field(default_factory=WorkflowDefinition)
    project_id: str = ""
    node_executions: dict[str, NodeExecution] = field(default_factory=dict)
    context: dict[str, Any] = field(default_factory=dict)
    status: str = "pending"
    started_at: Optional[float] = None
    completed_at: Optional[float] = None
    cancel_event: asyncio.Event = field(
        default_factory=asyncio.Event
    )

    def get_output(self, node_id: str) -> Optional[AgentResult]:
        """Get the output of a completed node."""
        exec_rec = self.node_executions.get(node_id)
        if exec_rec and exec_rec.status == NodeStatus.COMPLETED:
            return exec_rec.result
        return None


class WorkflowExecutor:
    """
    Executes a compiled workflow DAG.

    Handles topological ordering, parallel execution of independent
    nodes, retry logic, quality gates, and human review checkpoints.
    """

    def __init__(self, agent_registry: AgentRegistry) -> None:
        self.registry = agent_registry
        self._active_runs: dict[str, WorkflowRun] = {}

    async def execute(
        self,
        workflow: WorkflowDefinition,
        project_id: str,
        input_context: dict[str, Any],
        run_id: Optional[str] = None,
    ) -> WorkflowRun:
        """
        Execute a workflow definition.

        Returns the completed WorkflowRun with all node results.
        Raises WorkflowExecutionError on unrecoverable failure.
        """
        run = WorkflowRun(
            run_id=run_id or str(uuid4()),
            workflow=workflow,
            project_id=project_id,
            context=input_context,
        )
        run.started_at = time.time()
        self._active_runs[run.run_id] = run

        # Initialize all node executions
        for node in workflow.nodes:
            run.node_executions[node.node_id] = NodeExecution(
                node_id=node.node_id
            )

        try:
            # Topological execution
            order = workflow._topological_order()
            for node_id in order:
                if run.cancel_event.is_set():
                    self._cancel_all(run)
                    break

                node = workflow.get_node(node_id)
                if node is None:
                    continue

                await self._execute_node(node, run)

        except Exception:
            run.status = "failed"
            raise
        else:
            if run.status != "cancelled":
                run.status = "completed"
        finally:
            run.completed_at = time.time()

        return run

    async def cancel(self, run_id: str) -> None:
        """Cancel a running workflow."""
        run = self._active_runs.get(run_id)
        if run:
            run.cancel_event.set()

    async def _execute_node(
        self, node: WorkflowNode, run: WorkflowRun
    ) -> None:
        """Execute a single node with retry logic."""
        exec_rec = run.node_executions[node.node_id]

        # Check if all upstream nodes completed successfully
        upstream = run.workflow.get_upstream_nodes(node.node_id)
        for up_node in upstream:
            up_exec = run.node_executions[up_node.node_id]
            if up_exec.status != NodeStatus.COMPLETED:
                exec_rec.status = NodeStatus.SKIPPED
                return

        # Resolve input from upstream outputs
        node_input = self._resolve_inputs(node, run)

        # Execute with retries
        retry_policy = node.retry_policy or RetryPolicy()
        last_error: Optional[str] = None

        for attempt in range(1, retry_policy.max_attempts + 1):
            if run.cancel_event.is_set():
                exec_rec.status = NodeStatus.CANCELLED
                return

            exec_rec.attempt = attempt
            exec_rec.status = NodeStatus.RUNNING
            exec_rec.started_at = time.time()

            try:
                result = await self._run_node(node, run, node_input)
                exec_rec.result = result
                exec_rec.status = (
                    NodeStatus.COMPLETED
                    if result.success
                    else NodeStatus.FAILED
                )

                if exec_rec.status == NodeStatus.COMPLETED:
                    # Quality gate
                    qg_result = await self._check_quality_gate(
                        node, result
                    )
                    if qg_result == "fail":
                        exec_rec.status = NodeStatus.FAILED
                    elif qg_result == "retry":
                        continue

                if exec_rec.status == NodeStatus.COMPLETED:
                    # Store output in run context
                    if node.output_key:
                        run.context[node.output_key] = result
                    break

            except asyncio.CancelledError:
                exec_rec.status = NodeStatus.CANCELLED
                return
            except Exception as exc:
                last_error = str(exc)
                exec_rec.error = last_error
                exec_rec.status = NodeStatus.FAILED
                logger.warning(
                    "Node %s attempt %d failed: %s",
                    node.node_id,
                    attempt,
                    last_error,
                )

            # Backoff before retry
            if attempt < retry_policy.max_attempts:
                delay = min(
                    retry_policy.delay_seconds
                    * (retry_policy.backoff_multiplier ** (attempt - 1)),
                    retry_policy.max_delay_seconds,
                )
                await asyncio.sleep(delay)

        exec_rec.completed_at = time.time()

        # If all retries exhausted and still failed, propagate
        if exec_rec.status == NodeStatus.FAILED:
            raise WorkflowExecutionError(
                f"Node {node.node_id} ({node.name}) failed after "
                f"{retry_policy.max_attempts} attempts: {last_error}",
                node_id=node.node_id,
            )

    async def _run_node(
        self,
        node: WorkflowNode,
        run: WorkflowRun,
        node_input: dict[str, Any],
    ) -> AgentResult:
        """Delegate to the appropriate execution backend."""
        if node.node_type == NodeType.AGENT:
            return await self._run_agent_node(node, run, node_input)
        elif node.node_type == NodeType.TRANSFORM:
            return await self._run_transform_node(node, node_input)
        elif node.node_type == NodeType.HUMAN_REVIEW:
            return await self._run_human_review_node(node, node_input)
        elif node.node_type == NodeType.PARALLEL:
            return await self._run_parallel_node(node, run, node_input)
        elif node.node_type == NodeType.SUB_WORKFLOW:
            return await self._run_sub_workflow(node, run, node_input)
        elif node.node_type == NodeType.DECISION:
            return await self._run_decision_node(node, node_input)
        else:
            raise ValueError(f"Unknown node type: {node.node_type}")

    async def _run_agent_node(
        self,
        node: WorkflowNode,
        run: WorkflowRun,
        node_input: dict[str, Any],
    ) -> AgentResult:
        """Execute an agent-backed node."""
        if not node.agent_type:
            raise ValueError(f"Agent node {node.node_id} has no agent_type")

        agents = self.registry.find_by_type(node.agent_type)
        if not agents:
            raise ValueError(f"No agent found for type: {node.agent_type}")

        agent = agents[0]  # Take first matching agent
        agent_ctx = AgentContext(
            project_id=run.project_id,
            job_id=run.run_id,
            workflow_run_id=run.run_id,
            variables=node.config,
            upstream_outputs={},
        )

        return await agent.execute(agent_ctx, **node_input)

    async def _run_transform_node(
        self, node: WorkflowNode, node_input: dict[str, Any]
    ) -> AgentResult:
        """Pure data transformation node."""
        from backend.agents.base_agent import AgentStatus

        # Apply transform function from config
        transform_fn = node.config.get("transform_fn")
        if callable(transform_fn):
            output = transform_fn(node_input)
        else:
            output = node_input

        return AgentResult(
            agent_id=node.node_id,
            agent_type="transform",
            status=AgentStatus.COMPLETED,
            output={"data": output},
        )

    async def _run_human_review_node(
        self, node: WorkflowNode, node_input: dict[str, Any]
    ) -> AgentResult:
        """Human review gate — waits for external approval."""
        from backend.agents.base_agent import AgentStatus

        # In MVP, auto-approve or wait for review API callback
        auto_approve = node.config.get("auto_approve", True)
        if auto_approve:
            return AgentResult(
                agent_id=node.node_id,
                agent_type="human_review",
                status=AgentStatus.COMPLETED,
                output={"approved": True, "auto_approved": True},
            )
        # In production: this would await an external signal
        raise NotImplementedError("Human review requires external approval")

    async def _run_parallel_node(
        self,
        node: WorkflowNode,
        run: WorkflowRun,
        node_input: dict[str, Any],
    ) -> AgentResult:
        """Fan-out: execute sub-tasks in parallel."""
        from backend.agents.base_agent import AgentStatus

        sub_tasks = node.config.get("sub_tasks", [])
        results = await asyncio.gather(
            *[self._execute_sub_task(t, run, node_input) for t in sub_tasks],
            return_exceptions=True,
        )
        return AgentResult(
            agent_id=node.node_id,
            agent_type="parallel",
            status=AgentStatus.COMPLETED,
            output={"results": results},
        )

    async def _run_sub_workflow(
        self,
        node: WorkflowNode,
        run: WorkflowRun,
        node_input: dict[str, Any],
    ) -> AgentResult:
        """Execute a nested sub-workflow."""
        sub_def = node.config.get("sub_workflow")
        if not isinstance(sub_def, WorkflowDefinition):
            raise ValueError("sub_workflow config must be WorkflowDefinition")

        sub_run = await self.execute(sub_def, run.project_id, node_input)
        last_result = list(sub_run.node_executions.values())[-1]
        return last_result.result or AgentResult(
            agent_id=node.node_id,
            agent_type="sub_workflow",
            status="completed",
        )

    async def _run_decision_node(
        self, node: WorkflowNode, node_input: dict[str, Any]
    ) -> AgentResult:
        """Evaluate a condition and return the selected branch."""
        from backend.agents.base_agent import AgentStatus

        condition = node.config.get("condition", "True")
        result_branch = eval(condition, {"__builtins__": {}}, node_input)
        return AgentResult(
            agent_id=node.node_id,
            agent_type="decision",
            status=AgentStatus.COMPLETED,
            output={"branch": str(result_branch), "result": result_branch},
        )

    async def _execute_sub_task(
        self,
        task_config: dict[str, Any],
        run: WorkflowRun,
        node_input: dict[str, Any],
    ) -> dict[str, Any]:
        """Execute a single parallel sub-task."""
        await asyncio.sleep(0.001)  # placeholder
        return {"task": task_config.get("name", "unknown"), "status": "done"}

    def _resolve_inputs(
        self, node: WorkflowNode, run: WorkflowRun
    ) -> dict[str, Any]:
        """Build input dict from upstream node outputs and config."""
        resolved: dict[str, Any] = dict(node.config)

        for param, upstream_var in node.input_mapping.items():
            if "." in upstream_var:
                node_id, key = upstream_var.split(".", 1)
                upstream_result = run.get_output(node_id)
                if upstream_result:
                    resolved[param] = upstream_result.output.get(key)
            else:
                resolved[param] = run.context.get(upstream_var)

        return resolved

    async def _check_quality_gate(
        self, node: WorkflowNode, result: AgentResult
    ) -> str:
        """Check quality gate after node completion. Returns action."""
        qg = node.quality_gate
        if not qg:
            return "pass"

        value = result.output.get(qg.metric, 0)
        passed = eval(
            f"{value} {qg.operator} {qg.threshold}",
            {"__builtins__": {}},
            {},
        )
        return "pass" if passed else qg.on_fail

    def _cancel_all(self, run: WorkflowRun) -> None:
        """Mark all pending nodes as cancelled."""
        run.status = "cancelled"
        for exec_rec in run.node_executions.values():
            if exec_rec.status in (
                NodeStatus.PENDING,
                NodeStatus.RUNNING,
            ):
                exec_rec.status = NodeStatus.CANCELLED


class WorkflowExecutionError(Exception):
    """Wraps workflow execution failures with node context."""

    def __init__(self, message: str, node_id: str = "") -> None:
        super().__init__(message)
        self.node_id = node_id
