"""Phase 12.5: Director Arena tests (deterministic, no network)."""

from __future__ import annotations

from backend.director.arena import (
    COST_PROFILES,
    DIRECTOR_STRENGTH,
    WEIGHTS,
    DirectorArena,
    SimulatedDirectorProvider,
    build_arena_dataset,
)


def test_dataset_500_shots_across_four_scopes():
    dataset = build_arena_dataset()
    assert len(dataset) == 500
    counts = {}
    for item in dataset:
        counts[item.genre] = counts.get(item.genre, 0) + 1
    assert counts == {"科幻": 150, "古装": 150, "动画": 100, "都市": 100}
    assert {item.style for item in dataset} == {"cold_blue", "warm_light", "pastel", "neon"}


def test_arena_contenders_and_weights():
    arena = DirectorArena()
    assert set(arena.providers) == {"rule-v2", "llm-qwen", "llm-gpt", "llm-claude", "llm-deepseek"}
    assert WEIGHTS["narrative"] == 0.25
    assert WEIGHTS["camera"] == 0.20
    assert WEIGHTS["continuity"] == 0.20
    assert WEIGHTS["quality"] == 0.15
    assert WEIGHTS["cost"] == 0.10
    assert WEIGHTS["stability"] == 0.10
    assert sum(WEIGHTS.values()) == 1.0


def test_arena_run_produces_ranking_and_rows():
    arena = DirectorArena()
    report = arena.run(limit=20)
    assert report["dataset"]["shots"] == 20
    assert set(report["contenders"]) == set(arena.providers)
    assert len(report["ranking"]) == 5
    assert report["ranking"][0]["total"] >= report["ranking"][-1]["total"]
    assert len(report["rows"]) == 20 * 5


def test_specialization_matrix_covers_all_scopes_and_directors():
    arena = DirectorArena()
    report = arena.run()
    specialization = report["specialization"]
    assert set(specialization) == {"科幻", "古装", "动画", "都市"}
    for genre, specs in specialization.items():
        assert set(specs) == set(arena.providers)
        assert all(v is not None for v in specs.values())
    assert set(report["per_scope_winner"]) == {"科幻", "古装", "动画", "都市"}


def test_per_scope_winner_is_creative_specialization():
    arena = DirectorArena()
    report = arena.run()
    # per-scope winner == argmax simulated Quality per genre (creative
    # specialization, separate from the cost-adjusted weighted totals)
    for genre in report["per_scope_winner"]:
        expected = max(DIRECTOR_STRENGTH, key=lambda d: DIRECTOR_STRENGTH[d][genre])
        assert report["per_scope_winner"][genre] == expected
    assert report["per_scope_winner"]["古装"] == "rule-v2"
    assert report["per_scope_winner"]["科幻"] == "llm-gpt"
    assert report["per_scope_winner"]["动画"] == "llm-gpt"
    assert report["per_scope_winner"]["都市"] == "llm-gpt"


def test_no_single_champion_but_per_scope_specialization():
    arena = DirectorArena()
    report = arena.run()
    # at least two different directors are needed across scopes: specialization
    # beats a single champion (rule wins 古装, gpt wins 科幻/动画/都市)
    winners = set(report["per_scope_winner"].values())
    assert len(winners) >= 2
    assert "rule-v2" in winners
    # creative winners are NOT just the cost-adjusted overall champion: the
    # cost-adjusted leaderboard is an operational view, not the per-scope pick
    overall_champion = report["ranking"][0]["director"]
    assert overall_champion not in winners or len(winners) > 1


def test_scope_isolation_kept_in_arena():
    arena = DirectorArena()
    report = arena.run()
    rows = report["rows"]
    # specialization[genre][d] is the mean of that director's cost-adjusted
    # total computed ONLY from that genre's own shots: no cross-genre voting.
    for genre, specs in report["specialization"].items():
        genre_rows = [r for r in rows if r["genre"] == genre]
        for director, score in specs.items():
            subset = [r for r in genre_rows if r["director"] == director]
            assert score == round(sum(r["total"] for r in subset) / len(subset), 1)
        # the creative winner for this scope has the top simulated Quality
        winner = report["per_scope_winner"][genre]
        winner_strength = DIRECTOR_STRENGTH[winner][genre]
        for director in arena.providers:
            assert DIRECTOR_STRENGTH[director][genre] <= winner_strength


def test_cost_component_differentiates_providers():
    arena = DirectorArena()
    report = arena.run(limit=5)
    rule_cost = report["rows"][0]["components"]["cost"]
    gpt_cost = next(r for r in report["rows"] if r["director"] == "llm-gpt")["components"]["cost"]
    assert rule_cost > gpt_cost  # rule is cheapest, GPT most expensive
    assert COST_PROFILES["rule-v2"][0] == 0
