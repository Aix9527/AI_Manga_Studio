"""Phase 13.5-C: C2 分级验收 tests（3 集并行验证，GPT Priority 1）.

重点验证并发 / 依赖 / 返工 / 恢复，不新增功能：
- C2-1 三集并行全链路（每集 9 阶段 → done）
- C2-2 跨集依赖链（EP2 任务依赖 EP1 资产）
- C2-3 多线程并发状态迁移（RLock 安全、审计不丢）
- C2-4 重启恢复（重新实例化 TeamService 后状态/审计一致并继续完成）
- C2-5 三集交错定向返工（generation QC fail + sound 返工）
"""

from __future__ import annotations

import threading

import pytest

from backend.team.model import STAGE_REVIEW_OWNER
from backend.team.service import TeamService

STAGES = [
    ("planning", "Producer"), ("script", "Writer"), ("storyboard", "Director"),
    ("assets", "Director"), ("generation", "Production"), ("qc", "Reviewer"),
    ("editing", "Editor"), ("sound", "Sound"), ("final", "Producer"),
]


@pytest.fixture()
def service(tmp_path):
    return TeamService(str(tmp_path / "team"))


def _create_team(service: TeamService, project: str = "P1") -> dict:
    return service.create_team(project_id=project, name="C2 并行团队", actor="admin", reason="C2 初始化")


def _assign_episode(service: TeamService, project: str, episode: str,
                    *, task_prefix: str = "TASK", rework_stage: str | None = None) -> list[dict]:
    rows = []
    for i, (stage, role) in enumerate(STAGES):
        a = service.assign(
            project_id=project, episode_id=episode, stage=stage, role=role,
            assignee_type="agent", assignee_id=f"{episode}-{role}",
            task_id=f"{task_prefix}-{episode}-{i}",
            actor="admin", reason=f"分派{stage}",
        )
        rows.append(a)
    return rows


def _run_episode_ok(service: TeamService, assignment: dict, *, reviewer: str) -> None:
    current = service.get_assignment(assignment["id"])["assignment"]
    if current["status"] == "assigned":
        service.start(assignment["id"], actor=assignment["assignee_id"], reason="开工")
    service.review(
        assignment_id=assignment["id"],
        reviewer_role=STAGE_REVIEW_OWNER[assignment["stage"]],
        reviewer_id=reviewer,
        verdict="approve",
        evidence={"ok": True},
        actor=reviewer, reason="评审通过",
        approval_id="AP-FINAL" if assignment["stage"] == "final" else "",
    )
    service.complete(
        assignment["id"], actor=reviewer, reason="完成",
        approval_id="AP-FINAL" if assignment["stage"] == "final" else "",
    )


def _run_episode_with_rework(service: TeamService, assignment: dict,
                             *, issue_category: str, reviewer: str = "qc1") -> None:
    """generation 任务：QC 失败 → 定向返工 → 重生成 → QC 通过."""
    service.start(assignment["id"], actor=assignment["assignee_id"], reason="开工")
    service.review(
        assignment_id=assignment["id"], reviewer_role=STAGE_REVIEW_OWNER[assignment["stage"]], reviewer_id="qc1",
        verdict="reject", evidence={"qc_failed": True, "issue": issue_category},
        actor="qc1", reason="QC 失败",
    )
    service.rework(assignment_id=assignment["id"], issue_category=issue_category,
                   actor="orchestrator", reason="定向返工")
    # 返工后 stage 变为目标阶段，按目标阶段 Owner 评审
    target = service.get_assignment(assignment["id"])["assignment"]
    service.start(assignment["id"], actor=target["assignee_id"], reason="返工修正")
    service.review(
        assignment_id=assignment["id"], reviewer_role=target["role"],
        reviewer_id=reviewer, verdict="approve",
        evidence={"fixed": True}, actor=reviewer, reason="返工后通过",
    )
    service.complete(assignment["id"], actor=reviewer, reason="完成")


# ---------------------------------------------------------------- C2-1
def test_c2_three_episodes_parallel_closed_loop(service):
    _create_team(service)
    all_rows = []
    for ep in ("EP1", "EP2", "EP3"):
        all_rows.append(_assign_episode(service, "P1", ep))

    # 并行交错执行：每个 episode 按阶段推进
    for i in range(len(STAGES)):
        for ep_rows in all_rows:
            _run_episode_ok(service, ep_rows[i], reviewer=f"rv-{ep_rows[i]['episode_id']}")

    stats = service.stats()
    assert stats["assignments"] == 27
    assert stats["audit_coverage"] == 1.0
    assert stats["illegal_transitions"] == 0
    assert stats["infinite_rework"] == 0
    by_status = stats["by_status"]
    assert by_status.get("done", 0) == 27
    flow = service.flow("P1")
    assert len(flow["episodes"]) == 3
    assert all(e["assignments"] == 9 and e["waiting_human"] == 0 for e in flow["episodes"])


