"""Phase 11.1: Director Memory tests (no network)."""

from __future__ import annotations

from backend.director.memory import (
    DirectorExperience,
    DirectorMemory,
    FailureMemory,
    PolicyMemory,
    ShotMemory,
    SuccessPattern,
)
from backend.director.policy_router import PolicyDirector
from backend.director.providers.base import ProviderError, build_directive
from backend.story.models import Shot


def _shot(shot_id: str, shot_type: str = "medium", emotion: str = "tense") -> Shot:
    return Shot(id=shot_id, scene_id="sc1", shot_type=shot_type, emotion=emotion, duration=3.0)


def test_shot_memory_roundtrip(tmp_path):
    store = ShotMemory(tmp_path)
    exp = DirectorExperience(shot_id="s1", scene_type="action", director="rule-v2",
                             camera={"movement": "tracking"})
    store.record(exp)
    assert store.get("s1")["director"] == "rule-v2"
    store.record_quality("s1", 0.9, {"identity": 1.0})
    raw = store.get("s1")
    assert raw["quality_score"] == 0.9
    assert raw["feedback"]["identity"] == 1.0
    exps = store.experiences()
    assert len(exps) == 1
    assert exps[0].shot_id == "s1"
    assert exps[0].camera["movement"] == "tracking"


def test_shot_memory_quality_for_unknown_shot_is_noop(tmp_path):
    store = ShotMemory(tmp_path)
    store.record_quality("missing", 0.9)
    assert store.experiences() == []


def test_failure_memory_counts_by_type(tmp_path):
    store = FailureMemory(tmp_path)
    store.record("s1", "llm-qwen", "validator_reject", "physics")
    store.record("s1", "llm-qwen", "validator_reject", "camera")
    store.record("s2", "llm-qwen", "provider_error")
    assert store.count_by_type() == {"validator_reject": 2, "provider_error": 1}


def test_policy_memory_aggregates_and_suggests_winner(tmp_path):
    policy = PolicyMemory(tmp_path)
    for i in range(6):
        policy.record(DirectorExperience(shot_id=f"a{i}", scene_type="action",
                                         director="rule-v2", quality_score=0.5))
    for i in range(6):
        policy.record(DirectorExperience(shot_id=f"b{i}", scene_type="action",
                                         director="llm-qwen", quality_score=0.9))
    stats = {r["director"]: r for r in policy.stats()}
    assert stats["rule-v2"]["shots"] == 6
    assert stats["rule-v2"]["avg_quality"] == 0.5
    assert stats["llm-qwen"]["avg_quality"] == 0.9
    suggestion = policy.suggest("action")
    assert suggestion["winner"] == "llm-qwen"
    assert suggestion["reason"] == "avg_quality comparison"


def test_policy_memory_suggest_insufficient_samples(tmp_path):
    policy = PolicyMemory(tmp_path)
    policy.record(DirectorExperience(shot_id="a1", scene_type="action",
                                     director="rule-v2", quality_score=0.9))
    policy.record(DirectorExperience(shot_id="b1", scene_type="action",
                                     director="llm-qwen", quality_score=0.8))
    suggestion = policy.suggest("action")
    assert suggestion["winner"] is None
    assert suggestion["reason"] == "insufficient_samples"


def test_policy_memory_idempotent_decision_then_quality(tmp_path):
    policy = PolicyMemory(tmp_path)
    exp = DirectorExperience(shot_id="s1", scene_type="action", director="llm-qwen")
    policy.record(exp)
    policy.record(DirectorExperience(shot_id="s1", scene_type="action",
                                     director="llm-qwen", quality_score=0.8))
    rows = policy.stats()
    assert len(rows) == 1
    assert rows[0]["shots"] == 1
    assert rows[0]["avg_quality"] == 0.8


def test_success_pattern_aggregation_sorted_by_quality(tmp_path):
    pattern = SuccessPattern(tmp_path)
    exps = [
        DirectorExperience(shot_id=f"a{i}", shot_type="close-up", director="llm-qwen",
                           camera={"movement": "static"}, quality_score=0.9)
        for i in range(3)
    ] + [
        DirectorExperience(shot_id=f"b{i}", shot_type="close-up", director="rule-v2",
                           camera={"movement": "static"}, quality_score=0.4)
        for i in range(3)
    ]
    rows = pattern.patterns(exps)
    assert len(rows) == 2
    assert rows[0]["director"] == "llm-qwen"
    assert rows[0]["avg_quality"] == 0.9


def test_director_memory_facade_end_to_end(tmp_path):
    memory = DirectorMemory(tmp_path)
    memory.record_decision("s1", "llm-qwen", scene_type="dialogue", shot_type="medium",
                           intent="dialogue_beat", camera={"movement": "static"})
    memory.record_quality("s1", 0.8, {"identity": 1.0})
    memory.record_failure("s2", "llm-qwen", "validator_reject", "physics")
    stats = memory.stats()
    assert stats["shots"] == 1
    assert stats["failures"]["validator_reject"] == 1
    assert stats["policy"][0]["avg_quality"] == 0.8
    assert stats["policy"][0]["shots"] == 1


