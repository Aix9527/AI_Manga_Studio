"""Phase 12.7-B: Real Director Arena Runner tests (hermetic, no network)."""

from __future__ import annotations

from pathlib import Path

from backend.director.arena import SimulatedDirectorProvider
from backend.director.arena_runner import RealArenaRunner
from backend.director.providers.base import DirectorProvider, ProviderError
from backend.director.providers.registry import DirectorProviderRegistry


class _FakeLLM(DirectorProvider):
    """Deterministic stand-in that can simulate failures."""

    def __init__(self, name: str, fail: bool = False):
        self.name = name
        self.fail = fail

    @property
    def is_available(self) -> bool:
        return True

    def generate_directive(self, shot, section_context=None):
        if self.fail:
            raise ProviderError(f"{self.name} unavailable")
        return SimulatedDirectorProvider(self.name, {}).generate_directive(
            shot, section_context
        )


def _runner_with_fakes(limit: int = 30, fail: set[str] | None = None):
    fail = fail or set()
    registry = DirectorProviderRegistry({})
    registry.register("rule-v2", SimulatedDirectorProvider("rule-v2", {}))
    for name in ("llm-gpt", "llm-claude", "llm-qwen", "llm-deepseek"):
        registry.register(name, _FakeLLM(name, fail=name in fail))
    return RealArenaRunner(
        limit=limit,
        registry=registry,
        providers_override={
            name: registry.get(name)
            for name in registry.names()
        },
    )


# ------------------------------------------------------------ providers
def test_registry_manages_four_llms_plus_rule():
    registry = DirectorProviderRegistry()
    names = registry.names()
    assert "llm-gpt" in names
    assert "llm-claude" in names
    assert "llm-qwen" in names
    assert "llm-deepseek" in names
    assert "rule-v2" in names
    assert len(names) == 5
    # registry.get() returns a provider instance per name
    for name in names:
        assert registry.get(name) is not None


def test_registry_register_unregister_roundtrip():
    registry = DirectorProviderRegistry({})
    fake = _FakeLLM("llm-gpt")
    registry.register("llm-gpt", fake)
    assert registry.get("llm-gpt") is fake
    registry.unregister("llm-gpt")
    assert "llm-gpt" not in registry.names()


# ------------------------------------------------------------ runner
def test_runner_covers_200_plus_shots_and_three_scopes():
    # 310 shots spans 科幻(150) + 古装(150) + 动画(10) => 3 scopes
    runner = RealArenaRunner(limit=310)
    report = runner.run()
    assert report["dataset"]["shots"] == 310
    assert len(report["rows"]) >= 200
    assert report["coverage"]["scopes"] >= 3


def test_runner_records_cost_for_every_row():
    runner = RealArenaRunner(limit=40)
    report = runner.run()
    assert report["cost"]["shots"] == 40
    for row in report["rows"]:
        assert "tokens" in row["cost"]
        assert "latency_ms" in row["cost"]
        assert "api_cost" in row["cost"]
        assert "fallback_count" in row["cost"]


def test_provider_failure_recovers_100_percent():
    runner = _runner_with_fakes(limit=20, fail={"llm-gpt"})
    report = runner.run()
    # every failed llm-gpt call recovered via rule-v2 fallback
    gpt_rows = [r for r in report["rows"] if r["director"] == "llm-gpt"]
    assert gpt_rows
    for row in gpt_rows:
        assert row["fallback_count"] == 1
        assert row["valid"] is True  # recovered directive scored
        assert "unavailable" in row["error"]


def test_all_llms_down_still_recovers_to_rule():
    runner = _runner_with_fakes(
        limit=10, fail={"llm-gpt", "llm-claude", "llm-qwen", "llm-deepseek"}
    )
    report = runner.run()
    for row in report["rows"]:
        if row["director"] != "rule-v2":
            assert row["fallback_count"] == 1


# ------------------------------------------------------------ candidates
def test_arena_generates_router_candidates():
    runner = RealArenaRunner()
    report = runner.run()
    candidates = runner.to_candidates(report)
    # GPT gate: router candidate generation (>=1 per scope with evidence)
    assert candidates
    for candidate in candidates:
        assert candidate.scope_key
        assert candidate.score_delta >= 3.0
        assert candidate.avg_to >= candidate.avg_from
        assert candidate.samples_from >= 1


def test_arena_candidates_carry_scope_isolation():
    runner = RealArenaRunner()
    report = runner.run()
    candidates = runner.to_candidates(report)
    for candidate in candidates:
        assert candidate.genre == candidate.scope_key
        assert candidate.project_scope == candidate.scope_key


# ------------------------------------------------------------ review loop
def test_propose_goes_through_manual_approval(tmp_path):
    from backend.director.evolution import ControlledEvolution
    from backend.director.evolution.rollback import PolicyVersionStore
    from backend.director.memory import PolicyMemory
    from backend.director.policy_router import DEFAULT_POLICY_PATH

    import shutil

    policy_path = tmp_path / "policy.yaml"
    shutil.copyfile(DEFAULT_POLICY_PATH, policy_path)
    memory = PolicyMemory(tmp_path)
    evolution = ControlledEvolution(
        memory, policy_path=policy_path, versions_dir=tmp_path / "versions"
    )
    runner = RealArenaRunner(limit=40)
    proposal = runner.propose(evolution)
    assert proposal["approval_mode"] == "manual_approval"
    assert proposal["shots"] == 40
    # human approval chain: candidates are pending until approved
    if proposal["candidates"]:
        candidate = proposal["candidates"][0]
        assert candidate["scene_type"]
        assert candidate["to_director"]