# ---------------------------------------------------------------- C2-2
def test_c2_cross_episode_dependency_chain(service):
    _create_team(service)
    ep1 = _assign_episode(service, "P1", "EP1")
    # EP2 的 script 依赖 EP1 的 storyboard 完成
    ep1_story = ep1[2]
    _run_episode_ok(service, ep1[0], reviewer="r1")
    _run_episode_ok(service, ep1[1], reviewer="r1")
    _run_episode_ok(service, ep1_story, reviewer="r1")

    ep2_script = service.assign(
        project_id="P1", episode_id="EP2", stage="script", role="Writer",
        assignee_id="EP2-Writer", task_id="TASK-EP2-1",
        dependencies=[ep1_story["id"]], actor="admin", reason="EP2 剧本依赖 EP1 分镜",
    )
    # 依赖指向的 assignment 必须存在且已完成（可追溯）
    dep = service.get_assignment(ep1_story["id"])["assignment"]
    assert dep["status"] == "done"
    assert ep2_script["dependencies"] == [ep1_story["id"]]
    artifacts = service.artifacts(project_id="P1", episode_id="EP1")
    assert artifacts["traceable"] is True


# ---------------------------------------------------------------- C2-3
def test_c2_concurrent_transitions_thread_safe(service):
    _create_team(service)
    rows = []
    for ep in ("EP1", "EP2", "EP3"):
        rows.extend(_assign_episode(service, "P1", ep))

    errors: list[Exception] = []
    lock = threading.Lock()

    def work(row: dict) -> None:
        try:
            service.start(row["id"], actor="agent", reason="并行开工")
            service.review(
                assignment_id=row["id"], reviewer_role=STAGE_REVIEW_OWNER[row["stage"]],
                reviewer_id="r", verdict="approve", evidence={"ok": True},
                actor="r", reason="并行通过",
                approval_id="AP-FINAL" if row["stage"] == "final" else "",
            )
            service.complete(
                row["id"], actor="r", reason="完成",
                approval_id="AP-FINAL" if row["stage"] == "final" else "",
            )
        except Exception as exc:  # noqa: BLE001
            with lock:
                errors.append(exc)

    threads = [threading.Thread(target=work, args=(row,)) for row in rows]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert errors == [], errors[:3]
    stats = service.stats()
    assert stats["assignments"] == 27
    assert stats["by_status"].get("done", 0) == 27
    assert stats["audit_coverage"] == 1.0
    assert stats["illegal_transitions"] == 0
    # 审计记录 = 每任务至少 3 条（started/review_approved/completed）+ 分派
    assert stats["audit_records"] >= 27 * 4


# ---------------------------------------------------------------- C2-4
def test_c2_recovery_after_restart(service, tmp_path):
    _create_team(service)
    ep1 = _assign_episode(service, "P1", "EP1")
    _run_episode_ok(service, ep1[0], reviewer="r1")
    _run_episode_ok(service, ep1[1], reviewer="r1")
    service.start(ep1[2]["id"], actor="agent", reason="分镜开工")
    # 模拟 Worker Crash：中途重启（重新实例化同一 storage）
    root = str(tmp_path / "team")
    service2 = TeamService(root)
    recovered = service2.get_assignment(ep1[2]["id"])["assignment"]
    assert recovered["status"] == "in_progress"
    assert recovered["started_at"]
    assert service2.stats()["assignments"] == 9
    assert service2.stats()["audit_coverage"] == 1.0
    # 恢复后继续完成
    _run_episode_ok(service2, recovered, reviewer="r1")
    for a in ep1[3:]:
        _run_episode_ok(service2, a, reviewer="r1")
    stats = service2.stats()
    assert stats["by_status"].get("done", 0) == 9
    assert stats["illegal_transitions"] == 0


# ---------------------------------------------------------------- C2-5
def test_c2_interleaved_directed_rework(service):
    _create_team(service)
    ep1 = _assign_episode(service, "P1", "EP1")
    ep3 = _assign_episode(service, "P1", "EP3")

    # EP1 前 4 阶段正常完成，generation QC 失败（motion）
    for a in ep1[:4]:
        _run_episode_ok(service, a, reviewer="r1")
    _run_episode_with_rework(service, ep1[4], issue_category="motion")

    # EP3 前 7 阶段正常完成，sound 失败（audio_sync）
    for a in ep3[:7]:
        _run_episode_ok(service, a, reviewer="r3")
    _run_episode_with_rework(service, ep3[7], issue_category="audio_sync")

    # 收尾两集
    for a in ep1[5:]:
        _run_episode_ok(service, a, reviewer="r1")
    for a in ep3[8:]:
        _run_episode_ok(service, a, reviewer="r3")

    stats = service.stats()
    assert stats["assignments"] == 18
    assert stats["by_status"].get("done", 0) == 18
    assert stats["audit_coverage"] == 1.0
    assert stats["illegal_transitions"] == 0
    assert stats["infinite_rework"] == 0

    flow = service.flow("P1")
    by_ep = {e["episode_id"]: e for e in flow["episodes"]}
    assert by_ep["EP1"]["rework_count"] == 1
    assert by_ep["EP3"]["rework_count"] == 1
    # 定向路由：motion → storyboard/Director；audio_sync → sound/Sound
    ep1_gen = service.get_assignment(ep1[4]["id"])["assignment"]
    ep3_sound = service.get_assignment(ep3[7]["id"])["assignment"]
    assert ep1_gen["stage"] == "storyboard" and ep1_gen["role"] == "Director"
    assert ep3_sound["stage"] == "sound" and ep3_sound["role"] == "Sound"