class _FakeLLM:
    """Deterministic LLM provider for PolicyDirector memory tests."""

    name = "llm-qwen"
    is_available = True

    def __init__(self, fail: bool = False, invalid: bool = False):
        self.fail = fail
        self.invalid = invalid

    def generate_directive(self, shot, section_context=None):
        if self.fail:
            raise ProviderError("network down")
        data = {
            "shot_id": shot.id,
            "shot_intent": "emotional_beat",
            "camera": {"angle": "low-angle", "movement": "tracking", "distance": "close-up"},
            "lighting": {"style": "chiaroscuro", "key": "rim", "temperature": "cool"},
            "emotion_curve": [
                {"t": 0.0, "emotion": "calm", "intensity": 0.2},
                {"t": shot.duration / 2, "emotion": "tense", "intensity": 0.8},
                {"t": shot.duration, "emotion": "dark", "intensity": 0.9},
            ],
            "continuity": {"previous_shot": "", "constraints": ["carry_character_state:suwan"]},
            "rationale": "fake llm",
        }
        return build_directive(shot, data, director_version=self.name)


def test_policy_director_records_llm_decision(tmp_path):
    director = PolicyDirector(llm_provider=_FakeLLM(), memory_root=tmp_path)
    shot = _shot("gx001")
    directive = director.plan_shot(shot, {"scene_type": "dialogue"})
    assert directive.director_version == "llm-qwen"
    stats = director.memory.stats()
    assert stats["shots"] == 1
    raw = director.memory.shot.get("gx001")
    assert raw["scene_type"] == "dialogue"
    assert raw["director"] == "llm-qwen"
    assert raw["camera"]["movement"] == "tracking"


def test_policy_director_records_rule_route(tmp_path):
    director = PolicyDirector(llm_provider=_FakeLLM(), memory_root=tmp_path)
    shot = _shot("gx002", shot_type="long")
    directive = director.plan_shot(shot, {"scene_type": "action"})
    assert directive.director_version == "rule-v2"
    raw = director.memory.shot.get("gx002")
    assert raw["director"] == "rule-v2"


def test_policy_director_records_llm_fallback_failure(tmp_path):
    director = PolicyDirector(llm_provider=_FakeLLM(fail=True), memory_root=tmp_path)
    shot = _shot("gx003")
    directive = director.plan_shot(shot, {"scene_type": "dialogue"})
    assert directive.director_version == "rule-v2"  # fallback
    stats = director.memory.stats()
    assert stats["shots"] == 1
    assert stats["failures"]["llm_fallback"] == 1
    raw = director.memory.shot.get("gx003")
    assert raw["director"] == "rule-v2"


def test_policy_director_quality_feedback_flow(tmp_path):
    director = PolicyDirector(llm_provider=_FakeLLM(), memory_root=tmp_path)
    shot = _shot("gx004")
    director.plan_shot(shot, {"scene_type": "dialogue"})
    director.record_quality("gx004", 0.92, {"identity": 1.0, "motion_cv": 0.8})
    stats = director.memory.stats()
    assert stats["policy"][0]["avg_quality"] == 0.9
    raw = director.memory.shot.get("gx004")
    assert raw["quality_score"] == 0.92
    assert raw["feedback"]["identity"] == 1.0


def test_policy_director_without_memory_is_unchanged():
    director = PolicyDirector(llm_provider=_FakeLLM())
    assert director.memory is None
    directive = director.plan_shot(_shot("gx005"), {"scene_type": "dialogue"})
    assert directive.director_version == "llm-qwen"
    director.record_quality("gx005", 0.9)  # no-op, must not raise


# ------------------------------------------------- Phase 12.1 production data
def test_record_decision_with_production_metadata(tmp_path):
    memory = DirectorMemory(tmp_path)
    memory.record_decision("gx101", "llm-qwen", scene_type="action", shot_type="long",
                           project_id="归墟第二部", episode="ep02")
    raw = memory.shot.get("gx101")
    assert raw["project_id"] == "归墟第二部"
    assert raw["episode"] == "ep02"
    exp = memory.shot.experiences()[0]
    assert exp.project_id == "归墟第二部"
    assert exp.episode == "ep02"


def test_record_quality_with_production_fields(tmp_path):
    memory = DirectorMemory(tmp_path)
    memory.record_decision("gx102", "rule-v2", scene_type="action", project_id="P1")
    memory.record_quality(
        "gx102", 0.88, {"items": [{"issue": "static_video"}]},
        production_cost=12.5, generation_time=42.0,
        human_score=91.0, revision_count=2, final_approved=True,
    )
    raw = memory.shot.get("gx102")
    assert raw["production_cost"] == 12.5
    assert raw["generation_time"] == 42.0
    assert raw["human_score"] == 91.0
    assert raw["revision_count"] == 2
    assert raw["final_approved"] is True
    # policy memory reflects the updated quality
    row = memory.policy.stats()[0]
    assert row["avg_quality"] == 0.9


def test_accumulation_summary_counts(tmp_path):
    memory = DirectorMemory(tmp_path)
    for i in range(3):
        memory.record_decision(f"a{i}", "rule-v2", scene_type="action", project_id="P1", episode="ep1")
        memory.record_quality(f"a{i}", 0.8, {"items": [{"issue": "low_motion"}]})
    for i in range(2):
        memory.record_decision(f"b{i}", "rule-v2", scene_type="dialogue", project_id="P2", episode="ep1")
    summary = memory.accumulation()
    assert summary["shots"] == 5
    assert summary["projects"] == 2
    assert summary["feedback_records"] == 3
    assert summary["targets"]["shots"] == 500
    assert summary["targets"]["projects"] == 3


def test_policy_director_records_project_from_context(tmp_path):
    director = PolicyDirector(llm_provider=_FakeLLM(), memory_root=tmp_path)
    shot = _shot("gx103")
    director.plan_shot(shot, {"scene_type": "dialogue", "project_id": "归墟第二部", "episode": "ep03"})
    raw = director.memory.shot.get("gx103")
    assert raw["project_id"] == "归墟第二部"
    assert raw["episode"] == "ep03"
