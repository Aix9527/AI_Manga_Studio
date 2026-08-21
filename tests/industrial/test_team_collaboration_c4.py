"""Phase 13.5-C: C4 分级验收 tests（100 集 dry-run，GPT 批准执行）.

纯规模验证（不新增功能、0 GPU）：900 Assignment 吞吐 / 100 集依赖图（含
故意环检出）/ 规模化返工+升级+阻塞+失败 / 4 次重启恢复 / 审计压力 /
持久化增长 / 人工治理门禁未被绕过。
"""

from __future__ import annotations

import json
import pathlib
import statistics
import time

from backend.team.model import REWORK_TARGET_ROLE, REWORK_TARGET_STAGE, STAGE_REVIEW_OWNER
from backend.team.service import TeamService

EPISODES = 100
STAGES = [
    ("planning", "Producer"), ("script", "Writer"), ("storyboard", "Director"),
    ("assets", "Director"), ("generation", "Production"), ("qc", "Reviewer"),
    ("editing", "Editor"), ("sound", "Sound"), ("final", "Producer"),
]
REWORK_CATEGORIES = ["character_identity", "prompt_adherence", "motion", "lighting",
                     "continuity", "audio_sync", "pacing", "budget"]
RESTART_POINTS = {225, 450, 675, 850}


def _setup(root: str) -> tuple[TeamService, list[list[dict]]]:
    """100 集 × 9 阶段 = 900 assignments；相邻集依赖 + 共享资产 + 扇出/汇聚。"""
    service = TeamService(root)
    service.create_team(project_id="P1", name="C4 百集团队", actor="admin", reason="C4 初始化")
    all_rows: list[list[dict]] = []
    for ep_no in range(1, EPISODES + 1):
        ep = f"EP{ep_no:03d}"
        rows: list[dict] = []
        for i, (stage, role) in enumerate(STAGES):
            deps: list[str] = []
            if i > 0:
                deps.append(rows[i - 1]["id"])                       # 集内阶段依赖
            if stage == "script" and ep_no > 1:
                deps.append(all_rows[ep_no - 2][3]["id"])             # 相邻集依赖（99 条）
            if stage == "assets" and ep_no > 1:
                deps.append(all_rows[0][0]["id"])                     # 多集共享资产（扇入 99）
            max_attempts = 1 if (stage == "generation" and ep_no % 10 == 0) else None
            a = service.assign(
                project_id="P1", episode_id=ep, stage=stage, role=role,
                assignee_type="agent", assignee_id=f"{ep}-{role}",
                task_id=f"TASK-{ep}-{i}", dependencies=deps,
                max_attempts=max_attempts, actor="admin", reason=f"分派{stage}",
            )
            rows.append(a)
        all_rows.append(rows)
    return service, all_rows


def _t(fn, *args, **kwargs) -> float:
    start = time.perf_counter()
    fn(*args, **kwargs)
    return time.perf_counter() - start


