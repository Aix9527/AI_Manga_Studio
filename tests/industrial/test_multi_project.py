"""Phase 13.5-A: Multi-Project Production Orchestrator tests."""

from __future__ import annotations

import pytest

from backend.multi_project.service import MultiProjectOrchestrator
from backend.orchestration.task_queue import TaskQueue


@pytest.fixture()
def orch(tmp_path):
    return MultiProjectOrchestrator(
        str(tmp_path / "mp"),
        task_queue=TaskQueue(str(tmp_path / "tasks")),
    )


def test_season_lifecycle(orch):
    season = orch.seasons.create_season("PROJ-A", season_no=1, name="归墟第二部", target_episodes=100)
    assert season.season_no == 1
    orch.seasons.attach_episode(season.id, "EP-001")
    orch.seasons.attach_episode(season.id, "EP-002")
    orch.seasons.set_status(season.id, "production")
    seasons = orch.seasons.list("PROJ-A")
    assert len(seasons) == 1
    assert seasons[0].episode_ids == ["EP-001", "EP-002"]
    assert orch.seasons.stats("PROJ-A")["seasons"] == 1
    with pytest.raises(ValueError, match="invalid season status"):
        orch.seasons.set_status(season.id, "bogus")


def test_resource_planner(orch):
    resource = orch.resources.plan("PROJ-A", season_id="SN-1", gpu_capacity=3, budget_allocated=5000, priority=4)
    assert resource.priority == 4
    assert orch.resources.stats()["gpu_capacity"] == 3
    with pytest.raises(ValueError, match="priority"):
        orch.resources.plan("PROJ-B", priority=9)


def test_gpu_queue_recommend_scoring(orch):
    queue = orch.task_queue
    queue.enqueue("video_chain", {"deadline": "2099-01-01T00:00:00"}, project_id="PROJ-LOW", priority=1)
    queue.enqueue("video_chain", {"deadline": "2026-08-06T23:59:59"}, project_id="PROJ-HIGH", priority=5)
    rec = orch.gpu_queue.recommend(limit=10)
    assert rec["queued"] == 2
    assert rec["recommended"][0]["project_id"] == "PROJ-HIGH"
    assert rec["recommended"][0]["score"] > rec["recommended"][1]["score"]
    assert "推荐仅参考" in rec["note"]


def test_budget_controller(orch):
    orch.budget.set_policy("PROJ-B", monthly_limit=1000, warning_threshold=0.8, hard_limit=1.0)
    orch.budget.record_cost("PROJ-B", 850)
    summary = orch.budget.summary("PROJ-B")
    assert summary["status"] == "warning"
    assert summary["ratio"] == 0.85
    orch.budget.record_cost("PROJ-B", 200)
    assert orch.budget.summary("PROJ-B")["status"] == "exceeded"
    auth = orch.budget.authorize("PROJ-B", 10)
    assert auth["allowed"] is False
    assert auth["requires_approval"] is True
    override = orch.budget.approve_override("PROJ-B", reviewer="producer")
    assert override["approved"] is True


def test_budget_ok_path(orch):
    orch.budget.set_policy("PROJ-C", monthly_limit=1000)
    orch.budget.record_cost("PROJ-C", 100)
    assert orch.budget.summary("PROJ-C")["status"] == "ok"
    assert orch.budget.authorize("PROJ-C", 50)["allowed"] is True


def test_scheduler_dependency_and_dispatch(orch):
    orch.seasons.create_season("PROJ-S", season_no=1)
    season = orch.seasons.list("PROJ-S")[0]
    orch.seasons.attach_episode(season.id, "EP-1")
    orch.seasons.attach_episode(season.id, "EP-2")
    orch.scheduler.register_dependency("EP-2", requires=["character_version"])
    plan = orch.scheduler.build_plan("PROJ-S", max_parallel=2)
    # production readiness is BLOCKED without assets -> episodes blocked
    assert plan["blocked"]
    assert all("production_not_ready" in b["reasons"] for b in plan["blocked"])


def test_scheduler_approve_dispatch(orch):
    orch.seasons.create_season("PROJ-T", season_no=1)
    season = orch.seasons.list("PROJ-T")[0]
    orch.seasons.attach_episode(season.id, "EP-1")
    orch.scheduler.readiness = _ReadyMatrixStub()
    plan = orch.scheduler.build_plan("PROJ-T", max_parallel=1)
    with pytest.raises(ValueError, match="only approved"):
        orch.scheduler.dispatch_plan(plan["id"])
    orch.scheduler.approve_plan(plan["id"], reviewer="producer")
    result = orch.scheduler.dispatch_plan(plan["id"])
    assert result["status"] == "dispatched"
    assert len(result["dispatched"]) == 1
    assert orch.task_queue.get(result["dispatched"][0]).task_type == "video_chain"


class _ReadyMatrixStub:
    """Readiness matrix stub: everything production-ready."""

    def check_project(self, project_id: str) -> dict:
        return {"project_id": project_id, "status": "READY", "gates": {}, "missing": []}


def test_audit_trail(orch):
    orch.seasons.create_season("PROJ-A", season_no=1)
    orch.resources.plan("PROJ-A", gpu_capacity=2)
    audit = orch.audit()
    assert len(audit) >= 2
    assert any(entry["action"] == "season.create" for entry in audit)