"""Phase 14.4: AI Producer Agent tests（规划/资源/解释/报告）. """

from __future__ import annotations

import json

import pytest

from backend.producer_agent.service import ProducerAgentService
from tests.industrial.test_command_center import _seed as _seed_cc


@pytest.fixture()
def service(tmp_path):
    _seed_cc(tmp_path)
    return ProducerAgentService(root=str(tmp_path))


def test_plan_suggests_steps(service):
    plan = service.plan()
    assert plan["auto_approve"] is False
    assert plan["steps"], plan
    actions = [s["action"] for s in plan["steps"]]
    # seed 中有 escalated 任务 → 等待人工 → 处理审批队列
    assert any("人工审批队列" in a for a in actions)
    assert plan["summary"]["waiting_human"] >= 1


def test_resource_suggestion(service):
    result = service.resource_suggestion()
    assert result["auto_schedule"] is False
    assert result["suggestions"] is not None
    assert "仅参考" in result["note"]


def test_explain_risk(service):
    # 先触发风险生成
    service.dt.predict()
    candidates = service.dt.risk_candidates()["candidates"]
    assert candidates
    explained = service.explain_risk(candidates[0]["id"])
    assert explained["candidate"]["id"] == candidates[0]["id"]
    assert explained["explanation"]
    assert explained["auto_fix"] is False
    assert "人工决定" in explained["note"]
    with pytest.raises(KeyError):
        service.explain_risk("NOPE")


def test_report_aggregates(service):
    report = service.report()
    assert report["production_state"]["task_total"] >= 1
    assert report["prediction"]
    assert report["plan"] is not None
    assert report["resource_suggestions"] is not None
    assert report["governance"]["auto_control"] is False
    assert "不自动批准/调度" in report["note"]