def _advance(service: TeamService, row: dict, *, inject: dict | None = None) -> list[float]:
    """推进一个任务到终态；inject 可选 block / fail / issue（定向返工或升级）。"""
    lat: list[float] = []
    inject = inject or {}
    stage = row["stage"]
    lat.append(_t(service.start, row["id"], actor=row["assignee_id"], reason="开工"))

    if inject.get("block"):
        lat.append(_t(service.block, row["id"], actor="admin", reason="依赖缺失"))
        lat.append(_t(service.unblock, row["id"], actor="admin", reason="依赖就绪"))
        lat.append(_t(service.start, row["id"], actor=row["assignee_id"], reason="恢复开工"))

    if inject.get("fail"):
        lat.append(_t(service.review, assignment_id=row["id"],
                      reviewer_role=STAGE_REVIEW_OWNER[stage], reviewer_id="qc1",
                      verdict="escalate", evidence={"unrecoverable": True},
                      actor="qc1", reason="不可恢复"))
        lat.append(_t(service.escalate, assignment_id=row["id"], decision="abandon",
                      approval_id="AP-FAIL", actor="admin", reason="人工判定不可恢复"))
        return lat

    issue = inject.get("issue")
    if issue:  # 可恢复定向返工 或 返工耗尽升级
        lat.append(_t(service.review, assignment_id=row["id"],
                      reviewer_role=STAGE_REVIEW_OWNER[stage], reviewer_id="qc1",
                      verdict="reject", evidence={"qc_failed": True, "issue": issue},
                      actor="qc1", reason="QC 失败"))
        lat.append(_t(service.rework, assignment_id=row["id"], issue_category=issue,
                      actor="orchestrator", reason="定向返工"))
        cur = service.get_assignment(row["id"])["assignment"]
        if cur["status"] == "escalated":      # 返工耗尽 → 人工 retry
            lat.append(_t(service.escalate, assignment_id=row["id"], decision="retry",
                          approval_id="AP-C4", actor="admin", reason="人工批准重试"))
        lat.append(_t(service.start, row["id"], actor=row["assignee_id"], reason="返工后开工"))

    cur = service.get_assignment(row["id"])["assignment"]
    reviewer_role = STAGE_REVIEW_OWNER[cur["stage"]]       # 返工后按当前阶段 Owner 评审
    lat.append(_t(service.review, assignment_id=row["id"],
                  reviewer_role=reviewer_role, reviewer_id="rv",
                  verdict="approve", evidence={"ok": True}, actor="rv", reason="评审通过",
                  approval_id="AP-FINAL" if cur["stage"] == "final" else ""))
    lat.append(_t(service.complete, assignment_id=row["id"], actor="rv", reason="完成",
                  approval_id="AP-FINAL" if cur["stage"] == "final" else ""))
    return lat


def _inject_cycles(service: TeamService, all_rows: list[list[dict]]) -> None:
    """故意注入 3 个依赖环（模拟外部错误数据），供环检出验证。"""
    for i in (5, 25, 55):
        a = all_rows[i][2]     # storyboard
        b = all_rows[i][3]     # assets
        service._assignments[a["id"]]["dependencies"] = list(service._assignments[a["id"]].get("dependencies", [])) + [b["id"]]
        service._assignments[b["id"]]["dependencies"] = list(service._assignments[b["id"]].get("dependencies", [])) + [a["id"]]
    service._save_dict("assignments.json", service._assignments)


def _repair_cycles(service: TeamService, all_rows: list[list[dict]]) -> None:
    for i in (5, 25, 55):
        a = all_rows[i][2]
        b = all_rows[i][3]
        service._assignments[a["id"]]["dependencies"] = [d for d in service._assignments[a["id"]]["dependencies"] if d != b["id"]]
        service._assignments[b["id"]]["dependencies"] = [d for d in service._assignments[b["id"]]["dependencies"] if d != a["id"]]
    service._save_dict("assignments.json", service._assignments)


