"""Phase 12.7-A: Adaptive Dispatcher tests (deterministic, no network)."""

from __future__ import annotations

import pytest

from backend.orchestration.adaptive_dispatcher import (
    EMERGENCY_DIRECTOR,
    AdaptiveDispatcher,
    DispatchDecision,
    DispatchRequest,
)


@pytest.fixture()
def dispatcher():
    return AdaptiveDispatcher()


# ------------------------------------------------------------ dispatch
def test_dispatch_returns_primary_fallback_chain(dispatcher):
    decision = dispatcher.dispatch(DispatchRequest(
        project="归墟觉醒·天倾", genre="科幻", scene_type="world",
        shot_type="wide", style="cold_blue", shot_id="s001",
    ))
    assert decision.shot_id == "s001"
    assert decision.genre == "科幻"
    assert decision.primary_director == "llm-gpt"  # creative winner
    assert decision.fallback == "rule-v2"          # PVS winner behind
    assert decision.provider_chain[0] == "llm-gpt"
    assert EMERGENCY_DIRECTOR in decision.provider_chain
    assert decision.scope_key == "科幻"
    assert decision.source == "recommendation"


def test_dispatch_historical_uses_rule_primary(dispatcher):
    decision = dispatcher.dispatch(DispatchRequest(genre="古装", scene_type="action"))
    assert decision.primary_director == "rule-v2"
    assert decision.scope_key == "古装"


def test_dispatch_approved_cell_wins_over_recommendation(tmp_path, dispatcher):
    # approve 科幻|action -> 古装-style rule? approve writes to policy; use a
    # fresh router pinned to tmp_path so the approval is isolated.
    from backend.director.adaptive_router import AdaptiveDirectorRouter
    router = AdaptiveDirectorRouter(
        policy_path=tmp_path / "adaptive_router_policy.yaml",
        versions_dir=tmp_path / "versions",
    )
    router.approve("科幻|action|primary", approved_by="test")
    d = AdaptiveDispatcher(router=router)
    decision = d.dispatch(DispatchRequest(genre="科幻", scene_type="action"))
    assert decision.source == "approved"
    assert decision.primary_director == "llm-gpt"


# ------------------------------------------------------------ A/B
def test_ab_validation_100_shots_passes_gpt_gate(dispatcher):
    ab = dispatcher.ab_validation(limit=100)
    assert ab["shots"] == 100
    assert ab["quality_gain_pct"] >= 5.0
    assert ab["fallback_rate"] < 10.0
    assert ab["passed"] is True


def test_ab_validation_requires_100_shots(dispatcher):
    with pytest.raises(ValueError):
        dispatcher.ab_validation(limit=50)


# ------------------------------------------------------------ failure
def test_failure_test_degrades_to_fallback(dispatcher):
    result = dispatcher.failure_test(unavailable="llm-gpt", genre="科幻", scene_type="action")
    assert result["degraded"] is True
    assert result["resolved"] == result["expected"]
    assert result["chain_ends_at_emergency"] is True
    assert result["resolved"] != "llm-gpt"


def test_failure_all_llms_down_ends_at_emergency(dispatcher):
    decision = dispatcher.dispatch(DispatchRequest(genre="科幻", scene_type="action"))
    unavailable = {"llm-gpt", "llm-qwen", "llm-claude", "llm-deepseek"}
    resolved = dispatcher.resolve(decision, unavailable)
    assert resolved == EMERGENCY_DIRECTOR


def test_resolve_returns_primary_when_available(dispatcher):
    decision = dispatcher.dispatch(DispatchRequest(genre="科幻", scene_type="action"))
    assert dispatcher.resolve(decision, set()) == decision.primary_director


# ------------------------------------------------------------ scope
def test_scope_isolation_sci_fi_vs_historical(dispatcher):
    report = dispatcher.scope_isolation_report()
    assert report["scope_key_isolated"] is True
    # creative winners per scope differ: Sci-Fi=llm-gpt, Historical=rule-v2
    assert report["sci_fi_primary"]["action"] == "llm-gpt"
    assert report["historical_primary"]["action"] == "rule-v2"
    assert report["shared_primary_cells"] == []


def test_decision_dict_roundtrip(dispatcher):
    decision = dispatcher.dispatch(DispatchRequest(genre="都市", scene_type="emotion"))
    data = decision.to_dict()
    assert data["primary_director"] == decision.primary_director
    assert data["provider_chain"] == decision.provider_chain
