"""Phase 13.5-C: Team Collaboration tests (状态机 / 定向返工 / 审计 / 人工门)."""

from __future__ import annotations

import pytest

from backend.team.service import TeamService


@pytest.fixture()
def service(tmp_path):
    return TeamService(str(tmp_path / "team"))


def _create_team(service: TeamService, project: str = "P1") -> dict:
    return service.create_team(
        project_id=project, name="测试团队", actor="admin", reason="初始化团队",
    )


def _assign(service: TeamService, project: str = "P1", episode: str = "EP1",
            stage: str = "planning", role: str = "Producer", **kw) -> dict:
    return service.assign(
        project_id=project, episode_id=episode, stage=stage, role=role,
        actor="admin", reason="分派任务", **kw,
    )


# ---------------------------------------------------------------- team
def test_create_team_and_role_bindings(service):
    team = _create_team(service)
    assert team["status"] == "active"
    assert set(team["role_bindings"]) == {
        "Producer", "Planner", "Writer", "Director", "Editor", "Sound",
        "Production", "Reviewer", "Analyst",
    }
    overview = service.get_team("P1")
    assert overview["team"]["id"] == team["id"]
    with pytest.raises(ValueError, match="invalid role"):
        service.create_team(project_id="PX", name="x", role_bindings={"Boss": []}, actor="a", reason="r")


def test_team_not_found(service):
    with pytest.raises(KeyError):
        service.get_team("NOPE")


# ---------------------------------------------------------------- assign / start
def test_assign_creates_assigned_with_audit(service):
    _create_team(service)
    a = _assign(service)
    assert a["status"] == "assigned"
    assert a["stage"] == "planning"
    assert a["attempt"] == 1
    audit = service.audit("P1")["audit"]
    assert any(r["event"] == "assigned" and r["assignment_id"] == a["id"] for r in audit)
    with pytest.raises(ValueError, match="invalid stage"):
        _assign(service, stage="bogus")
    with pytest.raises(ValueError, match="invalid assignee_type"):
        _assign(service, assignee_type="robot")


def test_start_transition(service):
    _create_team(service)
    a = _assign(service)
    a2 = service.start(a["id"], actor="agent", reason="开工")
    assert a2["status"] == "in_progress"
    assert a2["started_at"]
    with pytest.raises(ValueError, match="illegal transition"):
        service.complete(a["id"], actor="x", reason="r")


# ---------------------------------------------------------------- review gate
def test_review_requires_evidence_and_owner(service):
    _create_team(service)
    a = _assign(service, stage="script", role="Writer")
    service.start(a["id"], actor="writer-agent", reason="开始写作")
    with pytest.raises(ValueError, match="evidence"):
        service.review(assignment_id=a["id"], reviewer_role="Writer", reviewer_id="w1",
                       verdict="approve", actor="w1", reason="无证据")
    with pytest.raises(ValueError, match="Review Owner"):
        service.review(assignment_id=a["id"], reviewer_role="Director", reviewer_id="d1",
                       verdict="approve", evidence={"ok": True}, actor="d1", reason="错角色")


def test_review_approve_flow(service):
    _create_team(service)
    a = _assign(service, stage="planning", role="Producer")
    service.start(a["id"], actor="p-agent", reason="开工")
    done = service.review(assignment_id=a["id"], reviewer_role="Producer", reviewer_id="p1",
                          verdict="approve", evidence={"rules": {"readiness": "pass"}},
                          comments="通过", actor="p1", reason="评审通过")
    assert done["status"] == "approved"
    detail = service.get_assignment(a["id"])
    assert len(detail["reviews"]) == 1
    assert len(detail["audit"]) >= 2  # submitted + approved


def test_review_reject_then_directed_rework(service):
    _create_team(service)
    a = _assign(service, episode="EP1", stage="qc", role="Reviewer")
    service.start(a["id"], actor="qc-agent", reason="开始质检")
    rejected = service.review(assignment_id=a["id"], reviewer_role="Reviewer", reviewer_id="qc1",
                              verdict="reject", evidence={"qc_failed": True},
                              comments="动作不自然", actor="qc1", reason="QC 失败")
    assert rejected["status"] == "rework"
    with pytest.raises(ValueError, match="invalid issue_category"):
        service.rework(assignment_id=a["id"], issue_category="unknown", actor="a", reason="r")
    routed = service.rework(assignment_id=a["id"], issue_category="motion",
                            evidence={"score": 0.4}, actor="orchestrator", reason="定向返工")
    assert routed["status"] == "assigned"
    assert routed["stage"] == "storyboard"      # motion → storyboard
    assert routed["role"] == "Director"          # motion → Director
    assert routed["attempt"] == 2
    assert routed["rework_count"] == 1


