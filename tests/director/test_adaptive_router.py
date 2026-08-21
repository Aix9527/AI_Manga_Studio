"""Phase 12.6: Adaptive Director Router tests (deterministic, no network)."""

from __future__ import annotations

from pathlib import Path

import pytest

from backend.director.adaptive_router import (
    PRODUCTION_VALUE_WEIGHTS,
    AdaptiveDirectorRouter,
    latency_score,
    production_value_score,
)


def _make(tmp_path) -> AdaptiveDirectorRouter:
    return AdaptiveDirectorRouter(
        policy_path=tmp_path / "adaptive_router_policy.yaml",
        versions_dir=tmp_path / "versions",
    )


# ------------------------------------------------------------- PVS
def test_production_value_weights_match_gpt_spec():
    assert PRODUCTION_VALUE_WEIGHTS["quality"] == 0.40
    assert PRODUCTION_VALUE_WEIGHTS["continuity"] == 0.20
    assert PRODUCTION_VALUE_WEIGHTS["stability"] == 0.15
    assert PRODUCTION_VALUE_WEIGHTS["cost"] == 0.15
    assert PRODUCTION_VALUE_WEIGHTS["latency"] == 0.10
    assert sum(PRODUCTION_VALUE_WEIGHTS.values()) == 1.0


def test_production_value_score_computes_with_latency():
    score = production_value_score(
        {"quality": 0.9, "continuity": 0.8, "stability": 1.0, "cost": 0.6}, "rule-v2"
    )
    assert 0.0 <= score <= 100.0
    # faster director gets a better latency component
    fast = latency_score("rule-v2")
    slow = latency_score("llm-gpt")
    assert fast > slow


def test_latency_score_bounds():
    assert latency_score("rule-v2") > latency_score("llm-gpt")
    assert all(0.0 <= latency_score(d) <= 1.0 for d in
               ("rule-v2", "llm-qwen", "llm-gpt", "llm-claude", "llm-deepseek"))


# ---------------------------------------------------------- proposal
def test_proposal_meets_30_suggestion_gate():
    router = _make(Path("."))  # path unused for proposal
    proposal = router.proposal()
    # GPT gate: >= 30 scene strategy suggestions
    assert proposal["count"] >= 30
    assert proposal["cells"] == 20  # 4 genres x 5 scene types


def test_primary_is_creative_per_scope_winner():
    router = _make(Path("."))
    primary = {
        r.cell: r.director
        for r in router.compute_recommendations() if r.role == "primary"
    }
    assert primary["科幻|action"] == "llm-gpt"
    assert primary["古装|action"] == "rule-v2"
    assert primary["动画|dialogue"] == "llm-gpt"
    assert primary["都市|world"] == "llm-gpt"


def test_fallback_is_best_production_value_behind_winner():
    router = _make(Path("."))
    recs = router.compute_recommendations()
    for cell in {r.cell for r in recs}:
        primary = next(r for r in recs if r.cell == cell and r.role == "primary")
        fallback = next(r for r in recs if r.cell == cell and r.role == "fallback")
        assert fallback.director != primary.director
        # fallback has the highest PVS among non-winners
        pvs_map = primary.evidence["pvs"]
        others = [d for d, p in pvs_map.items() if d != primary.director]
        assert pvs_map[fallback.director] == max(pvs_map[d] for d in others)


def test_scope_isolation_zero_pollution():
    router = _make(Path("."))
    audit = router.isolation_audit()
    assert audit["violations"] == 0
    assert audit["isolated"] is True
    assert audit["checked"] >= 30


def test_proposal_evidence_carries_pvs_and_memory():
    router = _make(Path("."))
    rec = next(r for r in router.compute_recommendations() if r.role == "primary")
    assert "pvs" in rec.evidence
    assert "memory" in rec.evidence
    assert rec.samples > 0


# ------------------------------------------------------------ approval
def test_approve_persists_primary_and_fallback(tmp_path):
    router = _make(tmp_path)
    result = router.approve("科幻|action|primary", approved_by="test")
    assert result["cell"] == "科幻|action"
    route = router.route_for("科幻", "action")
    assert route["primary"] == "llm-gpt"
    assert route["fallback"] == "rule-v2"  # best PVS behind the winner
    assert router.policy_path.exists()
    # versioned snapshot exists
    snapshots = list((tmp_path / "versions").glob("adaptive_router_policy_v*.yaml"))
    assert len(snapshots) == 1


def test_approve_is_traceable_and_idempotent_guarded(tmp_path):
    router = _make(tmp_path)
    router.approve("科幻|action|primary")
    with pytest.raises(ValueError):
        router.approve("科幻|action|primary")
    entries = router.versions.entries()
    assert entries[-1]["action"] == "approve"
    assert entries[-1]["cell"] == "科幻|action"
    assert entries[-1]["primary"] == "llm-gpt"


def test_reject_records_without_policy_change(tmp_path):
    router = _make(tmp_path)
    router.reject("古装|action|primary", reason="human review")
    entries = router.versions.entries()
    assert entries[-1]["action"] == "reject"
    assert entries[-1]["reason"] == "human review"
    # no snapshot created, no policy file
    assert not list((tmp_path / "versions").glob("adaptive_router_policy_v*.yaml"))


def test_rollback_restores_previous_policy(tmp_path):
    router = _make(tmp_path)
    router.approve("科幻|action|primary")
    first = router.route_for("科幻", "action")
    router.approve("动画|world|primary")
    assert router.route_for("动画", "world")["primary"] == "llm-gpt"
    router.rollback(reason="test")
    # rollback restores the snapshot taken before the second approve
    restored = router.route_for("动画", "world")
    assert restored["primary"] == "rule-v2"
    assert router.route_for("科幻", "action") == first


def test_rollback_without_snapshot_raises(tmp_path):
    router = _make(tmp_path)
    with pytest.raises(RuntimeError):
        router.rollback()


def test_route_for_default_before_approval():
    router = _make(Path("."))
    assert router.route_for("科幻", "action") == {
        "primary": "rule-v2", "fallback": "llm-qwen"
    }


# ------------------------------------------------------------ A/B
def test_ab_validation_uses_100_shots_and_passes_gate():
    router = _make(Path("."))
    ab = router.ab_validation(limit=100)
    assert ab["shots"] == 100
    assert ab["gate"]["quality_gain_min"] == 5.0
    assert ab["gate"]["cost_reduction_min"] == 10.0
    # GPT gate: quality +5% OR cost -10%
    assert ab["quality_gain_pct"] >= 5.0 or ab["cost_reduction_pct"] >= 10.0
    assert ab["passed"] is True


def test_ab_validation_adaptive_primary_matches_creative_winner():
    router = _make(Path("."))
    ab = router.ab_validation(limit=100)
    after = ab["after"]["adaptive_primary"]
    assert after["科幻"]["action"] == "llm-gpt"
    assert after["古装"]["action"] == "rule-v2"
    assert after["动画"]["dialogue"] == "llm-gpt"
    assert after["都市"]["world"] == "llm-gpt"


def test_ab_validation_requires_100_shots():
    router = _make(Path("."))
    with pytest.raises(ValueError):
        router.ab_validation(limit=50)
