"""Graph store（JSON 持久化，Phase 13.5-C 存储扩展受限结论后仍沿用 JSON，
KG 层只读摄取现有源数据，不承担高吞吐写入）。"""

from __future__ import annotations

import json
import threading
import uuid
from pathlib import Path

from backend.knowledge_graph.model import GraphEdge, GraphNode


def _new_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:10]}"


class GraphStore:
    def __init__(self, root: str | Path = "storage/knowledge_graph"):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._nodes: dict[str, dict] = self._load("nodes.json")
        self._edges: dict[str, dict] = self._load("edges.json")

    def _load(self, name: str) -> dict[str, dict]:
        path = self.root / name
        if not path.exists():
            return {}
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except Exception:  # noqa: BLE001
            return {}

    def _save(self, name: str, data: dict[str, dict]) -> None:
        path = self.root / name
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(path)

    # ------------------------------------------------------------ nodes
    def upsert_node(self, node: GraphNode) -> GraphNode:
        with self._lock:
            self._nodes[node.id] = node.to_dict()
            self._save("nodes.json", self._nodes)
        return node

    def has_node(self, node_id: str) -> bool:
        return node_id in self._nodes

    def get_node(self, node_id: str) -> dict | None:
        raw = self._nodes.get(node_id)
        return dict(raw) if raw else None

    def all_nodes(self) -> list[dict]:
        with self._lock:
            return [dict(raw) for raw in self._nodes.values()]

    def clear_nodes(self) -> None:
        with self._lock:
            self._nodes = {}
            self._save("nodes.json", self._nodes)

    # ------------------------------------------------------------ edges
    def upsert_edge(self, source: str, target: str, edge_type: str,
                    properties: dict | None = None) -> GraphEdge:
        edge_id = f"{source}:{target}:{edge_type}"
        with self._lock:
            edge = GraphEdge(
                id=edge_id,
                source=source,
                target=target,
                type=edge_type,
                properties=properties or {},
            )
            self._edges[edge_id] = edge.to_dict()
            self._save("edges.json", self._edges)
        return edge

    def get_edge(self, edge_id: str) -> dict | None:
        raw = self._edges.get(edge_id)
        return dict(raw) if raw else None

    def all_edges(self) -> list[dict]:
        with self._lock:
            return [dict(raw) for raw in self._edges.values()]

    def edges_for(self, node_id: str, edge_type: str | None = None) -> list[dict]:
        rows = [dict(raw) for raw in self._edges.values()
                if raw.get("source") == node_id or raw.get("target") == node_id]
        if edge_type:
            rows = [r for r in rows if r.get("type") == edge_type]
        return rows

    def clear_edges(self) -> None:
        with self._lock:
            self._edges = {}
            self._save("edges.json", self._edges)

    def clear(self) -> None:
        self.clear_nodes()
        self.clear_edges()
