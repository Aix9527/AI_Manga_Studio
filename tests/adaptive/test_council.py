"""Phase 12.8: Multi-Agent Director Council tests (hermetic, no network)."""

from __future__ import annotations

from collections import Counter

import pytest

from backend.director.arena_runner import RealArenaRunner
from backend.director.council import CouncilAgent, DirectorCouncil
from backend.director.council.base import CouncilDecision, CouncilVote


# ------------------------------------------------------------ agents
def test_council_has_five_agents_with_gpt_weights():
    council = DirectorCouncil()
    assert len(council.agents) == 5
    weights = {a.name: a.weight for a in council.agents}
    assert weights["narrative"] == 0.25
    assert weights["camera"] == 0.20
    assert weights["continuity"] == 0.20
    assert weights["production"] == 0.15
    assert weights["critic"] == 0.20
    assert abs(sum(weights.values()) - 1.0) < 1e-6


def test_each_agent_is_a_council_agent():
    council = DirectorCouncil()
    for agent in council.agents:
        assert isinstance(agent, CouncilAgent)
        assert agent.name
        assert agent.weight > 0


def test_weights_must_sum_to_one():
    from backend.director.council.cinematography_agent import CinematographyDirector
    class _Bad(CouncilAgent):
        name = "bad"
        weight = 0.5
        def score(self, row):  # noqa: ANN001
            return 0.0
    with pytest.raises(ValueError):
        DirectorCouncil(agents=[_Bad(), CinematographyDirector()])


# ------------------------------------------------------------ voting
def test_council_runs_over_200_shots_with_5_candidates():
    runner = RealArenaRunner(limit=220)
    report = runner.run()
    council = DirectorCouncil()
    summary = council.run(report)
    assert summary.coverage["shots"] >= 200
    # at least 5 candidate directors appear across decisions
    candidate_dirs = set()
    for decision in summary.decisions:
        candidate_dirs.update(decision.candidates)
    assert len(candidate_dirs) >= 5


def test_decisions_are_100_percent_explainable():
    runner = RealArenaRunner(limit=100)
    report = runner.run()
    council = DirectorCouncil()
    summary = council.run(report)
    assert summary.explainable == len(summary.decisions)
    for decision in summary.decisions:
        assert decision.reasons  # at least one reason per decision


def test_each_vote_carries_agent_candidate_confidence_reason():
    runner = RealArenaRunner(limit=10)
    report = runner.run()
    council = DirectorCouncil()
    summary = council.run(report)
    for decision in summary.decisions:
        for vote in decision.votes:
            assert vote.agent in ("narrative", "camera", "continuity", "production", "critic")
            assert vote.candidate
            assert 0.0 <= vote.confidence <= 1.0
            assert vote.reason


def test_winner_is_weighted_aggregate_not_single_vote():
    # 310 shots span 科幻(150)+古装(150)+动画(10) => multiple scopes
    runner = RealArenaRunner(limit=310)
    report = runner.run()
    council = DirectorCouncil()
    summary = council.run(report)
    # multiple directors win across scopes (council != single-champion)
    assert len(summary.winners) >= 2


def test_scope_coverage_across_genres():
    runner = RealArenaRunner()  # 500 shots, 4 scopes
    report = runner.run()
    council = DirectorCouncil()
    summary = council.run(report)
    assert summary.coverage["scopes"] >= 3
    assert summary.coverage["genres"]


# ------------------------------------------------------------ decision score
def test_council_decision_score_separate_from_arena():
    runner = RealArenaRunner(limit=20)
    report = runner.run()
    council = DirectorCouncil()
    summary = council.run(report)
    decision = summary.decisions[0]
    cds = council.council_decision_score(decision, decision.scope_key)
    assert "score" in cds
    assert "boost" in cds
    assert cds["genre"] == decision.scope_key


# ------------------------------------------------------------ failure fallback
def test_failure_fallback_100_percent():
    from backend.director.arena import SimulatedDirectorProvider
    from backend.director.providers.base import DirectorProvider, ProviderError
    from backend.director.providers.registry import DirectorProviderRegistry

    class _FailLLM(DirectorProvider):
        def __init__(self, name: str):
            self.name = name
        @property
        def is_available(self):
            return True
        def generate_directive(self, shot, section_context=None):
            raise ProviderError(f"{self.name} unavailable")

    registry = DirectorProviderRegistry({})
    registry.register("rule-v2", SimulatedDirectorProvider("rule-v2", {}))
    for name in ("llm-gpt", "llm-claude", "llm-qwen", "llm-deepseek"):
        registry.register(name, _FailLLM(name))
    runner = RealArenaRunner(
        limit=20,
        registry=registry,
        providers_override={name: registry.get(name) for name in registry.names()},
    )
    report = runner.run()
    for row in report["rows"]:
        if row["director"] != "rule-v2":
            assert row["fallback_count"] == 1
            assert row["valid"] is True  # recovered via rule fallback


# ------------------------------------------------------------ approval chain
def test_council_candidates_go_through_manual_approval():
    runner = RealArenaRunner(limit=200)
    report = runner.run()
    council = DirectorCouncil()
    summary = council.run(report)
    candidates = council.to_candidates(summary, report)
    assert candidates
    for candidate in candidates:
        assert candidate.scope_key
        assert candidate.to_director
        assert candidate.confidence > 0.5
        assert candidate.reason.startswith("council")


def test_council_never_auto_deploys_policy(tmp_path):
    """Council decisions must not touch the router policy without approval."""
    import shutil

    from backend.director.policy_router import DEFAULT_POLICY_PATH

    before = open(DEFAULT_POLICY_PATH, encoding="utf-8").read()
    runner = RealArenaRunner(limit=30)
    report = runner.run()
    council = DirectorCouncil()
    summary = council.run(report)
    council.to_candidates(summary, report)
    after = open(DEFAULT_POLICY_PATH, encoding="utf-8").read()
    assert before == after  # no auto policy deployment
