"""Knowledge Graph service：统计 / 检索 / 邻居 / 路径 / 智能推荐。"""

from __future__ import annotations

from collections import deque

from backend.knowledge_graph.ingest import KnowledgeGraphIngestor
from backend.knowledge_graph.model import NODE_TYPES
from backend.knowledge_graph.store import GraphStore


class KnowledgeGraphService:
    def __init__(self, store: GraphStore | None = None, root: str = "storage"):
        self.store = store or GraphStore()
        self.ingestor = KnowledgeGraphIngestor(self.store, root=root)

    # ------------------------------------------------------------ stats
    def stats(self) -> dict:
        nodes = self.store.all_nodes()
        edges = self.store.all_edges()
        by_type: dict[str, int] = {}
        for node in nodes:
            t = node.get("type", "")
            by_type[t] = by_type.get(t, 0) + 1
        by_edge: dict[str, int] = {}
        for edge in edges:
            t = edge.get("type", "")
            by_edge[t] = by_edge.get(t, 0) + 1
        by_project: dict[str, int] = {}
        for node in nodes:
            p = node.get("project_id", "") or "(global)"
            by_project[p] = by_project.get(p, 0) + 1
        return {
            "nodes": len(nodes),
            "edges": len(edges),
            "node_types": NODE_TYPES,
            "by_type": by_type,
            "by_edge": by_edge,
            "by_project": by_project,
        }

    # ------------------------------------------------------------ queries
    def nodes(self, *, node_type: str | None = None, project_id: str | None = None,
              q: str | None = None, limit: int = 50) -> list[dict]:
        rows = self.store.all_nodes()
        if node_type:
            rows = [r for r in rows if r.get("type") == node_type]
        if project_id:
            rows = [r for r in rows if r.get("project_id") == project_id]
        if q:
            needle = q.lower()
            rows = [r for r in rows if needle in str(r.get("label", "")).lower()
                    or needle in str(r.get("id", "")).lower()
                    or needle in str(r.get("properties", {})).lower()]
        rows.sort(key=lambda r: r.get("id", ""))
        return rows[:limit]

    def get_node(self, node_id: str) -> dict:
        node = self.store.get_node(node_id)
        if not node:
            raise KeyError(f"node not found: {node_id}")
        return node

    def neighbors(self, node_id: str, *, edge_type: str | None = None,
                  depth: int = 1, limit: int = 50) -> dict:
        self.get_node(node_id)
        edges = self.store.edges_for(node_id, edge_type=edge_type)
        seen: dict[str, dict] = {}
        for edge in edges:
            other = edge["target"] if edge["source"] == node_id else edge["source"]
            node = self.store.get_node(other)
            if node:
                seen[other] = {
                    "node": node,
                    "edge": {"type": edge.get("type", ""), "properties": edge.get("properties", {})},
                }
        return {
            "node_id": node_id,
            "depth": depth,
            "neighbors": list(seen.values())[:limit],
            "count": len(seen),
        }

    def paths(self, from_id: str, to_id: str, *, limit: int = 3) -> dict:
        self.get_node(from_id)
        self.get_node(to_id)
        if from_id == to_id:
            return {"paths": [[{"id": from_id, "type": "self"}]]}
        adj: dict[str, list[tuple[str, str]]] = {}
        for edge in self.store.all_edges():
            adj.setdefault(edge["source"], []).append((edge["target"], edge.get("type", "")))
            adj.setdefault(edge["target"], []).append((edge["source"], edge.get("type", "")))
        found: list[list[dict]] = []
        visited: set[str] = set()
        queue: deque[tuple[str, list[dict]]] = deque([(from_id, [{"id": from_id, "edge": ""}])])
        visited.add(from_id)
        while queue and len(found) < limit:
            current, path = queue.popleft()
            for nxt, edge_type in adj.get(current, []):
                if nxt in visited and len(found) > 0:
                    continue
                new_path = path + [{"id": nxt, "edge": edge_type}]
                if nxt == to_id:
                    found.append(new_path)
                    if len(found) >= limit:
                        break
                    continue
                if nxt not in visited:
                    visited.add(nxt)
                    queue.append((nxt, new_path))
        return {"from": from_id, "to": to_id, "paths": found}

    def search(self, q: str, *, limit: int = 20) -> dict:
        rows = self.nodes(q=q, limit=limit)
        return {"query": q, "results": rows, "count": len(rows)}

    # ------------------------------------------------------------ recommend
    def recommend(self, node_id: str, *, limit: int = 5) -> dict:
        """基于共享邻居与标签的关联推荐（不自动修改任何资产，仅建议）。"""
        node = self.get_node(node_id)
        node_type = node.get("type", "")
        my_edges = self.store.edges_for(node_id)
        my_neighbors = {e["source"] if e["target"] == node_id else e["target"] for e in my_edges}
        scores: dict[str, float] = {}
        for other in self.store.all_nodes():
            oid = other.get("id", "")
            if oid == node_id:
                continue
            score = 0.0
            if other.get("type") == node_type:
                score += 1.0
            other_edges = self.store.edges_for(oid)
            shared = 0
            for e in other_edges:
                nbr = e["source"] if e["target"] == oid else e["target"]
                if nbr in my_neighbors:
                    shared += 1
            score += shared * 0.5
            if score > 0:
                scores[oid] = score
        ranked = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)[:limit]
        return {
            "node_id": node_id,
            "recommendations": [
                {"node": self.store.get_node(oid), "score": round(sc, 3)}
                for oid, sc in ranked
            ],
            "note": "仅建议，不自动修改生产资产",
        }

    def ingest(self, *, clear: bool = True) -> dict:
        return self.ingestor.ingest(clear=clear)
