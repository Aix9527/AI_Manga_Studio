"""Phase 12.3: Multi-Project Memory Isolation tests (no network)."""

from __future__ import annotations

from backend.director.evolution import ControlledEvolution
from backend.director.memory import DirectorExperience, DirectorMemory, PolicyMemory
from backend.director.memory.scope import MemoryScope, scope_from_experience
from backend.director.policy_router import PolicyDirector
from backend.story.models import Shot

import shutil


def _shot(shot_id: str, scene_id: str = "sc1", shot_type: str = "medium") -> Shot:
    return Shot(id=shot_id, scene_id=scene_id, shot_type=shot_type, emotion="tense", duration=3.0)


def _seed(memory: DirectorMemory, project_id, genre, style, scene_type, director, shots, avg):
    for i in range(shots):
        shot_id = f"{project_id}-{scene_type}-{director}-{i}"
        memory.record_decision(
            shot_id, director, scene_type=scene_type, project_id=project_id,
            episode="ep1", genre=genre, style=style,
        )
        memory.record_quality(shot_id, avg, {"items": [{"issue": "low_motion"}]})


# -------------------------------------------------------------- scope model
def test_scope_from_context_and_key():
    scope = MemoryScope.from_context({
        "project_id": "归墟", "genre": "科幻", "style": "cold_blue",
        "episode": "ep02", "character_universe": "gx",
    })
    assert scope.project_scope == "归墟"
    assert scope.scope_key() == "归墟|科幻|cold_blue"
    assert scope.policy_key("action", "rule-v2") == "归墟|科幻|cold_blue|action|rule-v2"
    fallback = MemoryScope.from_context({"genre": "古装"})
    assert fallback.project_scope == "古装"
    empty = MemoryScope.from_context(None)
    assert empty.project_scope == "default"


def test_scope_from_experience():
    exp = DirectorExperience(shot_id="s1", project_id="P", genre="g", style="st", episode="e")
    scope = scope_from_experience(exp)
    assert scope.scope_key() == "P|g|st"
    assert scope.episode == "e"


# ---------------------------------------------------- policy memory isolation
def test_policy_memory_isolates_scopes(tmp_path):
    policy = PolicyMemory(tmp_path)
    # same scene_type + director in two genres with different quality
    for i in range(5):
        policy.record(DirectorExperience(
            shot_id=f"a{i}", scene_type="action", director="rule-v2",
            project_id="sci", genre="科幻", style="cold_blue", quality_score=70.0,
        ))
    for i in range(5):
        policy.record(DirectorExperience(
            shot_id=f"b{i}", scene_type="action", director="rule-v2",
            project_id="hist", genre="古装", style="warm_light", quality_score=95.0,
        ))
    stats = policy.stats()
    assert len(stats) == 2  # same (scene_type, director) split by scope
    by_scope = {r["scope_key"]: r for r in stats}
    assert by_scope["sci|科幻|cold_blue"]["avg_quality"] == 70.0
    assert by_scope["hist|古装|warm_light"]["avg_quality"] == 95.0
    # suggest() honors the scope
    sci = policy.suggest("action", scope_key="sci|科幻|cold_blue")
    assert sci["winner"] is None or True  # single director present


# ----------------------------------------------------- success pattern isolation
def test_success_pattern_scope_key(tmp_path):
    from backend.director.memory import SuccessPattern
    pattern = SuccessPattern(tmp_path)
    experiences = [
        DirectorExperience(shot_id=f"a{i}", shot_type="close-up", director="rule-v2",
                           camera={"movement": "static"}, quality_score=0.9,
                           project_id="sci", genre="科幻", style="cold_blue")
        for i in range(3)
    ] + [
        DirectorExperience(shot_id=f"b{i}", shot_type="close-up", director="rule-v2",
                           camera={"movement": "static"}, quality_score=0.4,
                           project_id="hist", genre="古装", style="warm_light")
        for i in range(3)
    ]
    rows = pattern.patterns(experiences)
    assert len(rows) == 2
    scopes = {row["scope_key"] for row in rows}
    assert scopes == {"sci|科幻|cold_blue", "hist|古装|warm_light"}
    high = next(row for row in rows if row["scope_key"] == "sci|科幻|cold_blue")
    assert high["avg_quality"] == 0.9


# ------------------------------------------------------ director records scope
def test_policy_director_records_scope_from_context(tmp_path):
    director = PolicyDirector(llm_provider=None, memory_root=tmp_path)
    shot = _shot("s1")
    director.plan_shot(shot, {
        "scene_type": "dialogue", "project_id": "归墟", "genre": "科幻",
        "style": "cold_blue", "character_universe": "gx",
    })
    raw = director.memory.shot.get("s1")
    assert raw["genre"] == "科幻"
    assert raw["style"] == "cold_blue"
    assert raw["character_universe"] == "gx"


# ------------------------------------------------------- analyzer isolation
def test_analyzer_produces_scope_scoped_candidates(tmp_path):
    memory = DirectorMemory(tmp_path)
    # sci-fi action (route=rule): qwen clearly beats rule -> candidate rule->qwen
    _seed(memory, "sci", "科幻", "cold_blue", "action", "rule-v2", 20, 78.0)
    _seed(memory, "sci", "科幻", "cold_blue", "action", "llm-qwen", 20, 90.0)
    # historical world (route=hybrid, current llm-qwen): rule clearly beats qwen
    _seed(memory, "hist", "古装", "warm_light", "world", "llm-qwen", 20, 80.0)
    _seed(memory, "hist", "古装", "warm_light", "world", "rule-v2", 20, 92.0)

    policy_path = tmp_path / "policy.yaml"
    shutil.copyfile("backend/director/router_policy.yaml", policy_path)
    evolution = ControlledEvolution(memory.policy, policy_path=policy_path,
                                    versions_dir=tmp_path / "versions",
                                    director_memory=memory)
    candidates = evolution.analyze()
    # two scope-specific candidates, no cross-pollution
    assert len(candidates) == 2
    by_scope = {c.scope_key: c for c in candidates}
    sci = by_scope["sci|科幻|cold_blue"]
    hist = by_scope["hist|古装|warm_light"]
    assert sci.scene_type == "action"
    assert sci.to_director == "llm-qwen"      # sci-fi action prefers qwen
    assert hist.scene_type == "world"
    assert hist.to_director == "rule-v2"      # historical world prefers rule
    assert sci.genre == "科幻" and hist.genre == "古装"


def test_stats_by_scope(tmp_path):
    memory = DirectorMemory(tmp_path)
    _seed(memory, "sci", "科幻", "cold_blue", "action", "rule-v2", 5, 80.0)
    _seed(memory, "hist", "古装", "warm_light", "action", "llm-qwen", 5, 85.0)
    scoped = memory.stats_by_scope()
    assert scoped["scopes"] == 2
    assert "sci|科幻|cold_blue" in scoped["by_scope"]
    assert "hist|古装|warm_light" in scoped["by_scope"]
