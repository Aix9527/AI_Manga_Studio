"""Phase 15.1: 归墟第二部 Production Pilot tests（剧本解析 / 编排 / 事件 / 报告）. """

from __future__ import annotations

import pytest

from backend.production_pilot.pilot import PilotRunner


@pytest.fixture()
def pilot(tmp_path):
    return PilotRunner(root=str(tmp_path))


def test_plan_100_episodes(pilot):
    plan = pilot.plan()
    assert plan["project_id"] == "guixu2"
    assert plan["total_episodes"] == 100
    assert len(plan["chapters"]) == 6
    assert plan["episodes"][0]["id"] == "EP001"
    assert plan["episodes"][-1]["id"] == "EP100"
    assert "归墟第二部" in plan["title"]


def test_run_limited_episodes(pilot):
    plan = pilot.plan()
    result = pilot.run_episodes(limit=2)
    assert result["episodes_planned"] == 2
    assert result["assignments_total"] == 18          # 2 × 9
    assert result["assignments_done"] == 18
    assert result["audit_coverage"] == 1.0
    assert result["illegal_transitions"] == 0
    stats = pilot.team.stats()
    assert stats["new_queue_count"] == 0


def test_seed_events(pilot):
    pilot.run_episodes(limit=1)
    result = pilot.seed_events(limit=1)
    assert result["project_id"] == "guixu2"
    assert result["events_recorded"] == 10            # 5 镜 × (start + end)
    stats = pilot.pi.stats()
    assert stats["warehouse"]["events"] == 10
    assert stats["warehouse"]["shot_metrics"] == 5
    assert stats["warehouse"]["episode_metrics"] == 1


def test_report_validation_targets(pilot):
    pilot.run_episodes(limit=2)
    pilot.seed_events(limit=2)
    pilot.kg.ingest()
    report = pilot.report()
    assert report["total_episodes"] == 100
    assert report["orchestration"]["done"] == 18
    assert report["validation_targets"]["audit_coverage"] == "PASS"
    assert report["validation_targets"]["analytics_roi"] == "PASS"
    assert report["digital_twin"]["prediction"]
    assert report["knowledge_graph"]["nodes"] >= 1