def test_illegal_transitions_rejected(service):
    _create_team(service)
    a = _assign(service)
    # planned 不允许直接 done
    with pytest.raises(ValueError, match="illegal transition"):
        service._transition(a["id"], "done", event="x", actor="a", reason="r")
    # in_progress 不允许直接 approved
    service.start(a["id"], actor="a", reason="r")
    with pytest.raises(ValueError, match="illegal transition"):
        service._transition(a["id"], "approved", event="x", actor="a", reason="r")
    stats = service.stats()
    assert stats["illegal_transitions"] == 0


# ---------------------------------------------------------------- blocked / fail
def test_blocked_unblock_fail(service):
    _create_team(service)
    a = _assign(service)
    b = service.block(a["id"], actor="a", reason="依赖缺失")
    assert b["status"] == "blocked"
    assert b["blocked_reason"] == "依赖缺失"
    u = service.unblock(a["id"], actor="a", reason="依赖就绪")
    assert u["status"] == "assigned"
    assert u["blocked_reason"] == ""
    service.start(a["id"], actor="a", reason="r")
    f = service.fail(a["id"], actor="a", reason="不可恢复")
    assert f["status"] == "failed"


# ---------------------------------------------------------------- escalate / complete
def test_escalate_requires_approval_id(service):
    _create_team(service)
    a = _assign(service, stage="generation", role="Production")
    with pytest.raises(ValueError, match="approval_id"):
        service.escalate(assignment_id=a["id"], actor="a", reason="升级")
    service.start(a["id"], actor="a", reason="r")
    e = service.review(assignment_id=a["id"], reviewer_role="Reviewer", reviewer_id="qc1",
                       verdict="escalate", evidence={"retry_exhausted": True},
                       actor="qc1", reason="重试耗尽")
    assert e["status"] == "escalated"
    # retry：escalated → assigned（人工批准）
    r = service.escalate(assignment_id=a["id"], decision="retry", approval_id="AP-1",
                         actor="admin", reason="人工批准重试")
    assert r["status"] == "assigned"
    assert r["attempt"] == 1


def test_rework_exhausted_escalates(service):
    _create_team(service)
    a = _assign(service, stage="generation", role="Production", max_attempts=2)
    service.start(a["id"], actor="a", reason="r")
    service.review(assignment_id=a["id"], reviewer_role="Reviewer", reviewer_id="qc1",
                   verdict="reject", evidence={"qc_failed": True}, actor="qc1", reason="QC 失败")
    service.rework(assignment_id=a["id"], issue_category="character_identity",
                   actor="o", reason="返工1")  # attempt 2
    service.start(a["id"], actor="a", reason="r")
    service.review(assignment_id=a["id"], reviewer_role="Reviewer", reviewer_id="qc1",
                   verdict="reject", evidence={"qc_failed": True}, actor="qc1", reason="QC 失败")
    escalated = service.rework(assignment_id=a["id"], issue_category="character_identity",
                               actor="o", reason="返工2 超限")
    assert escalated["status"] == "escalated"


def test_final_complete_requires_approval_id(service):
    _create_team(service)
    a = _assign(service, stage="final", role="Producer")
    service.start(a["id"], actor="a", reason="r")
    with pytest.raises(ValueError, match="approval_id"):
        service.review(assignment_id=a["id"], reviewer_role="Producer", reviewer_id="p1",
                       verdict="approve", evidence={"lock": True}, actor="p1", reason="锁定成片")
    ok = service.review(assignment_id=a["id"], reviewer_role="Producer", reviewer_id="p1",
                        verdict="approve", evidence={"lock": True}, approval_id="AP-FINAL",
                        actor="p1", reason="人工批准成片锁定")
    assert ok["status"] == "approved"
    with pytest.raises(ValueError, match="approval_id"):
        service.complete(a["id"], actor="p1", reason="完成")
    done = service.complete(a["id"], actor="p1", reason="完成", approval_id="AP-FINAL")
    assert done["status"] == "done"
    assert done["completed_at"]


# ---------------------------------------------------------------- views / stats
def test_flow_artifacts_audit_stats(service):
    _create_team(service)
    a1 = _assign(service, episode="EP1", stage="planning", role="Producer",
                 input_artifacts=[{"ref": "episode-EP1"}])
    a2 = _assign(service, episode="EP1", stage="script", role="Writer",
                 dependencies=[a1["id"]])
    flow = service.flow("P1")
    assert flow["episodes"][0]["episode_id"] == "EP1"
    assert flow["episodes"][0]["assignments"] == 2
    art = service.artifacts(project_id="P1", episode_id="EP1")
    assert art["traceable"] is True
    assert art["input_artifacts"][0]["assignment_id"] == a1["id"]
    audits = service.audit("P1")["audit"]
    assert len(audits) >= 2
    stats = service.stats()
    assert stats["assignments"] == 2
    assert stats["new_queue_count"] == 0
    assert stats["audit_coverage"] == 1.0
    assert stats["governance"]["human_approval"] is True
    assert stats["governance"]["auto_apply"] is False


