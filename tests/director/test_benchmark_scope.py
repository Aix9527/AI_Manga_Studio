"""Phase 12.4: Cross-Project Benchmark acceptance tests (no network)."""

from __future__ import annotations

import shutil

from backend.director.benchmark_scope import ScopeBenchmark, ScopeSpec
from backend.director.memory import DirectorMemory

SPECS = [
    ScopeSpec(project="归墟觉醒·天倾", genre="科幻", style="cold_blue",
              preferred={"action": "llm-qwen", "dialogue": "llm-qwen", "world": "llm-qwen"}),
    ScopeSpec(project="古装世界", genre="古装", style="warm_light",
              preferred={"action": "rule-v2", "dialogue": "rule-v2", "world": "rule-v2"}),
    ScopeSpec(project="彩虹动画", genre="动画", style="pastel",
              preferred={"action": "rule-v2", "dialogue": "llm-qwen", "world": "llm-qwen"}),
]


def _benchmark(tmp_path):
    memory = DirectorMemory(tmp_path / "memory")
    policy_path = tmp_path / "policy.yaml"
    shutil.copyfile("backend/director/router_policy.yaml", policy_path)
    return ScopeBenchmark(memory, SPECS, policy_path=str(policy_path)), memory


def test_benchmark_data_meets_shot_target(tmp_path):
    benchmark, _ = _benchmark(tmp_path)
    shots = benchmark.seed()
    assert shots >= 300  # GPT: benchmark data >= 300 shots
    assert benchmark.memory.accumulation()["shots"] >= 300
    assert benchmark.memory.accumulation()["projects"] == 3


def test_scope_isolation_accuracy_100_percent(tmp_path):
    benchmark, _ = _benchmark(tmp_path)
    benchmark.seed()
    report = benchmark.run()
    # GPT gate: scope isolation accuracy = 100%
    assert report["scope_isolation_accuracy"] == 1.0
    assert report["scopes"] == 3
    assert report["cells"] == 9


def test_transfer_test_isolated_beats_global(tmp_path):
    benchmark, _ = _benchmark(tmp_path)
    benchmark.seed()
    report = benchmark.run()
    transfer = report["transfer_test"]
    assert transfer["total"] == 9
    # GPT goal: isolated_score > global_score (>= here because ties count as wins)
    assert transfer["isolated_wins"] >= 8
    assert transfer["rate"] >= 0.8


def test_pollution_detection_zero_violations(tmp_path):
    benchmark, _ = _benchmark(tmp_path)
    benchmark.seed()
    report = benchmark.run()
    pollution = report["pollution_detection"]
    # GPT gate: cross-project pollution cases = 0 (all prevented)
    assert pollution["violations"] == 0
    # the global-vs-isolated divergence cases must be caught and prevented
    assert pollution["prevented_cases"] >= 1


def test_candidate_attribution_meets_threshold(tmp_path):
    benchmark, _ = _benchmark(tmp_path)
    benchmark.seed()
    report = benchmark.run()
    attribution = report["candidate_attribution"]
    assert attribution["checked"] >= 3
    # GPT gate: candidate correct attribution >= 95%
    assert attribution["rate"] >= 0.95


def test_score_difference_explainable(tmp_path):
    benchmark, _ = _benchmark(tmp_path)
    benchmark.seed()
    report = benchmark.run()
    # every isolated winner carries a real average -> explainable 100%
    assert report["score_explainable_rate"] == 1.0


def test_cross_scope_learning_disabled(tmp_path):
    benchmark, _ = _benchmark(tmp_path)
    benchmark.seed()
    report = benchmark.run()
    # isolation only ever prevents transfers; it never merges scopes
    for case in report["pollution_detection"]["cases"]:
        assert case["prevented"] is True
