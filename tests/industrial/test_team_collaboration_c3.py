"""Phase 13.5-C: C3 分级验收 tests（20 集模拟验证，GPT Priority 1）.

规模化验证（不新增功能）：吞吐 / 依赖图 / 返工与升级 / 审计量 / 重启恢复。
- C3-1 20 集并行吞吐：20 × 9 = 180 assignments 全部 done
- C3-2 规模化定向返工与升级（含返工耗尽 → escalated → 人工 retry/abandon）
- C3-3 跨集依赖图校验（EPi 依赖 EPi-1 资产，引用合法）
- C3-4 审计量压测（每事件一条审计，覆盖率 100%）
- C3-5 大规模重启恢复（执行一半后重新实例化，状态一致并继续完成）
"""

from __future__ import annotations

import time

import pytest

from backend.team.model import REWORK_TARGET_ROLE, REWORK_TARGET_STAGE, STAGE_REVIEW_OWNER
from backend.team.service import TeamService

EPISODES = 20
STAGES = [
    ("planning", "Producer"), ("script", "Writer"), ("storyboard", "Director"),
    ("assets", "Director"), ("generation", "Production"), ("qc", "Reviewer"),
    ("editing", "Editor"), ("sound", "Sound"), ("final", "Producer"),
]


@pytest.fixture()
def service(tmp_path):
    return TeamService(str(tmp_path / "team"))


def _setup(service: TeamService, episodes: int = EPISODES) -> list[list[dict]]:
    service.create_team(project_id="P1", name="C3 20 集团队", actor="admin", reason="C3 初始化")
    all_rows = []
    for ep_no in range(1, episodes + 1):
        ep = f"EP{ep_no:02d}"
        rows = []
        for i, (stage, role) in enumerate(STAGES):
            deps = []
            if i > 0:
                deps.append(rows[i - 1]["id"])           # 集内依赖
            if stage == "script" and ep_no > 1:
                prev_assets = all_rows[ep_no - 2][3]["id"]  # 跨集依赖上一集 assets
                deps.append(prev_assets)
            a = service.assign(
                project_id="P1", episode_id=ep, stage=stage, role=role,
                assignee_type="agent", assignee_id=f"{ep}-{role}",
                task_id=f"TASK-{ep}-{i}", dependencies=deps,
                actor="admin", reason=f"分派{stage}",
            )
            rows.append(a)
        all_rows.append(rows)
    return all_rows


def _review_ok(service: TeamService, row: dict, reviewer: str) -> None:
    cur = service.get_assignment(row["id"])["assignment"]
    if cur["status"] == "assigned":
        service.start(row["id"], actor=row["assignee_id"], reason="开工")
    service.review(
        assignment_id=row["id"],
        reviewer_role=STAGE_REVIEW_OWNER[row["stage"]],
        reviewer_id=reviewer, verdict="approve", evidence={"ok": True},
        actor=reviewer, reason="评审通过",
        approval_id="AP-FINAL" if row["stage"] == "final" else "",
    )
    service.complete(
        row["id"], actor=reviewer, reason="完成",
        approval_id="AP-FINAL" if row["stage"] == "final" else "",
    )


# ---------------------------------------------------------------- C3-1
def test_c3_20_episodes_throughput(service):
    all_rows = _setup(service)
    started = time.time()
    for stage_idx in range(len(STAGES)):
        for rows in all_rows:
            _review_ok(service, rows[stage_idx], reviewer=f"rv-{rows[stage_idx]['episode_id']}")
    elapsed = time.time() - started

    stats = service.stats()
    assert stats["assignments"] == EPISODES * 9 == 180
    assert stats["by_status"].get("done", 0) == 180
    assert stats["audit_coverage"] == 1.0
    assert stats["illegal_transitions"] == 0
    assert stats["infinite_rework"] == 0
    flow = service.flow("P1")
    assert len(flow["episodes"]) == EPISODES
    assert all(e["assignments"] == 9 for e in flow["episodes"])
    print(f"C3-1 20 集吞吐: 180 assignments 完成, {elapsed:.2f}s")


