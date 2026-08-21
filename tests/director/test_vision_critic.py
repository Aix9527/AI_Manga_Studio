"""Phase 11.2: Vision Critic Loop tests (no network, no video files)."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from backend.director.memory import DirectorMemory
from backend.director.memory.feedback_schema import (
    FEEDBACK_CATEGORIES,
    ISSUE_MAP,
    SEVERITY_LEVELS,
    VisionFeedback,
    feedback_from_issue,
)
from backend.director.policy_router import DirectorRouter, PolicyDirector
from backend.director.vision_critic import VisionCritic
from backend.director.vision_critic_loop import VisionCriticLoop
from backend.story.models import Shot
from backend.video.identity_gate import IdentityGateReport


def _shot(shot_id: str, scene_id: str, shot_type: str = "medium", emotion: str = "tense") -> Shot:
    return Shot(id=shot_id, scene_id=scene_id, shot_type=shot_type, emotion=emotion, duration=3.0)


def _section(scene_id: str, scene_type: str, emotion: str = "tense"):
    return SimpleNamespace(
        scene_id=scene_id, scene_type=scene_type,
        character_state={}, visual_theme={}, emotion=emotion,
    )


def _fake_quality(issues: list[str], score: float = 50.0, **extra):
    data = dict(
        overall_score=score, passed=False, issues=issues,
        recommendations=["adjust the generation prompt"],
        mean_frame_diff=0.3, static_frame_ratio=0.95, motion_score=0.1,
        motion_cv=0.6, temporal_consistency=0.8,
    )
    data.update(extra)
    return SimpleNamespace(**data)


def _fake_identity_fail(cid: str = "suwan", ratio: float = 0.4) -> IdentityGateReport:
    return IdentityGateReport(
        video_path="shot.mp4", frames_checked=5,
        per_character={cid: {"verdict": "fail", "presence_ratio": ratio}},
        overall_verdict="fail",
    )


# ------------------------------------------------------------------ schema
def test_feedback_schema_categories_and_severity():
    assert "character_identity" in FEEDBACK_CATEGORIES
    assert set(SEVERITY_LEVELS) == {"low", "medium", "high"}
    item = VisionFeedback(shot_id="s1", category="motion", severity="high", issue="static_video")
    assert item.validate()
    bad = VisionFeedback(shot_id="s1", category="not_a_category", severity="high")
    assert not bad.validate()


def test_feedback_from_issue_maps_category_severity_suggestion():
    item = feedback_from_issue("s1", "static_video")
    assert item.category == "motion"
    assert item.severity == "high"
    assert item.suggestion
    unknown = feedback_from_issue("s1", "brand_new_issue")
    assert unknown.category == "physics"  # safe default


def test_issue_map_categories_all_valid():
    for issue, (category, severity, _) in ISSUE_MAP.items():
        assert category in FEEDBACK_CATEGORIES, issue
        assert severity in SEVERITY_LEVELS, issue


# ------------------------------------------------------------ critic rules
def test_critic_emotion_too_strong_detected_without_mutating_directive():
    critic = VisionCritic()
    shot = _shot("s1", "sc1", emotion="calm")
    director = PolicyDirector(llm_provider=None, memory_root=None)
    directive = director.plan_shot(shot, {"scene_type": "emotion"})
    # force a very strong peak to simulate an over-acted emotion
    for point in directive.emotion_curve:
        point["intensity"] = 1.0
    snapshot = [dict(p) for p in directive.emotion_curve]
    result = critic.critique(shot, directive)
    assert any(f.issue == "emotion_too_strong" for f in result.feedback)
    # GPT constraint 1: the critic never mutates the directive
    assert [dict(p) for p in directive.emotion_curve] == snapshot


def test_critic_camera_physics_rule_check():
    critic = VisionCritic()
    shot = _shot("s2", "sc2")
    director = PolicyDirector(llm_provider=None, memory_root=None)
    directive = director.plan_shot(shot, {"scene_type": "action"})
    directive.camera["movement"] = "orbit"
    directive.camera["distance"] = "extreme-close-up"
    result = critic.critique(shot, directive)
    assert any(f.issue == "camera_physics" for f in result.feedback)


def test_critic_maps_quality_gate_issues():
    critic = VisionCritic()
    shot = _shot("s3", "sc3", emotion="neutral")
    directive = PolicyDirector(llm_provider=None, memory_root=None).plan_shot(shot, {"scene_type": "action"})
    report = _fake_quality(["static_video", "too_dark"], score=45.0)
    result = critic.critique(shot, directive, quality_report=report)
    categories = {f.category for f in result.feedback}
    assert "motion" in categories
    assert "lighting" in categories
    assert any(f.detail.get("motion_cv") == 0.6 for f in result.feedback)


def test_critic_maps_identity_gate_failure():
    critic = VisionCritic()
    shot = _shot("s4", "sc4")
    directive = PolicyDirector(llm_provider=None, memory_root=None).plan_shot(shot, {"scene_type": "dialogue"})
    result = critic.critique(shot, directive, identity_report=_fake_identity_fail(ratio=0.4))
    assert any(f.category == "character_identity" for f in result.feedback)
    assert any(f.issue == "character_drift" for f in result.feedback)
    assert result.passed is False
    assert result.quality_score < 60.0


def test_critic_score_penalties_and_passed():
    critic = VisionCritic()
    shot = _shot("s5", "sc5", emotion="neutral")
    directive = PolicyDirector(llm_provider=None, memory_root=None).plan_shot(shot, {"scene_type": "environment"})
    clean = critic.critique(shot, directive)
    assert clean.passed and clean.quality_score >= 60.0
    bad = critic.critique(shot, directive, quality_report=_fake_quality(["mosaic", "block_artifact"], score=30.0))
    assert not bad.passed
    assert any(f.category == "physics" for f in bad.feedback)


# ------------------------------------------------- memory -> next directive
def test_memory_adjustments_from_feedback(tmp_path):
    memory = DirectorMemory(tmp_path)
    memory.record_decision("prev", "rule-v2", scene_type="action", shot_type="long")
    memory.record_quality("prev", 40.0, {"items": [feedback_from_issue("prev", "static_video").to_dict()]})
    adjustments = memory.adjustments_for("prev")
    assert "static" in adjustments["avoid_movements"]
    assert adjustments["note"] == "static_video:add_motion"
    assert memory.adjustments_for("unknown") == {}


def test_apply_memory_feedback_changes_next_directive(tmp_path):
    director = PolicyDirector(llm_provider=None, memory_root=tmp_path)
    prev = _shot("p1", "scp", shot_type="long", emotion="neutral")
    nxt = _shot("n1", "scn", shot_type="long", emotion="neutral")
    section = {"scene_type": "action"}
    director.plan_shot(prev, section)  # creates the memory record for p1
    baseline = director.plan_shot(nxt, section)
    baseline.continuity["previous_shot"] = "p1"
    director.apply_memory_feedback(baseline)
    assert "memory_feedback" not in baseline.continuity

    # record emotion feedback on the previous shot, then plan the next one
    director.record_quality("p1", 45.0, {"items": [feedback_from_issue("p1", "emotion_too_strong").to_dict()]})

    directive = director.plan_shot(nxt, section)
    directive.continuity["previous_shot"] = "p1"
    director.apply_memory_feedback(directive)
    assert directive.continuity.get("memory_feedback") == "emotion_too_strong:reduce_expression_level"
    assert "memory_feedback" in directive.rationale
    peak = max(p["intensity"] for p in directive.emotion_curve)
    assert peak < 0.7  # 0.55 scale applied (traceable next-shot optimization)


def test_policy_director_plan_sequence_applies_memory_feedback(tmp_path):
    director = PolicyDirector(llm_provider=None, memory_root=tmp_path)
    sections = [_section("sc1", "emotion", emotion="dramatic"), _section("sc2", "action")]
    shots = [_shot("a1", "sc1", shot_type="medium", emotion="dramatic"),
             _shot("a2", "sc2", shot_type="long", emotion="neutral")]
    director.plan_sequence(shots, sections)
    director.record_quality("a1", 40.0, {"items": [feedback_from_issue("a1", "emotion_too_strong").to_dict()]})
    directives = director.plan_sequence(shots, sections)
    assert directives[1].continuity.get("memory_feedback") == "emotion_too_strong:reduce_expression_level"


# -------------------------------------------------------------- 20-shot loop
def _build_20_shot_mvp():
    specs = [
        ("d01", "sc-d1", "medium", "dialogue", "tense"),
        ("d02", "sc-d2", "close-up", "dialogue", "calm"),
        ("d03", "sc-d3", "medium", "dialogue", "tense"),
        ("d04", "sc-d4", "close-up", "dialogue", "hopeful"),
        ("d05", "sc-d5", "medium", "dialogue", "neutral"),
        ("a01", "sc-a1", "long", "action", "tense"),
        ("a02", "sc-a2", "wide", "action", "dramatic"),
        ("a03", "sc-a3", "long", "action", "tense"),
        ("a04", "sc-a4", "wide", "action", "dramatic"),
        ("a05", "sc-a5", "long", "action", "tense"),
        ("e01", "sc-e1", "wide", "environment", "neutral"),
        ("e02", "sc-e2", "panorama", "environment", "calm"),
        ("e03", "sc-e3", "wide", "environment", "neutral"),
        ("e04", "sc-e4", "panorama", "environment", "calm"),
        ("e05", "sc-e5", "wide", "environment", "neutral"),
        ("c01", "sc-c1", "close-up", "climax", "dramatic"),
        ("c02", "sc-c2", "medium", "climax", "dramatic"),
        ("c03", "sc-c3", "extreme-close-up", "climax", "tense"),
        ("c04", "sc-c4", "medium", "climax", "dramatic"),
        ("c05", "sc-c5", "close-up", "climax", "dramatic"),
    ]
    shots = [_shot(sid, scid, st, emo) for sid, scid, st, stype, emo in
             [(s[0], s[1], s[2], s[3], s[4]) for s in specs]]
    sections = [_section(s[1], s[3], s[4]) for s in specs]
    return shots, sections


def test_vision_critic_loop_requires_memory():
    director = PolicyDirector(llm_provider=None)
    with pytest.raises(ValueError):
        VisionCriticLoop(director)


def test_vision_critic_loop_20_shot_acceptance(tmp_path):
    shots, sections = _build_20_shot_mvp()
    director = PolicyDirector(llm_provider=None, memory_root=tmp_path)
    loop = VisionCriticLoop(director)

    gate_reports = {}
    seeded = {}
    for i, shot in enumerate(shots):
        scene_type = sections[i].scene_type
        if scene_type == "dialogue":
            seeded[shot.id] = ["character_drift"]
            gate_reports[shot.id] = {"identity": _fake_identity_fail(ratio=0.4)}
        elif scene_type == "action":
            seeded[shot.id] = ["static_video"]
            gate_reports[shot.id] = {"quality": _fake_quality(["static_video"], score=45.0)}
        elif scene_type == "environment":
            seeded[shot.id] = ["too_dark"]
            gate_reports[shot.id] = {"quality": _fake_quality(["too_dark"], score=60.0)}
        else:  # climax
            seeded[shot.id] = ["emotion_too_strong"]
            gate_reports[shot.id] = {"quality": _fake_quality(["emotion_too_strong"], score=55.0)}

    report = loop.run(
        shots, sections,
        gate_reports=gate_reports,
        seeded=seeded,
    )
    metrics = report["metrics"]
    # GPT MVP gate 1: problem detection >= 80%
    assert metrics["seeded_problems"] == 20
    assert metrics["problem_detection_rate"] >= 0.8
    # GPT MVP gate 2: feedback written to memory = 100%
    assert metrics["feedback_write_rate"] == 1.0
    # GPT MVP gate 3: next-shot directive change >= 50% (substantive: 12/19)
    assert metrics["directive_change_rate"] >= 0.5
    assert len(report["directives"]) == 20


def test_vision_critic_loop_directives_traceable(tmp_path):
    shots, sections = _build_20_shot_mvp()[:4]
    shots, sections = shots[:4], sections[:4]
    director = PolicyDirector(llm_provider=None, memory_root=tmp_path)
    loop = VisionCriticLoop(director)
    gate_reports = {
        shots[0].id: {"quality": _fake_quality(["static_video"], score=40.0)},
        shots[1].id: {"quality": _fake_quality(["emotion_too_strong"], score=50.0)},
    }
    report = loop.run(shots, sections, gate_reports=gate_reports)
    # second directive carried the previous shot's feedback note
    assert report["directives"][1].continuity.get("memory_feedback") == "static_video:add_motion"
    # memory holds structured feedback for every shot (write rate 100%)
    for result in report["results"]:
        memory = director.memory.shot.get(result["shot_id"])
        assert "feedback" in memory
        assert "quality_score" in memory
    # seeded shots carry the detected items
    memory0 = director.memory.shot.get(shots[0].id)
    issues0 = {f.get("issue") for f in (memory0.get("feedback") or {}).get("items", [])}
    assert "static_video" in issues0


# ------------------------------------------------------------ router config
def test_router_exposes_policy_learning_config():
    router = DirectorRouter()
    assert router.policy_learning.get("min_samples") == 20
    assert router.policy_learning.get("confidence_threshold") == 0.85
    assert router.policy_learning.get("mode") == "manual_approval"