# ---------------------------------------------------------------- e2e C1
def test_episode_end_to_end_closed_loop(service):
    """1 集端到端：策划→剧本→分镜→生成→QC失败→定向返工→重生成→QC通过→剪辑→声音→最终审批→done."""
    _create_team(service)
    a = _assign(service, episode="EP1", stage="planning", role="Producer")
    service.start(a["id"], actor="producer-agent", reason="开始")
    service.review(assignment_id=a["id"], reviewer_role="Producer", reviewer_id="p1",
                   verdict="approve", evidence={"plan_ok": True}, actor="p1", reason="策划通过")
    service.complete(a["id"], actor="p1", reason="策划完成")

    a = _assign(service, episode="EP1", stage="script", role="Writer")
    service.start(a["id"], actor="writer-agent", reason="开始")
    service.review(assignment_id=a["id"], reviewer_role="Planner", reviewer_id="pl1",
                   verdict="approve", evidence={"script_ok": True}, actor="pl1", reason="剧本通过")
    service.complete(a["id"], actor="pl1", reason="剧本完成")

    a = _assign(service, episode="EP1", stage="storyboard", role="Director")
    service.start(a["id"], actor="director-agent", reason="开始")
    service.review(assignment_id=a["id"], reviewer_role="Director", reviewer_id="d1",
                   verdict="approve", evidence={"sb_ok": True}, actor="d1", reason="分镜通过")
    service.complete(a["id"], actor="d1", reason="分镜完成")

    a = _assign(service, episode="EP1", stage="generation", role="Production",
                task_id="TASK-1", max_attempts=3)
    service.start(a["id"], actor="worker", reason="开始生成")
    # QC 失败
    service.review(assignment_id=a["id"], reviewer_role="Reviewer", reviewer_id="qc1",
                   verdict="reject", evidence={"qc_failed": True, "issue": "motion"},
                   actor="qc1", reason="动作不符合物理")
    routed = service.rework(assignment_id=a["id"], issue_category="motion",
                            actor="orchestrator", reason="定向返工")
    assert routed["stage"] == "storyboard"
    assert routed["role"] == "Director"
    # 返工：分镜修正（motion → storyboard/Director）
    service.start(a["id"], actor="director-agent", reason="分镜修正")
    service.review(assignment_id=a["id"], reviewer_role="Director", reviewer_id="d1",
                   verdict="approve", evidence={"storyboard_fixed": True},
                   actor="d1", reason="分镜修正通过")
    service.complete(a["id"], actor="d1", reason="分镜修正完成")
    # 重生成
    a = _assign(service, episode="EP1", stage="generation", role="Production",
                task_id="TASK-2", max_attempts=3)
    service.start(a["id"], actor="worker", reason="重生成")
    service.review(assignment_id=a["id"], reviewer_role="Reviewer", reviewer_id="qc1",
                   verdict="approve", evidence={"qc_pass": True}, actor="qc1", reason="QC 通过")
    service.complete(a["id"], actor="qc1", reason="生成完成")

    a = _assign(service, episode="EP1", stage="editing", role="Editor")
    service.start(a["id"], actor="editor-agent", reason="开始剪辑")
    service.review(assignment_id=a["id"], reviewer_role="Editor", reviewer_id="ed1",
                   verdict="approve", evidence={"edit_ok": True}, actor="ed1", reason="剪辑通过")
    service.complete(a["id"], actor="ed1", reason="剪辑完成")

    a = _assign(service, episode="EP1", stage="sound", role="Sound")
    service.start(a["id"], actor="sound-agent", reason="开始声音")
    service.review(assignment_id=a["id"], reviewer_role="Sound", reviewer_id="s1",
                   verdict="approve", evidence={"audio_sync": True}, actor="s1", reason="声音通过")
    service.complete(a["id"], actor="s1", reason="声音完成")

    a = _assign(service, episode="EP1", stage="final", role="Producer")
    service.start(a["id"], actor="producer-agent", reason="开始成片")
    service.review(assignment_id=a["id"], reviewer_role="Producer", reviewer_id="p1",
                   verdict="approve", evidence={"lock": True}, approval_id="AP-FINAL",
                   actor="p1", reason="最终人工审批")
    done = service.complete(a["id"], actor="p1", reason="成片锁定", approval_id="AP-FINAL")
    assert done["status"] == "done"

    stats = service.stats()
    assert stats["assignments"] == 8
    assert stats["audit_coverage"] == 1.0
    assert stats["illegal_transitions"] == 0
    assert stats["infinite_rework"] == 0
    flow = service.flow("P1")
    episode = flow["episodes"][0]
    assert episode["assignments"] == 8
    assert episode["rework_count"] == 1
    assert episode["waiting_human"] == 0