# ---------------------------------------------------------------- C3-2
def test_c3_scaled_rework_and_escalation(service):
    all_rows = _setup(service, episodes=10)
    # 前半段（前 4 阶段）正常完成，generation 保留用于返工测试
    for stage_idx in range(4):
        for rows in all_rows:
            _review_ok(service, rows[stage_idx], reviewer="r")

    # 6 个 generation 任务定向返工（motion / lighting / character_identity）
    rework_rows = [all_rows[i][4] for i in (1, 3, 5, 7, 8, 9)]
    categories = ["motion", "lighting", "character_identity", "motion", "lighting", "pacing"]
    for row, cat in zip(rework_rows, categories):
        service.start(row["id"], actor="worker", reason="开工")
        service.review(
            assignment_id=row["id"], reviewer_role="Reviewer", reviewer_id="qc1",
            verdict="reject", evidence={"qc_failed": True, "issue": cat},
            actor="qc1", reason="QC 失败",
        )
        routed = service.rework(assignment_id=row["id"], issue_category=cat,
                                actor="orchestrator", reason="定向返工")
        assert routed["stage"] == REWORK_TARGET_STAGE[cat]
        assert routed["role"] == REWORK_TARGET_ROLE[cat]

    # 1 个任务返工耗尽 → escalated（max_attempts=1）→ 人工 retry
    ep99 = service.assign(
        project_id="P1", episode_id="EP99", stage="generation", role="Production",
        assignee_id="EP99-Production", task_id="TASK-EP99-4", max_attempts=1,
        actor="admin", reason="升级测试",
    )
    service.start(ep99["id"], actor="worker", reason="开工")
    service.review(
        assignment_id=ep99["id"], reviewer_role="Reviewer", reviewer_id="qc1",
        verdict="reject", evidence={"qc_failed": True, "issue": "motion"},
        actor="qc1", reason="QC 失败",
    )
    escalated = service.rework(assignment_id=ep99["id"], issue_category="motion",
                               actor="orchestrator", reason="返工耗尽")
    assert escalated["status"] == "escalated"
    recovered = service.escalate(assignment_id=ep99["id"], decision="retry", approval_id="AP-C3",
                                 actor="admin", reason="人工批准重试")
    assert recovered["status"] == "assigned"
    assert recovered["attempt"] == 1

    stats = service.stats()
    assert stats["illegal_transitions"] == 0
    assert stats["infinite_rework"] == 0
    flow = service.flow("P1")
    reworked = [e for e in flow["episodes"] if e["episode_id"] in ("EP02", "EP04", "EP06", "EP08", "EP09", "EP10")]
    assert all(e["rework_count"] == 1 for e in reworked)


# ---------------------------------------------------------------- C3-3
def test_c3_dependency_graph_validation(service):
    all_rows = _setup(service)
    for rows in all_rows:
        for i, row in enumerate(rows):
            for dep in row["dependencies"]:
                dep_row = service.get_assignment(dep)["assignment"]
                # 集内依赖必须存在于同一集且阶段更早；跨集依赖指向上一集 assets
                assert dep_row["episode_id"] in (row["episode_id"], f"EP{int(row['episode_id'][2:]) - 1:02d}")
    # EP02 script 依赖 EP01 assets
    ep02_script = all_rows[1][1]
    assert ep02_script["dependencies"][-1] == all_rows[0][3]["id"]
    artifacts = service.artifacts(project_id="P1", episode_id="EP02")
    assert artifacts["traceable"] is True


# ---------------------------------------------------------------- C3-4
def test_c3_audit_scale(service):
    all_rows = _setup(service)
    for stage_idx in range(len(STAGES)):
        for rows in all_rows:
            _review_ok(service, rows[stage_idx], reviewer="r")

    stats = service.stats()
    # 每条迁移/事件一条审计：assign(1) + start(1) + review 提交(1) + approved(1) + completed(1) = 5 条/任务；另含 1 条 team_created
    assert stats["audit_records"] == 180 * 5 + 1
    assert stats["audit_coverage"] == 1.0
    audits = service.audit("P1")["audit"]
    assert len(audits) == 180 * 5 + 1
    assert len({a["id"] for a in audits}) == len(audits)  # append-only，无覆盖


# ---------------------------------------------------------------- C3-5
def test_c3_restart_at_scale(service, tmp_path):
    all_rows = _setup(service)
    for stage_idx in range(5):
        for rows in all_rows:
            _review_ok(service, rows[stage_idx], reviewer="r")

    root = str(tmp_path / "team")
    service2 = TeamService(root)
    stats2 = service2.stats()
    assert stats2["assignments"] == 180
    assert stats2["by_status"].get("done", 0) == 100  # 前 5 阶段 × 20 集
    assert stats2["audit_coverage"] == 1.0
    # 恢复后继续完成剩余 4 阶段
    for stage_idx in range(5, len(STAGES)):
        for rows in all_rows:
            _review_ok(service2, rows[stage_idx], reviewer="r")
    final = service2.stats()
    assert final["by_status"].get("done", 0) == 180
    assert final["illegal_transitions"] == 0
    assert final["infinite_rework"] == 0
