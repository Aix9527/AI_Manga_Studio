"""Phase 13.7: Production Knowledge Graph tests（GPT Priority 2）.

多源摄取（Team / Production Intelligence / Feedback / Prompt OS / Shot DNA）、
统计 / 检索 / 邻居 / 路径 / 智能推荐 / 幂等。
"""

from __future__ import annotations

import json

import pytest

from backend.knowledge_graph.service import KnowledgeGraphService
from backend.knowledge_graph.store import GraphStore


@pytest.fixture()
def service(tmp_path):
    store = GraphStore(str(tmp_path / "kg"))
    return KnowledgeGraphService(store=store, root=str(tmp_path))


def _seed_sources(root):
    (root / "team").mkdir(parents=True, exist_ok=True)
    (root / "production_intelligence").mkdir(parents=True, exist_ok=True)
    (root / "feedback").mkdir(parents=True, exist_ok=True)
    (root / "prompt_os").mkdir(parents=True, exist_ok=True)
    (root / "shot_dna").mkdir(parents=True, exist_ok=True)

    (root / "team" / "assignments.json").write_text(json.dumps({
        "ASG-1": {"id": "ASG-1", "project_id": "P1", "episode_id": "EP1", "stage": "planning",
                  "role": "Producer", "status": "done", "dependencies": [],
                  "input_artifacts": [], "output_artifacts": [{"ref": "plan-1"}],
                  "assignee_id": "p1", "task_id": "T-1", "rework_count": 0},
        "ASG-2": {"id": "ASG-2", "project_id": "P1", "episode_id": "EP1", "stage": "script",
                  "role": "Writer", "status": "done", "dependencies": ["ASG-1"],
                  "input_artifacts": [{"ref": "plan-1"}], "output_artifacts": [{"ref": "script-1"}],
                  "assignee_id": "w1", "task_id": "T-2", "rework_count": 1},
    }, ensure_ascii=False), encoding="utf-8")
    (root / "team" / "reviews.json").write_text(json.dumps({
        "RVW-1": {"id": "RVW-1", "assignment_id": "ASG-1", "verdict": "approve",
                  "reviewer_role": "Producer", "reviewer_id": "p1"},
        "RVW-2": {"id": "RVW-2", "assignment_id": "ASG-2", "verdict": "reject",
                  "reviewer_role": "Planner", "reviewer_id": "pl1"},
    }, ensure_ascii=False), encoding="utf-8")
    (root / "production_intelligence" / "events.json").write_text(json.dumps({
        "EV-1": {"id": "EV-1", "project_id": "P1", "episode_id": "EP1", "shot_id": "S1",
                 "event_type": "generation_end", "actor": "worker", "payload": {"qc": 0.8}},
    }, ensure_ascii=False), encoding="utf-8")
    (root / "feedback" / "events.json").write_text(json.dumps({
        "FB-1": {"id": "FB-1", "project_id": "P1", "target_type": "character",
                 "target_id": "CH-1", "kind": "expression_forced", "severity": "medium"},
    }, ensure_ascii=False), encoding="utf-8")
    (root / "prompt_os" / "dna.json").write_text(json.dumps({
        "DNA-1": {"id": "DNA-1", "kind": "continuity", "name": "人物状态继承", "usage_count": 3},
    }, ensure_ascii=False), encoding="utf-8")
    (root / "prompt_os" / "shot_designs.json").write_text(json.dumps({
        "SD-1": {"id": "SD-1", "status": "approved", "version": "v1",
                 "layers": {"story": "少年进入地下遗迹"}, "project_id": "P1"},
    }, ensure_ascii=False), encoding="utf-8")
    (root / "shot_dna" / "library.json").write_text(json.dumps({
        "entries": {
            "SHDNA-1": {"id": "SHDNA-1", "name": "慢推", "category": "camera", "usage_count": 5},
        },
    }, ensure_ascii=False), encoding="utf-8")


# ---------------------------------------------------------------- ingest
def test_ingest_all_sources(service, tmp_path):
    _seed_sources(tmp_path)
    result = service.ingest()
    assert result["node_total"] >= 8
    assert result["edge_total"] >= 5
    stats = service.stats()
    assert stats["nodes"] == result["node_total"]
    assert stats["edges"] == result["edge_total"]
    types = stats["by_type"]
    assert types.get("assignment") == 2
    assert types.get("episode", 0) >= 1
    assert types.get("production_event", 0) >= 1
    assert types.get("feedback", 0) >= 1
    assert types.get("shot_dna", 0) >= 1


def test_ingest_empty_sources(service):
    result = service.ingest()
    assert result["node_total"] == 0
    assert result["edge_total"] == 0
    stats = service.stats()
    assert stats["nodes"] == 0 and stats["edges"] == 0


def test_ingest_idempotent(service, tmp_path):
    _seed_sources(tmp_path)
    first = service.ingest()
    second = service.ingest(clear=True)
    assert second["node_total"] == first["node_total"]
    assert second["edge_total"] == first["edge_total"]


# ---------------------------------------------------------------- queries
def test_nodes_filter_and_search(service, tmp_path):
    _seed_sources(tmp_path)
    service.ingest()
    assignments = service.nodes(node_type="assignment")
    assert len(assignments) == 2
    found = service.search("少年进入地下遗迹")
    assert len(found["results"]) >= 1
    ep_nodes = service.nodes(node_type="episode")
    assert len(ep_nodes) == 1
    assert ep_nodes[0]["id"] == "ep:EP1"


def test_neighbors(service, tmp_path):
    _seed_sources(tmp_path)
    service.ingest()
    nbr = service.neighbors("ASG-1")
    # ASG-1 邻居：ep:EP1（HAS_PHASE）+ ASG-2（DEPENDS_ON 反向）+ RVW-1（REVIEWED_BY 反向）+ art:plan-1（PRODUCED）
    ids = {n["node"]["id"] for n in nbr["neighbors"]}
    assert "ep:EP1" in ids
    assert "ASG-2" in ids
    assert "RVW-1" in ids
    assert "art:plan-1" in ids


def test_paths(service, tmp_path):
    _seed_sources(tmp_path)
    service.ingest()
    result = service.paths("RVW-1", "ASG-2")
    assert len(result["paths"]) >= 1
    # RVW-1 → ASG-1 → ASG-2（或 RVW-1 → ASG-1 经由 DEPENDS_ON）
    path_ids = [p["id"] for p in result["paths"][0]]
    assert path_ids[0] == "RVW-1"
    assert path_ids[-1] == "ASG-2"


def test_recommend(service, tmp_path):
    _seed_sources(tmp_path)
    service.ingest()
    rec = service.recommend("ASG-1")
    assert "recommendations" in rec
    assert rec["note"] == "仅建议，不自动修改生产资产"
    # 与 ASG-2 同类型（assignment）且有共享邻居 → 应被推荐
    ids = [r["node"]["id"] for r in rec["recommendations"]]
    assert "ASG-2" in ids


def test_node_not_found(service):
    with pytest.raises(KeyError):
        service.get_node("NOPE")
    with pytest.raises(KeyError):
        service.neighbors("NOPE")
