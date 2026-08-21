"""Phase 11.3: Controlled Director Evolution tests (no network)."""

from __future__ import annotations

import shutil

import pytest

from backend.director.evolution import ControlledEvolution
from backend.director.evolution.policy_candidate import PolicyCandidate
from backend.director.evolution.policy_diff import policy_diff, policy_diff_text
from backend.director.evolution.rollback import PolicyVersionStore
from backend.director.memory import DirectorExperience, PolicyMemory
from backend.director.policy_router import DEFAULT_POLICY_PATH

# route -> current director per the default router_policy.yaml
CURRENT = {
    "action": "rule-v2",
    "chase": "rule-v2",
    "world": "llm-qwen",
    "environment": "rule-v2",
    "exploration": "llm-qwen",
    "dialogue": "llm-qwen",
    "emotion": "llm-qwen",
    "transition": "llm-qwen",
    "revelation": "llm-qwen",
    "establishment": "llm-qwen",
}


def _seed(memory: PolicyMemory, scene_type: str, director: str, shots: int, avg: float) -> None:
    for i in range(shots):
        memory.record(DirectorExperience(
            shot_id=f"{scene_type}-{director}-{i}",
            scene_type=scene_type, director=director, quality_score=avg,
        ))


def _seed_6_opportunities(memory: PolicyMemory) -> None:
    """6 scene types where the alternative director clearly beats the current one."""
    # action: rule-v2 current 80, llm-qwen 90
    _seed(memory, "action", "rule-v2", 20, 80.0)
    _seed(memory, "action", "llm-qwen", 20, 90.0)
    # environment: rule-v2 78, llm-qwen 85
    _seed(memory, "environment", "rule-v2", 20, 78.0)
    _seed(memory, "environment", "llm-qwen", 20, 85.0)
    # dialogue: llm-qwen 82, rule-v2 92
    _seed(memory, "dialogue", "llm-qwen", 20, 82.0)
    _seed(memory, "dialogue", "rule-v2", 20, 92.0)
    # emotion: llm-qwen 80, rule-v2 88
    _seed(memory, "emotion", "llm-qwen", 20, 80.0)
    _seed(memory, "emotion", "rule-v2", 20, 88.0)
    # world (hybrid): llm-qwen 81, rule-v2 89
    _seed(memory, "world", "llm-qwen", 20, 81.0)
    _seed(memory, "world", "rule-v2", 20, 89.0)
    # exploration (hybrid): llm-qwen 79, rule-v2 87
    _seed(memory, "exploration", "llm-qwen", 20, 79.0)
    _seed(memory, "exploration", "rule-v2", 20, 87.0)


def _make_evolution(tmp_path) -> tuple[ControlledEvolution, PolicyMemory]:
    policy_path = tmp_path / "policy.yaml"
    shutil.copyfile(DEFAULT_POLICY_PATH, policy_path)
    versions_dir = tmp_path / "versions"
    memory = PolicyMemory(tmp_path)
    evolution = ControlledEvolution(
        memory, policy_path=policy_path, versions_dir=versions_dir
    )
    return evolution, memory


# ------------------------------------------------------------- analyzer
def test_analyzer_discovers_six_candidates_with_evidence(tmp_path):
    evolution, memory = _make_evolution(tmp_path)
    _seed_6_opportunities(memory)
    candidates = evolution.analyze()
    # GPT gate: >= 5 auto-discovered optimization opportunities
    assert len(candidates) >= 5
    for candidate in candidates:
        # every proposal carries samples, confidence and score delta
        assert candidate.samples_from >= 20
        assert candidate.samples_to >= 20
        assert 0.0 < candidate.confidence <= 0.99
        assert candidate.score_delta >= 3.0
    assert candidates[0].scene_type == "action"  # largest delta first
    assert candidates[0].to_director == "llm-qwen"


def test_propose_respects_thresholds(tmp_path):
    evolution, memory = _make_evolution(tmp_path)
    # action: valid (20 samples, delta 10)
    _seed(memory, "action", "rule-v2", 20, 80.0)
    _seed(memory, "action", "llm-qwen", 20, 90.0)
    # dialogue: alternative has too few samples (10 < 20)
    _seed(memory, "dialogue", "llm-qwen", 20, 82.0)
    _seed(memory, "dialogue", "rule-v2", 10, 92.0)
    # emotion: delta below threshold (1.0 < 3.0)
    _seed(memory, "emotion", "llm-qwen", 20, 87.0)
    _seed(memory, "emotion", "rule-v2", 20, 88.0)
    proposal = evolution.propose()
    assert proposal["mode"] == "manual_approval"
    assert len(proposal["candidates"]) == 1
    assert proposal["candidates"][0].scene_type == "action"


# -------------------------------------------------------------- diff
def test_policy_diff_reports_route_changes():
    before = {"version": 1.0, "routes": {"action": "rule", "dialogue": "qwen"}}
    after = {"version": 1.1, "routes": {"action": "hybrid", "dialogue": "qwen"}}
    diffs = policy_diff(before, after)
    assert diffs == [{"scene_type": "action", "route_before": "rule", "route_after": "hybrid"}]
    assert "action: rule -> hybrid" in policy_diff_text(before, after)


