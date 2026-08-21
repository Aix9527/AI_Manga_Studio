"""Phase 13.5-B: Production Intelligence tests (B1 warehouse → B4 candidates)."""

from __future__ import annotations

import datetime

import pytest

from backend.production_intelligence.service import ProductionIntelligenceService


@pytest.fixture()
def service(tmp_path):
    return ProductionIntelligenceService(str(tmp_path / "pi"))


def _ts(offset: float) -> str:
    return datetime.datetime.fromtimestamp(datetime.datetime.now().timestamp() + offset).isoformat()


def _seed_episode(service: ProductionIntelligenceService, project: str = "P1", episode: str = "EP1") -> None:
    base = dict(project_id=project, episode_id=episode, audit_id=f"AUD-{episode}")
    service.record_event(event_type="generation_start", shot_id="S1", created_at=_ts(0),
                         payload={"director": "导演A", "prompt_version": "pv1", "shot_dna_id": "dna1"}, **base)
    service.record_event(event_type="generation_end", shot_id="S1", created_at=_ts(10),
                         payload={"quality": 0.85, "identity_score": 0.9, "vision_score": 0.8,
                                  "motion_score": 0.7, "retention": 0.6, "hook_score": 0.5,
                                  "cliffhanger": 0.4, "lead_time_s": 120}, **base)
    service.record_event(event_type="cost_recorded", shot_id="S1", created_at=_ts(11),
                         payload={"cost": 10, "planned_cost": 8, "cost_delta": 2, "reason": "retry"}, **base)
    service.record_event(event_type="approval_passed", shot_id="S1", created_at=_ts(20), payload={}, **base)
    service.record_event(event_type="generation_start", shot_id="S2", created_at=_ts(30),
                         payload={"director": "导演A", "prompt_version": "pv1", "shot_dna_id": "dna2"}, **base)
    service.record_event(event_type="generation_end", shot_id="S2", created_at=_ts(40),
                         payload={"quality": 0.7, "retention": 0.5, "lead_time_s": 90}, **base)
    service.record_event(event_type="qc_failed", shot_id="S2", created_at=_ts(45), payload={}, **base)
    service.record_event(event_type="revision_created", shot_id="S2", created_at=_ts(46), payload={}, **base)
    service.record_event(event_type="cost_recorded", shot_id="S2", created_at=_ts(47),
                         payload={"cost": 12, "planned_cost": 8, "cost_delta": 4, "reason": "qc_failure"}, **base)
    service.record_event(event_type="generation_start", shot_id="S2", created_at=_ts(50), payload={}, **base)
    service.record_event(event_type="generation_end", shot_id="S2", created_at=_ts(60),
                         payload={"quality": 0.75, "retention": 0.55, "lead_time_s": 60}, **base)
    service.record_event(event_type="approval_passed", shot_id="S2", created_at=_ts(70), payload={}, **base)


# ---------------------------------------------------------------- B1
def test_event_record_and_audit_coverage(service):
    _seed_episode(service)
    stats = service.warehouse_stats()
    assert stats["events"] == 12
    assert stats["audit_coverage"] == 1.0
    assert stats["shot_metrics"] == 2
    assert stats["episode_metrics"] == 1
    events = service.list_events(event_type="cost_recorded")
    assert len(events) == 2


def test_invalid_event_type_rejected(service):
    with pytest.raises(ValueError, match="invalid event type"):
        service.record_event(event_type="unknown", project_id="P", episode_id="E", audit_id="a")


def test_shot_and_episode_metric_aggregation(service):
    _seed_episode(service)
    sm = service.wh.shot_metric("S1")
    assert sm.quality == 0.85
    assert sm.identity_score == 0.9
    assert sm.director == "导演A"
    assert sm.prompt_version == "pv1"
    em = service.wh.episode_metric("EP1")
    assert em.cost_planned == 16.0
    assert em.cost_actual == 22.0
    assert em.failure_rate == 0.5
    assert em.avg_qc == pytest.approx(0.787, abs=0.01)


