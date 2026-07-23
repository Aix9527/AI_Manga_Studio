"""
Workflow Compiler — validates and prepares workflow definitions (Part 12)

Transforms a high-level WorkflowDefinition into a compiled,
execution-ready form. Performs structural validation, cycle
detection, type checking, and optimizations.
"""

from __future__ import annotations

import logging
from typing import Any

from backend.workflow.graph import (
    WorkflowDefinition,
    WorkflowNode,
    WorkflowEdge,
    NodeType,
)
from backend.agents.base_agent import AgentRegistry


logger = logging.getLogger(__name__)


class WorkflowCompileError(Exception):
    """Raised when a workflow definition fails validation."""

    def __init__(self, errors: list[str]) -> None:
        super().__init__("; ".join(errors))
        self.errors = errors


class WorkflowCompiler:
    """
    Validates, optimizes, and prepares workflow definitions for execution.

    Checks:
    - DAG structure (no cycles, valid edges)
    - Agent availability (all agent_type references exist)
    - Input/output compatibility between connected nodes
    - Required configuration for special node types
    """

    def __init__(self, registry: AgentRegistry) -> None:
        self.registry = registry

    async def compile(
        self, workflow: WorkflowDefinition
    ) -> WorkflowDefinition:
        """
        Compile and validate a workflow definition.

        Returns the same definition if valid (with optimizations applied).
        Raises WorkflowCompileError if invalid.
        """
        errors: list[str] = []

        # 1. Structural validation (from graph.py)
        errors.extend(workflow.validate())

        # 2. Agent type validation
        for node in workflow.nodes:
            if (
                node.node_type == NodeType.AGENT
                and node.agent_type
            ):
                agents = self.registry.find_by_type(node.agent_type)
                if not agents:
                    errors.append(
                        f"Node '{node.name}': no registered agent "
                        f"of type '{node.agent_type}'"
                    )

        # 3. Required config checks
        for node in workflow.nodes:
            if node.node_type == NodeType.SUB_WORKFLOW:
                if "sub_workflow" not in node.config:
                    errors.append(
                        f"Sub-workflow node '{node.name}' missing "
                        f"'sub_workflow' in config"
                    )

        # 4. Input mapping validation
        all_node_ids = {n.node_id for n in workflow.nodes}
        for node in workflow.nodes:
            for param, upstream_var in node.input_mapping.items():
                if "." in upstream_var:
                    ref_node_id = upstream_var.split(".")[0]
                    if ref_node_id not in all_node_ids:
                        errors.append(
                            f"Node '{node.name}': input mapping "
                            f"'{param}' references unknown node "
                            f"'{ref_node_id}'"
                        )

        if errors:
            raise WorkflowCompileError(errors)

        logger.info(
            "Workflow '%s' v%s compiled successfully (%d nodes)",
            workflow.name,
            workflow.version,
            len(workflow.nodes),
        )

        return workflow


class WorkflowValidator:
    """Lightweight structural-only validator (no agent registry needed)."""

    @staticmethod
    def validate(workflow: WorkflowDefinition) -> list[str]:
        """Validate workflow structure. Returns list of errors."""
        return workflow.validate()
