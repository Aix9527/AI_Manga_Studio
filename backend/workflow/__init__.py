"""
Workflow Engine — DAG-driven workflow system (Part 12)

Transforms the manga/anime production pipeline into a directed
acyclic graph (DAG) that can be compiled, validated, and executed.

Pipeline flow:
    NovelInput → StoryParser → CharacterAgent → SceneAgent
        → Storyboard → ImageGen → VideoGen → AudioGen
        → Compositor → Review → Export

Components:
    graph.py     — DAG data structure (nodes + edges)
    nodes.py     — Node type definitions (12 production node types)
    edges.py     — Edge type definitions (data/conditional/fan-out/fan-in)
    executor.py  — Runtime execution engine with progress reporting
    compiler.py  — Pipeline-to-DAG compiler
    validator.py — Structural validation (cycle detection, etc.)
    checkpoint.py — Checkpoint persistence for resume
"""

from backend.workflow.graph import DAGGraph
from backend.workflow.nodes import (
    BaseNode,
    NodeConfig,
    NodeStatus,
    NodeCategory,
    NODE_REGISTRY,
    create_node,
)
from backend.workflow.edges import (
    BaseEdge,
    EdgeConfig,
    EdgeType,
    DataEdge,
    ConditionalEdge,
    FanOutEdge,
    FanInEdge,
    EdgeFactory,
)
from backend.workflow.executor import WorkflowExecutor
from backend.workflow.compiler import DAGCompiler
from backend.workflow.validator import DAGValidator, ValidationReport

__all__ = [
    "DAGGraph",
    "BaseNode",
    "NodeConfig",
    "NodeStatus",
    "NodeCategory",
    "NODE_REGISTRY",
    "create_node",
    "BaseEdge",
    "EdgeConfig",
    "EdgeType",
    "DataEdge",
    "ConditionalEdge",
    "FanOutEdge",
    "FanInEdge",
    "EdgeFactory",
    "WorkflowExecutor",
    "DAGCompiler",
    "DAGValidator",
    "ValidationReport",
]
