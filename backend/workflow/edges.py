"""
Workflow Edges — DAG edge definitions (Part 12)

Edges define the data flow and control flow between nodes.

Edge types:
- DataEdge: Passes output from source node to input of target node
- ConditionalEdge: Routes based on a predicate function
- FanOutEdge: Splits one output to multiple downstream inputs (parallel)
- FanInEdge: Collects multiple upstream outputs into one input

Edges carry a transform function that maps node outputs
to the expected input format of the downstream node.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable

logger = logging.getLogger(__name__)

TransformFn = Callable[[dict[str, Any]], dict[str, Any]]
ConditionFn = Callable[[dict[str, Any]], bool]


class EdgeType(str, Enum):
    """Edge classification."""
    DATA = "data"            # Simple pass-through
    CONDITIONAL = "conditional"  # Branch based on condition
    FAN_OUT = "fan_out"      # One-to-many
    FAN_IN = "fan_in"        # Many-to-one
    OPTIONAL = "optional"    # May be skipped


@dataclass
class EdgeConfig:
    """Configuration for an edge."""
    edge_id: str
    source_node_id: str
    target_node_id: str
    edge_type: EdgeType = EdgeType.DATA
    label: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


# ── Base Edge ──────────────────────────────────────────────────────────


class BaseEdge(ABC):
    """
    Abstract base for all DAG edges.

    Each edge implements:
    - transform(): Maps source node output to target node input.
    - can_execute(): Optional condition check for conditional edges.
    """

    def __init__(self, config: EdgeConfig) -> None:
        self.config = config

    @abstractmethod
    async def transform(self, source_output: dict[str, Any]) -> dict[str, Any]:
        """Transform source output into input for target node."""
        ...

    async def can_execute(self, source_output: dict[str, Any]) -> bool:
        """Conditional gate. Default: always True."""
        return True

    def to_dict(self) -> dict[str, Any]:
        return {
            "edge_id": self.config.edge_id,
            "source": self.config.source_node_id,
            "target": self.config.target_node_id,
            "type": self.config.edge_type.value,
            "label": self.config.label,
        }


# ── Concrete Edges ─────────────────────────────────────────────────────


class DataEdge(BaseEdge):
    """
    Simple data pass-through edge.

    Automatically wraps source output into a dict keyed by source node type
    if the transform_fn is not provided.

    Example:
        Source: StoryParserNode output {"chapters": [...]}
        Target receives: {"story": {"chapters": [...]}}
    """

    def __init__(
        self,
        config: EdgeConfig,
        transform_fn: TransformFn | None = None,
        input_key: str = "",
    ) -> None:
        super().__init__(config)
        self._transform_fn = transform_fn
        self._input_key = input_key

    async def transform(self, source_output: dict[str, Any]) -> dict[str, Any]:
        if self._transform_fn:
            return self._transform_fn(source_output)
        if self._input_key:
            return {self._input_key: source_output}
        # Auto-wrap: use source node_id prefix
        key = self.config.source_node_id.split("_")[0] if self.config.source_node_id else "input"
        return {key: source_output}


class ConditionalEdge(BaseEdge):
    """
    Conditional branching edge.

    Only passes data through if the condition_fn returns True.
    Used for review gates, quality checks, etc.

    Example:
        ConditionalEdge(
            config=...,
            condition_fn=lambda output: output.get("quality_score", 0) >= 0.8,
            true_edge=quality_pass_edge,
            false_edge=retry_edge,
        )
    """

    def __init__(
        self,
        config: EdgeConfig,
        condition_fn: ConditionFn,
        true_edge: BaseEdge | None = None,
        false_edge: BaseEdge | None = None,
    ) -> None:
        super().__init__(config)
        self._condition_fn = condition_fn
        self.true_edge = true_edge
        self.false_edge = false_edge

    async def transform(self, source_output: dict[str, Any]) -> dict[str, Any]:
        return source_output  # Pass-through; routing handled by can_execute + executor

    async def can_execute(self, source_output: dict[str, Any]) -> bool:
        return self._condition_fn(source_output)

    async def get_active_edge(self, source_output: dict[str, Any]) -> BaseEdge | None:
        """Return the edge that should be taken based on condition."""
        return self.true_edge if self._condition_fn(source_output) else self.false_edge


class FanOutEdge(BaseEdge):
    """
    One-to-many edge: splits source output to multiple downstream nodes.

    Each downstream target gets a copy of the (optionally transformed) output.
    Used for parallel generation stages (e.g., multiple ImageGen nodes from one storyboard).

    Example:
        FanOutEdge(
            config=...,
            targets=["image_gen_1", "image_gen_2", "image_gen_3"],
            split_fn=lambda output, index: {"shot": output["shots"][index]},
        )
    """

    def __init__(
        self,
        config: EdgeConfig,
        targets: list[str],
        split_fn: Callable[[dict[str, Any], int], dict[str, Any]] | None = None,
    ) -> None:
        super().__init__(config)
        self.targets = targets
        self._split_fn = split_fn or (lambda output, idx: output)

    async def transform(self, source_output: dict[str, Any]) -> dict[str, Any]:
        return source_output  # Pass-through; splitting done by executor

    async def split(self, source_output: dict[str, Any]) -> dict[str, dict[str, Any]]:
        """Split output into per-target inputs."""
        result: dict[str, dict[str, Any]] = {}
        for i, target_id in enumerate(self.targets):
            result[target_id] = self._split_fn(source_output, i)
        return result


class FanInEdge(BaseEdge):
    """
    Many-to-one edge: collects multiple upstream outputs into one.

    Used for compositing/export stages that need all upstream results.
    Provides a reduce_fn to merge multiple outputs.

    Example:
        FanInEdge(
            config=...,
            sources=["video_gen_1", "video_gen_2"],
            reduce_fn=lambda outputs: {"video_clips": [o["video"] for o in outputs]},
        )
    """

    def __init__(
        self,
        config: EdgeConfig,
        sources: list[str],
        reduce_fn: Callable[[list[dict[str, Any]]], dict[str, Any]] | None = None,
    ) -> None:
        super().__init__(config)
        self.sources = sources
        self._reduce_fn = reduce_fn or (lambda outputs: {"merged": outputs})

    async def transform(self, source_output: dict[str, Any]) -> dict[str, Any]:
        return source_output  # Pass-through; merging done by executor

    async def reduce(self, outputs: list[dict[str, Any]]) -> dict[str, Any]:
        """Reduce multiple outputs into a single input dict."""
        return self._reduce_fn(outputs)


class OptionalEdge(BaseEdge):
    """
    Optional edge: may be skipped if source node is not executed.

    Used for optional stages in the pipeline.
    """

    def __init__(self, config: EdgeConfig, default_value: dict[str, Any] | None = None) -> None:
        super().__init__(config)
        self._default_value = default_value or {}

    async def transform(self, source_output: dict[str, Any]) -> dict[str, Any]:
        return source_output

    async def get_default(self) -> dict[str, Any]:
        """Return default input when source is skipped."""
        return self._default_value


# ── Edge Factory ───────────────────────────────────────────────────────


class EdgeFactory:
    """Factory for creating edges from simplified configs."""

    @staticmethod
    def simple(source: str, target: str, input_key: str = "", label: str = "") -> DataEdge:
        """Create a simple data edge."""
        import uuid
        config = EdgeConfig(
            edge_id=str(uuid.uuid4()),
            source_node_id=source,
            target_node_id=target,
            edge_type=EdgeType.DATA,
            label=label,
        )
        return DataEdge(config, input_key=input_key)

    @staticmethod
    def conditional(
        source: str,
        target: str,
        condition_fn: ConditionFn,
        label: str = "",
    ) -> ConditionalEdge:
        """Create a conditional edge."""
        import uuid
        config = EdgeConfig(
            edge_id=str(uuid.uuid4()),
            source_node_id=source,
            target_node_id=target,
            edge_type=EdgeType.CONDITIONAL,
            label=label,
        )
        return ConditionalEdge(config, condition_fn=condition_fn)

    @staticmethod
    def fan_out(
        source: str,
        targets: list[str],
        split_fn: Callable[[dict[str, Any], int], dict[str, Any]] | None = None,
        label: str = "",
    ) -> FanOutEdge:
        """Create a fan-out edge."""
        import uuid
        config = EdgeConfig(
            edge_id=str(uuid.uuid4()),
            source_node_id=source,
            target_node_id=targets[0] if targets else "",
            edge_type=EdgeType.FAN_OUT,
            label=label,
        )
        return FanOutEdge(config, targets=targets, split_fn=split_fn)

    @staticmethod
    def fan_in(
        sources: list[str],
        target: str,
        reduce_fn: Callable[[list[dict[str, Any]]], dict[str, Any]] | None = None,
        label: str = "",
    ) -> FanInEdge:
        """Create a fan-in edge."""
        import uuid
        config = EdgeConfig(
            edge_id=str(uuid.uuid4()),
            source_node_id=sources[0] if sources else "",
            target_node_id=target,
            edge_type=EdgeType.FAN_IN,
            label=label,
        )
        return FanInEdge(config, sources=sources, reduce_fn=reduce_fn)