def _percentile(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    values = sorted(values)
    return values[min(len(values) - 1, int(len(values) * p))]


def test_c4_100_episode_dry_run(tmp_path):
    root = str(tmp_path / "team")
    service, all_rows = _setup(root)

    # ---------------------------------------------------------- 依赖图（含故意环检出）
    _inject_cycles(service, all_rows)
    graph = service.dependency_graph("P1")
    assert graph["nodes"] == 900
    assert graph["cycle_count"] == 3, graph["cycles"]
    assert graph["deadlocks"] == 0
    _repair_cycles(service, all_rows)
    graph = service.dependency_graph("P1")
    assert graph["cycle_count"] == 0
    assert graph["dangling_count"] == 0
    assert graph["max_fan_out"] >= 1 and graph["max_fan_in"] >= 99  # 共享资产扇入

    # ---------------------------------------------------------- 执行 + 注入 + 4 次重启
    latencies: list[float] = []
    cold_starts: list[float] = []
    completed = 0
    rework_done = 0
    escalate_done = 0
    block_done = 0
    fail_done = 0
    rework_info: list[tuple[str, str]] = []
    issue_iter = iter(REWORK_CATEGORIES * 30)

    for stage_idx, (stage, role) in enumerate(STAGES):
        for ep_no in range(1, EPISODES + 1):
            row = all_rows[ep_no - 1][stage_idx]
            inject: dict | None = None
            if stage == "sound" and ep_no in (50, 100) and fail_done < 2:
                inject = {"fail": True}
                fail_done += 1
            elif stage == "editing" and ep_no % 20 == 0 and block_done < 5:
                inject = {"block": True}
                block_done += 1
            elif stage == "generation" and ep_no % 10 == 0 and escalate_done < 10:
                inject = {"issue": next(issue_iter)}
                escalate_done += 1
            elif rework_done < 45 and stage_idx in (2, 3, 4) and ep_no % 2 == 0:
                issue = next(issue_iter)
                inject = {"issue": issue}
                rework_info.append((row["id"], issue))
                rework_done += 1
            latencies.extend(_advance(service, row, inject=inject))
            completed += 1
            if completed in RESTART_POINTS:
                t0 = time.perf_counter()
                service = TeamService(root)       # 模拟重启（Worker Crash）
                cold_starts.append(time.perf_counter() - t0)
                assert service.stats()["audit_coverage"] == 1.0
                assert service.stats()["illegal_transitions"] == 0

    # ---------------------------------------------------------- 结果与门槛
    stats = service.stats()
    assert stats["assignments"] == 900
    by_status = stats["by_status"]
    assert by_status.get("done", 0) == 898          # 2 个不可恢复终态 failed
    assert by_status.get("failed", 0) == 2
    assert stats["illegal_transitions"] == 0
    assert stats["infinite_rework"] == 0
    assert stats["audit_coverage"] == 1.0
    assert stats["new_queue_count"] == 0
    assert rework_done == 45 and escalate_done == 10 and block_done == 5 and fail_done == 2

    # 返工定向路由准确率 100%
    for aid, cat in rework_info:
        cur = service.get_assignment(aid)["assignment"]
        assert cur["stage"] == REWORK_TARGET_STAGE[cat], (aid, cat)
        assert cur["role"] == REWORK_TARGET_ROLE[cat], (aid, cat)

    graph_final = service.dependency_graph("P1")
    assert graph_final["cycle_count"] == 0
    assert graph_final["dangling_count"] == 0
    assert graph_final["deadlocks"] == 0

    audits = service.audit("P1")["audit"]
    assert stats["audit_records"] == len(audits)
    assert stats["audit_records"] >= 4501
    assert len({a["id"] for a in audits}) == len(audits)     # 无重复审计 ID
    assert stats["governance"]["auto_deploy"] is False
    assert stats["governance"]["auto_budget_change"] is False

    audits_path = pathlib.Path(root) / "audits.json"
    asg_path = pathlib.Path(root) / "assignments.json"
    size_bytes = audits_path.stat().st_size
    asg_size = asg_path.stat().st_size

    # ---------------------------------------------------------- 统计输出
    p50 = _percentile(latencies, 0.50)
    p95 = _percentile(latencies, 0.95)
    p99 = _percentile(latencies, 0.99)
    total_elapsed = sum(latencies)
    throughput = completed / max(total_elapsed, 1e-9)
    print(f"C4: assignments={completed} elapsed={total_elapsed:.2f}s throughput={throughput:.2f}/s")
    print(f"C4: migration latency P50={p50*1000:.2f}ms P95={p95*1000:.2f}ms P99={p99*1000:.2f}ms")
    print(f"C4: restarts={len(cold_starts)} avg cold_start={statistics.mean(cold_starts)*1000:.1f}ms")
    print(f"C4: audit_records={stats['audit_records']} audits.json={size_bytes/1024:.0f}KB assignments.json={asg_size/1024:.0f}KB")
    print(f"C4: done={by_status.get('done')} failed={by_status.get('failed', 0)} "
          f"rework={rework_done} escalate={escalate_done} block={block_done}")
