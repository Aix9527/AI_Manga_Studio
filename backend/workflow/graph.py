"""
Workflow Graph Core — DAG definition, nodes, and edges (Part 12)

The workflow engine represents all production pipelines as directed
acyclic graphs. Nodes are processing stages (backed by Agents or
external services). Edges define data and control flow.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional
from uuid import uuid4


# ── Enums ────────────────────────────────────────────────────────────────


class NodeType(Enum):
    """Classification of workflow graph nodes."""
    AGENT = "agent"           # Backed by an Agent
    TRANSFORM = "transform"   # Pure data transformation
    DECISION = "decision"     # Conditional branching
    PARALLEL = "parallel"     # Fan-out / fan-in
    HUMAN_REVIEW = "human_review"  # Manual approval gate
    SUB_WORKFLOW = "sub_workflow"  # Nested workflow


class EdgeType(Enum):
    """Kind of dependency between nodes."""
    DATA_FLOW = "data_flow"        # Passes output to input
    CONTROL_FLOW = "control_flow"  # Sequential execution
    CONDITIONAL = "conditional"    # Branch on condition
    ERROR_FLOW = "error_flow"      # On failure path


class NodeStatus(Enum):
    """Runtime status of a node during execution."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"
    CANCELLED = "cancelled"


# ── Graph Objects ───────────────────────────────────────────────────────


@dataclass
class WorkflowNode:
    """A single processing stage in the DAG."""

    node_id: str = field(default_factory=lambda: str(uuid4()))
    name: str = ""
    node_type: NodeType = NodeType.AGENT
    agent_type: Optional[str] = None
    config: dict[str, Any] = field(default_factory=dict)
    input_mapping: dict[str, str] = field(
        default_factory=dict
    )  # param -> upstream_var
    output_key: str = ""  # key under which output is stored
    timeout_seconds: int = 600
    retry_policy: Optional[RetryPolicy] = None
    quality_gate: Optional[QualityGate] = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class WorkflowEdge:
    """A directed edge connecting two nodes in the DAG."""

    edge_id: str = field(default_factory=lambda: str(uuid4()))
    source_node_id: str = ""
    target_node_id: str = ""
    edge_type: EdgeType = EdgeType.DATA_FLOW
    condition: Optional[str] = None  # Python expression for conditional
    label: str = ""


@dataclass
class RetryPolicy:
    """Configures how a node retries on failure."""

    max_attempts: int = 3
    delay_seconds: int = 5
    backoff_multiplier: float = 2.0
    max_delay_seconds: int = 300
    retry_on: list[str] = field(default_factory=list)  # error codes


@dataclass
class QualityGate:
    """Automatic quality check after node completion."""

    metric: str = ""  # e.g., "aesthetic_score"
    operator: str = ">="  # >=, <=, ==, >
    threshold: float = 0.0
    on_fail: str = "retry"  # retry | skip | fail | human_review


@dataclass
class WorkflowDefinition:
    """
    Complete workflow graph definition.

    Represents one version of a production pipeline.
    Immutable once compiled. Source of truth for the
    workflow compiler and executor.
    """

    workflow_id: str = field(default_factory=lambda: str(uuid4()))
    name: str = ""
    version: str = "1.0.0"
    description: str = ""
    nodes: list[WorkflowNode] = field(default_factory=list)
    edges: list[WorkflowEdge] = field(default_factory=list)
    entry_node_id: Optional[str] = None
    exit_node_id: Optional[str] = None
    config: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def get_node(self, node_id: str) -> Optional[WorkflowNode]:
        """Find a node by ID."""
        for n in self.nodes:
            if n.node_id == node_id:
                return n
        return None

    def get_upstream_nodes(self, node_id: str) -> list[WorkflowNode]:
        """Get all nodes that feed into this node."""
        source_ids = {
            e.source_node_id
            for e in self.edges
            if e.target_node_id == node_id
        }
        return [n for n in self.nodes if n.node_id in source_ids]

    def get_downstream_nodes(self, node_id: str) -> list[WorkflowNode]:
        """Get all nodes this node feeds into."""
        target_ids = {
            e.target_node_id
            for e in self.edges
            if e.source_node_id == node_id
        }
        return [n for n in self.nodes if n.node_id in target_ids]

    def validate(self) -> list[str]:
        """
        Validate DAG structure. Returns list of errors (empty = valid).
        """
        errors: list[str] = []
        node_ids = {n.node_id for n in self.nodes}

        if not self.nodes:
            errors.append("Workflow has no nodes")

        # Entry/exit checks
        if self.entry_node_id and self.entry_node_id not in node_ids:
            errors.append(f"Entry node {self.entry_node_id} not in nodes")

        # Edge validation
        for edge in self.edges:
            if edge.source_node_id not in node_ids:
                errors.append(
                    f"Edge source {edge.source_node_id} not found"
                )
            if edge.target_node_id not in node_ids:
                errors.append(
                    f"Edge target {edge.target_node_id} not found"
                )

        # Cycle detection (topological sort)
        try:
            self._topological_order()
        except ValueError as e:
            errors.append(str(e))

        return errors

    def _topological_order(self) -> list[str]:
        """Return nodes in topological order. Raises ValueError on cycle."""
        in_degree: dict[str, int] = {n.node_id: 0 for n in self.nodes}
        adj: dict[str, list[str]] = {n.node_id: [] for n in self.nodes}

        for e in self.edges:
            adj[e.source_node_id].append(e.target_node_id)
            in_degree[e.target_node_id] += 1

        queue = [nid for nid, deg in in_degree.items() if deg == 0]
        order: list[str] = []

        while queue:
            node = queue.pop(0)
            order.append(node)
            for neighbor in adj[node]:
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)

        if len(order) != len(self.nodes):
            raise ValueError("Workflow graph contains a cycle")
        return order