# ------------------------------------------------------------ approval
def test_approve_writes_versioned_policy_and_trace(tmp_path):
    evolution, memory = _make_evolution(tmp_path)
    _seed_6_opportunities(memory)
    candidate = evolution.analyze()[0]  # action -> llm-qwen
    before_routes = evolution._policy_dict()["routes"]["action"]

    result = evolution.approve(candidate)
    # active policy updated
    assert evolution._policy_dict()["routes"]["action"] == "qwen"
    assert before_routes == "rule"
    # versioned snapshot exists
    snapshot_path = tmp_path / "versions" / "router_policy_v1.yaml"
    assert snapshot_path.exists()
    # trace: before/after/affected shots/score delta/confidence
    entry = result["log"]
    assert entry["action"] == "approve"
    assert entry["candidate"]["scene_type"] == "action"
    assert entry["diff"][0]["route_before"] == "rule"
    assert entry["diff"][0]["route_after"] == "qwen"
    assert entry["affected_shots"] >= 40
    assert entry["score_delta"] == 10.0
    assert entry["confidence"] > 0.8
    assert entry["approved_by"] == "human"
    # router sees the new route
    assert evolution.router.route_for("action") == "qwen"


def test_version_increments_on_each_approval(tmp_path):
    evolution, memory = _make_evolution(tmp_path)
    _seed_6_opportunities(memory)
    candidates = evolution.analyze()
    evolution.approve(candidates[0])
    evolution.approve(candidates[1])
    assert evolution.versions.latest_version() == 2
    assert (tmp_path / "versions" / "router_policy_v2.yaml").exists()


def test_approve_rejects_invalid_candidate(tmp_path):
    evolution, memory = _make_evolution(tmp_path)
    candidate = PolicyCandidate(
        scene_type="action", from_director="rule-v2", to_director="llm-qwen",
        samples_from=5, samples_to=5, avg_from=80.0, avg_to=90.0,
        score_delta=10.0, confidence=0.99,
    )
    with pytest.raises(ValueError):
        evolution.approve(candidate)


def test_approve_blocked_outside_manual_mode(tmp_path):
    evolution, memory = _make_evolution(tmp_path)
    evolution.mode = "auto"  # simulate a config that disabled manual approval
    _seed(memory, "action", "rule-v2", 20, 80.0)
    _seed(memory, "action", "llm-qwen", 20, 90.0)
    candidate = evolution.analyze()[0]
    with pytest.raises(RuntimeError):
        evolution.approve(candidate)


def test_reject_records_trace_without_changing_policy(tmp_path):
    evolution, memory = _make_evolution(tmp_path)
    _seed_6_opportunities(memory)
    candidate = evolution.analyze()[0]
    before_routes = dict(evolution._policy_dict()["routes"])
    entry = evolution.reject(candidate, reason="risk of style drift")
    assert entry["action"] == "reject"
    assert entry["reason"] == "risk of style drift"
    assert evolution._policy_dict()["routes"] == before_routes
    assert evolution.versions.latest_version() == 0  # no snapshot written


# ------------------------------------------------------------- rollback
def test_rollback_restores_previous_policy(tmp_path):
    evolution, memory = _make_evolution(tmp_path)
    _seed_6_opportunities(memory)
    candidates = evolution.analyze()
    original_routes = dict(evolution._policy_dict()["routes"])

    evolution.approve(candidates[0])  # deploy action -> qwen
    bad_routes = dict(evolution._policy_dict()["routes"])
    assert bad_routes["action"] == "qwen"

    result = evolution.rollback(reason="bad_policy_deployed")
    # routes restored
    assert evolution._policy_dict()["routes"] == original_routes
    # traceable rollback record with before/after + affected shots
    entry = result["log"]
    assert entry["action"] == "rollback"
    assert entry["reason"] == "bad_policy_deployed"
    assert entry["diff"][0]["route_before"] == "qwen"
    assert entry["diff"][0]["route_after"] == "rule"
    assert entry["affected_shots"] >= 40
    # version stays monotonic after revert
    assert float(evolution._policy_dict()["version"]) > float(bad_routes and 1.0 or 0.0)
    assert evolution.router.route_for("action") == "rule"


def test_rollback_without_snapshot_raises(tmp_path):
    evolution, _ = _make_evolution(tmp_path)
    with pytest.raises(RuntimeError):
        evolution.rollback()


def test_evolution_config_read_from_yaml(tmp_path):
    evolution, _ = _make_evolution(tmp_path)
    assert evolution.mode == "manual_approval"
    assert evolution.min_samples == 20
    assert evolution.confidence_threshold == 0.85
    assert evolution.versions.rollback_window == 200


def test_version_store_prunes_beyond_window(tmp_path):
    store = PolicyVersionStore(tmp_path / "policy.yaml", versions_dir=tmp_path / "versions",
                               rollback_window=3)
    from backend.director.evolution.rollback import _save_yaml
    for i in range(1, 7):
        _save_yaml(tmp_path / "versions" / f"router_policy_v{i}.yaml", {"version": i})
    store._prune()
    remaining = sorted(
        p.name for p in (tmp_path / "versions").iterdir() if p.name.startswith("router_policy_v")
    )
    assert remaining == ["router_policy_v4.yaml", "router_policy_v5.yaml", "router_policy_v6.yaml"]
