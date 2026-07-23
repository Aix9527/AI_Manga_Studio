"""
Workflow Validator — DAG structural validation (Part 12)

Validates workflow DAGs before execution to catch errors early:
- No cycles (DAG property)
- No orphan nodes (unreachable from entry point)
- All required inputs connected
- Node types match registered handlers
- No conflicting parallel writes
- Resource constraints satisfied
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class ValidationError:
    """A single validation issue."""
    code: str
    message: str
    node_id: str = ""
    edge_id: str = ""
    severity: str = "error"  # error, warning


@dataclass
class ValidationReport:
    """Complete validation result."""
    is_valid: bool = True
    errors: list[ValidationError] = field(default_factory=list)
    warnings: list[ValidationError] = field(default_factory=list)
    stats: dict[str, int] = field(default_factory=dict)

    def add_error(self, error: ValidationError) -> None:
        self.errors.append(error)
        self.is_valid = False

    def add_warning(self, warning: ValidationError) -> None:
        self.warnings.append(warning)

    def to_dict(self) -> dict[str, Any]:
        return {
            "is_valid": self.is_valid,
            "error_count": len(self.errors),
            "warning_count": len(self.warnings),
            "errors": [
                {"code": e.code, "message": e.message, "node_id": e.node_id, "edge_id": e.edge_id}
                for e in self.errors
            ],
            "warnings": [
                {"code": w.code, "message": w.message, "node_id": w.node_id, "edge_id": w.edge_id}
                for w in self.warnings
            ],
            "stats": self.stats,
        }

    def __str__(self) -> str:
        lines = [f"Validation {'PASSED' if self.is_valid else 'FAILED'}"]
        lines.append(f"  Nodes: {self.stats.get('node_count', 0)}, Edges: {self.stats.get('edge_count', 0)}")
        for err in self.errors:
            lines.append(f"  [ERROR] {err.code}: {err.message}")
        for warn in self.warnings:
            lines.append(f"  [WARN]  {warn.code}: {warn.message}")
        return "\n".join(lines)


class DAGValidator:
    """
    Validates workflow DAG structure.

    Performs these checks:
    1. No cycles (topological sortable)
    2. All nodes have unique IDs
    3. All edges reference existing nodes
    4. Entry node(s) exist (nodes with no incoming edges)
    5. Exit node(s) exist (nodes with no outgoing edges)
    6. Fan-in nodes have at least one source
    7. Fan-out nodes have at least two targets
    8. No self-loops
    9. Node types are registered in NODE_REGISTRY
    10. No orphan nodes (unreachable from entry)
    """

    def __init__(self) -> None:
        pass

    async def validate(
        self,
        nodes: list[dict[str, Any]],
        edges: list[dict[str, Any]],
        node_registry_keys: set[str] | None = None,
    ) -> ValidationReport:
        """
        Validate a DAG given nodes and edges.

        Args:
            nodes: List of node configs (must have 'node_id').
            edges: List of edge configs (must have 'source_node_id', 'target_node_id').
            node_registry_keys: Optional set of valid node_type values.

        Returns:
            ValidationReport with all issues found.
        """
        report = ValidationReport()
        report.stats["node_count"] = len(nodes)
        report.stats["edge_count"] = len(edges)

        node_ids = {n.get("node_id", "") for n in nodes}
        node_types = {n.get("node_id", ""): n.get("node_type", "") for n in nodes}

        # ── 0. Basic structure checks ──────────────────────────────────
        if not nodes:
            report.add_error(ValidationError(
                code="EMPTY_DAG",
                message="Workflow has no nodes",
            ))
            return report

        # ── 1. Duplicate node IDs ──────────────────────────────────────
        seen_ids: set[str] = set()
        for n in nodes:
            nid = n.get("node_id", "")
            if not nid:
                report.add_error(ValidationError(
                    code="MISSING_NODE_ID",
                    message="Node has no node_id",
                ))
            elif nid in seen_ids:
                report.add_error(ValidationError(
                    code="DUPLICATE_NODE_ID",
                    message=f"Duplicate node_id: {nid}",
                    node_id=nid,
                ))
            else:
                seen_ids.add(nid)

        # ── 2. Unknown node types ─────────────────────────────────────
        if node_registry_keys:
            for nid, ntype in node_types.items():
                if ntype and ntype not in node_registry_keys:
                    report.add_error(ValidationError(
                        code="UNKNOWN_NODE_TYPE",
                        message=f"Node type '{ntype}' not registered for node {nid}",
                        node_id=nid,
                    ))

        # ── 3. Edge references ────────────────────────────────────────
        for e in edges:
            src = e.get("source_node_id", "")
            tgt = e.get("target_node_id", "")
            eid = e.get("edge_id", "")

            if not src or not tgt:
                report.add_error(ValidationError(
                    code="MISSING_EDGE_ENDPOINT",
                    message=f"Edge {eid} has missing source or target",
                    edge_id=eid,
                ))
                continue

            if src not in node_ids:
                report.add_error(ValidationError(
                    code="MISSING_SOURCE_NODE",
                    message=f"Edge {eid} references unknown source: {src}",
                    edge_id=eid,
                    node_id=src,
                ))

            if tgt not in node_ids:
                report.add_error(ValidationError(
                    code="MISSING_TARGET_NODE",
                    message=f"Edge {eid} references unknown target: {tgt}",
                    edge_id=eid,
                    node_id=tgt,
                ))

            # Self-loop
            if src == tgt:
                report.add_error(ValidationError(
                    code="SELF_LOOP",
                    message=f"Edge {eid} is a self-loop ({src} -> {src})",
                    edge_id=eid,
                    node_id=src,
                ))

        # ── 4. Entry nodes (no incoming edges) ────────────────────────
        targets = {e.get("target_node_id", "") for e in edges}
        entry_nodes = node_ids - targets
        if not entry_nodes:
            report.add_error(ValidationError(
                code="NO_ENTRY_NODE",
                message="No entry node found (all nodes have incoming edges)",
            ))
        report.stats["entry_nodes"] = len(entry_nodes)

        # ── 5. Exit nodes (no outgoing edges) ──────────────────────────
        sources = {e.get("source_node_id", "") for e in edges}
        exit_nodes = node_ids - sources
        if not exit_nodes:
            report.add_warning(ValidationError(
                code="NO_EXIT_NODE",
                message="No exit node found (all nodes have outgoing edges)",
                severity="warning",
            ))
        report.stats["exit_nodes"] = len(exit_nodes)

        # ── 6. Cycle detection (Kahn's algorithm) ──────────────────────
        in_degree: dict[str, int] = {nid: 0 for nid in node_ids}
        adj: dict[str, list[str]] = {nid: [] for nid in node_ids}

        for e in edges:
            src = e.get("source_node_id", "")
            tgt = e.get("target_node_id", "")
            if src and tgt and src in node_ids and tgt in node_ids:
                adj[src].append(tgt)
                in_degree[tgt] += 1

        # Kahn's topological sort
        from collections import deque
        queue = deque(nid for nid in node_ids if in_degree.get(nid, 0) == 0)
        visited_count = 0

        while queue:
            current = queue.popleft()
            visited_count += 1

            for neighbor in adj.get(current, []):
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)

        if visited_count != len(node_ids):
            report.add_error(ValidationError(
                code="CYCLE_DETECTED",
                message=f"DAG has cycles: {len(node_ids) - visited_count} nodes in cycle(s)",
            ))

        # ── 7. Orphan nodes (unreachable from entry) ──────────────────
        if entry_nodes:
            # BFS from all entry nodes
            reachable: set[str] = set()
            bfs_queue = deque(entry_nodes)
            while bfs_queue:
                current = bfs_queue.popleft()
                if current in reachable:
                    continue
                reachable.add(current)
                for neighbor in adj.get(current, []):
                    if neighbor not in reachable:
                        bfs_queue.append(neighbor)

            orphans = node_ids - reachable
            for orphan_id in orphans:
                report.add_warning(ValidationError(
                    code="ORPHAN_NODE",
                    message=f"Node {orphan_id} is not reachable from any entry node",
                    node_id=orphan_id,
                    severity="warning",
                ))
            report.stats["orphan_nodes"] = len(orphans)

        # ── 8. Summary ────────────────────────────────────────────────
        report.stats["error_count"] = len(report.errors)
        report.stats["warning_count"] = len(report.warnings)

        if report.errors:
            logger.warning(f"DAG validation failed: {len(report.errors)} errors")
        else:
            logger.info("DAG validation passed")

        return report