# ---------------------------------------------------------------- B2
def test_cost_intelligence_explanation_rate_gate(service):
    _seed_episode(service)
    cost = service.cost_intelligence("P1")
    assert cost["variance"] == 6.0
    assert cost["explanation_rate"] >= 0.9
    factors = {f["factor"]: f["cost"] for f in cost["factors"]}
    assert factors.get("retry") == 2.0
    assert factors.get("qc_failure") == 4.0


def test_cycle_intelligence_lead_time_segments(service):
    _seed_episode(service)
    cycle = service.cycle_intelligence("P1")
    assert cycle["lead_time_s"] > 0
    segments = cycle["segments"]
    assert segments["generation"] > 0
    assert segments["approval"] > 0
    total = segments["waiting"] + segments["generation"] + segments["review"] + segments["approval"]
    assert total == pytest.approx(cycle["lead_time_s"], abs=1)


def test_director_intelligence_and_prompt_roi(service):
    _seed_episode(service)
    directors = service.director_intelligence("P1")
    assert directors[0]["director"] == "导演A"
    assert directors[0]["shots"] == 2
    assert directors[0]["success_rate"] == 0.5
    prompts = service.prompt_roi("P1")
    assert prompts[0]["prompt_version"] == "pv1"
    assert prompts[0]["usage"] == 2
    assert prompts[0]["revision_rate"] == 0.5


# ---------------------------------------------------------------- B3
def test_overview_and_episode_roi(service):
    _seed_episode(service)
    overview = service.overview("P1")
    assert overview["episodes"] == 1
    assert overview["shots"] == 2
    assert overview["total_cost"] == 22.0
    rows = service.episode_roi("P1")
    assert rows[0]["episode_id"] == "EP1"
    assert rows[0]["roi"] > 0


def test_risk_radar_detects_overrun_and_qc(service):
    _seed_episode(service)
    risks = service.risk_radar("P1")
    types = {r["risk_type"] for r in risks}
    assert "cost_overrun" in types
    assert "qc_failure_rate" in types


def test_optimization_candidates_produced(service):
    _seed_episode(service)
    suggestions = service.optimization_candidates("P1")
    assert len(suggestions) >= 2
    assert all("suggested_changes" in s for s in suggestions)


# ---------------------------------------------------------------- B4
def test_candidate_flow_review_and_apply(service):
    _seed_episode(service)
    candidates = service.propose_candidates("P1")
    assert len(candidates) >= 1
    cid = candidates[0]["id"]
    # 未审批直接应用被拒绝（auto_apply=false）
    with pytest.raises(ValueError, match="approved"):
        service.apply_candidate(cid)
    service.review_candidate(cid, "approved", reviewer="制片人")
    applied = service.apply_candidate(cid)
    assert applied["status"] == "applied"
    assert applied["applied_at"]
    # 重复应用被拒绝
    with pytest.raises(ValueError, match="已应用|applied"):
        service.apply_candidate(cid)


def test_candidate_reject_path(service):
    _seed_episode(service)
    candidates = service.propose_candidates("P1")
    cid = candidates[0]["id"]
    service.review_candidate(cid, "rejected", reviewer="导演")
    rows = service.list_candidates(status="rejected")
    assert rows[0]["id"] == cid


def test_candidate_invalid_review_decision(service):
    _seed_episode(service)
    candidates = service.propose_candidates("P1")
    with pytest.raises(ValueError, match="approved 或 rejected"):
        service.review_candidate(candidates[0]["id"], "maybe")


def test_governance_flags_frozen(service):
    stats = service.stats()
    assert stats["governance"]["auto_learning"] is False
    assert stats["governance"]["auto_apply"] is False
    assert stats["governance"]["auto_deploy"] is False
    assert stats["governance"]["human_approval"] is True