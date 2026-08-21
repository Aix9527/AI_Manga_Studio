"""Multi-source ingest：把 Team / Production Intelligence / Feedback /
Prompt OS / Shot DNA 已有数据读入知识图谱（只读源，幂等重建）。"""

from __future__ import annotations

import json
from pathlib import Path

from backend.knowledge_graph.model import GraphNode
from backend.knowledge_graph.store import GraphStore


def _load_dict(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:  # noqa: BLE001
        return {}


def _load_list(path: Path) -> list:
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except Exception:  # noqa: BLE001
        return []


class KnowledgeGraphIngestor:
    """从各生产模块存储目录摄取节点与边。"""

    def __init__(self, store: GraphStore, root: str | Path = "storage"):
        self.store = store
        self.root = Path(root)

    # ------------------------------------------------------------ helpers
    def _node(self, node_id: str, node_type: str, label: str,
              properties: dict | None = None, project_id: str = "") -> GraphNode:
        return GraphNode(
            id=node_id, type=node_type, label=label,
            properties=properties or {}, project_id=project_id,
        )

    def _ingest_project(self, project_id: str) -> None:
        if not project_id:
            return
        if not self.store.has_node(project_id):
            self.store.upsert_node(self._node(project_id, "project", project_id))

    # ------------------------------------------------------------ team
    def _ingest_team(self) -> dict:
        counts = {"nodes": 0, "edges": 0}
        assignments = _load_dict(self.root / "team" / "assignments.json")
        reviews = _load_dict(self.root / "team" / "reviews.json")
        for row in assignments.values():
            aid = row.get("id", "")
            if not aid:
                continue
            project_id = row.get("project_id", "")
            episode_id = row.get("episode_id", "")
            self._ingest_project(project_id)
            if episode_id:
                self.store.upsert_node(self._node(
                    f"ep:{episode_id}", "episode", f"Episode {episode_id}", project_id=project_id))
            self.store.upsert_node(self._node(
                aid, "assignment",
                f"{episode_id} · {row.get('stage', '')} · {row.get('role', '')}",
                properties={
                    "status": row.get("status", ""),
                    "stage": row.get("stage", ""),
                    "role": row.get("role", ""),
                    "assignee_id": row.get("assignee_id", ""),
                    "task_id": row.get("task_id", ""),
                    "rework_count": row.get("rework_count", 0),
                },
                project_id=project_id,
            ))
            counts["nodes"] += 1
            if episode_id:
                self.store.upsert_edge(aid, f"ep:{episode_id}", "HAS_PHASE",
                                       {"stage": row.get("stage", "")})
                counts["edges"] += 1
            for dep in row.get("dependencies", []):
                self.store.upsert_edge(aid, dep, "DEPENDS_ON")
                counts["edges"] += 1
            for idx, art in enumerate(row.get("input_artifacts", [])):
                art_id = art.get("ref") if isinstance(art, dict) else str(art)
                if art_id:
                    self.store.upsert_node(self._node(
                        f"art:{art_id}", "artifact", art_id, project_id=project_id))
                    self.store.upsert_edge(aid, f"art:{art_id}", "USES")
                    counts["nodes"] += 1
                    counts["edges"] += 1
            for idx, art in enumerate(row.get("output_artifacts", [])):
                art_id = art.get("ref") if isinstance(art, dict) else str(art)
                if art_id:
                    self.store.upsert_node(self._node(
                        f"art:{art_id}", "artifact", art_id, project_id=project_id))
                    self.store.upsert_edge(f"art:{art_id}", aid, "PRODUCED")
                    counts["nodes"] += 1
                    counts["edges"] += 1
        for row in reviews.values():
            rid = row.get("id", "")
            aid = row.get("assignment_id", "")
            if not rid or not aid:
                continue
            self.store.upsert_node(self._node(
                rid, "review",
                f"评审 {row.get('verdict', '')} by {row.get('reviewer_role', '')}",
                properties={
                    "verdict": row.get("verdict", ""),
                    "reviewer_role": row.get("reviewer_role", ""),
                    "reviewer_id": row.get("reviewer_id", ""),
                },
            ))
            self.store.upsert_edge(rid, aid, "REVIEWED_BY")
            counts["nodes"] += 1
            counts["edges"] += 1
        return counts

    # ------------------------------------------------------------ production intelligence
    def _ingest_production_intelligence(self) -> dict:
        counts = {"nodes": 0, "edges": 0}
        events = _load_dict(self.root / "production_intelligence" / "events.json")
        for row in events.values():
            eid = row.get("id", "")
            if not eid:
                continue
            project_id = row.get("project_id", "")
            episode_id = row.get("episode_id", "")
            shot_id = row.get("shot_id", "")
            self._ingest_project(project_id)
            self.store.upsert_node(self._node(
                eid, "production_event", row.get("event_type", "event"),
                properties={
                    "event_type": row.get("event_type", ""),
                    "shot_id": shot_id,
                    "actor": row.get("actor", ""),
                    "payload": row.get("payload", {}),
                },
                project_id=project_id,
            ))
            counts["nodes"] += 1
            if episode_id:
                self.store.upsert_edge(eid, f"ep:{episode_id}", "EVENT_FOR")
                counts["edges"] += 1
            if shot_id:
                self.store.upsert_edge(eid, f"shot:{shot_id}", "EVENT_FOR")
                counts["edges"] += 1
        return counts

    # ------------------------------------------------------------ feedback
    def _ingest_feedback(self) -> dict:
        counts = {"nodes": 0, "edges": 0}
        events = _load_dict(self.root / "feedback" / "events.json")
        candidates = _load_dict(self.root / "feedback" / "candidates.json")
        for row in events.values():
            fid = row.get("id", "")
            target_id = row.get("target_id", "")
            if not fid:
                continue
            self.store.upsert_node(self._node(
                fid, "feedback", f"{row.get('kind', 'feedback')} → {target_id}",
                properties={
                    "kind": row.get("kind", ""),
                    "target_type": row.get("target_type", ""),
                    "target_id": target_id,
                    "severity": row.get("severity", ""),
                },
                project_id=row.get("project_id", ""),
            ))
            counts["nodes"] += 1
            if target_id:
                self.store.upsert_edge(fid, f"{row.get('target_type', '')}:{target_id}", "FEEDBACK_ON")
                counts["edges"] += 1
        for row in candidates.values():
            cid = row.get("id", "")
            if not cid:
                continue
            self.store.upsert_node(self._node(
                cid, "candidate",
                f"{row.get('target_type', '')} 候选 · {row.get('status', '')}",
                properties={
                    "target_type": row.get("target_type", ""),
                    "target_id": row.get("target_id", ""),
                    "status": row.get("status", ""),
                    "reason": row.get("reason", ""),
                },
                project_id=row.get("project_id", ""),
            ))
            counts["nodes"] += 1
        return counts

    # ------------------------------------------------------------ prompt os
    def _ingest_prompt_os(self) -> dict:
        counts = {"nodes": 0, "edges": 0}
        dna = _load_dict(self.root / "prompt_os" / "dna.json")
        for row in dna.values():
            did = row.get("id", "")
            if not did:
                continue
            self.store.upsert_node(self._node(
                did, "shot_dna", f"DNA · {row.get('name', did)}",
                properties={
                    "kind": row.get("kind", ""),
                    "name": row.get("name", ""),
                    "usage_count": row.get("usage_count", 0),
                },
            ))
            counts["nodes"] += 1
        designs = _load_dict(self.root / "prompt_os" / "shot_designs.json")
        for row in designs.values():
            sid = row.get("id", "")
            if not sid:
                continue
            self.store.upsert_node(self._node(
                f"sd:{sid}", "shot_design", f"ShotDesign {sid} · {row.get('status', '')}",
                properties={
                    "status": row.get("status", ""),
                    "version": row.get("version", ""),
                    "logline": (row.get("layers", {}) or {}).get("story", ""),
                },
                project_id=row.get("project_id", ""),
            ))
            counts["nodes"] += 1
        return counts

    # ------------------------------------------------------------ shot dna
    def _ingest_shot_dna(self) -> dict:
        counts = {"nodes": 0, "edges": 0}
        library = _load_dict(self.root / "shot_dna" / "library.json")
        entries = library.get("entries", {}) if isinstance(library, dict) else {}
        if isinstance(entries, dict):
            rows = list(entries.values())
        else:
            rows = entries if isinstance(entries, list) else []
        for row in rows:
            sid = row.get("id", "")
            if not sid:
                continue
            self.store.upsert_node(self._node(
                sid, "shot_dna", f"ShotDNA · {row.get('name', sid)}",
                properties={
                    "name": row.get("name", ""),
                    "category": row.get("category", ""),
                    "usage_count": row.get("usage_count", 0),
                },
            ))
            counts["nodes"] += 1
        return counts

    # ------------------------------------------------------------ run
    def ingest(self, *, clear: bool = True) -> dict:
        if clear:
            self.store.clear()
        total = {"nodes": 0, "edges": 0}
        for ingest in (self._ingest_team, self._ingest_production_intelligence,
                       self._ingest_feedback, self._ingest_prompt_os, self._ingest_shot_dna):
            counts = ingest()
            total["nodes"] += counts["nodes"]
            total["edges"] += counts["edges"]
        total["node_total"] = len(self.store.all_nodes())
        total["edge_total"] = len(self.store.all_edges())
        total["sources"] = ["team", "production_intelligence", "feedback", "prompt_os", "shot_dna"]
        return total
