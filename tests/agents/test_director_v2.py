from __future__ import annotations

from backend.agents.director_v2 import DirectorV2Agent, ShotDirective
from backend.story.models import Shot


def _shot(sid: str, scene_id: str = "sc1", shot_type: str = "close-up", emotion: str = "tense") -> Shot:
    return Shot(id=sid, scene_id=scene_id, shot_type=shot_type, emotion=emotion,
                camera_angle="low-angle", camera_movement="push-in", duration=3.0)


def test_plan_shot_produces_full_directive():
    agent = DirectorV2Agent()
    d = agent.plan_shot(_shot("sh1"), {"character_state": {"苏晚": {"present": True}}, "visual_theme": {"palette": "cold_blue"}})
    assert isinstance(d, ShotDirective)
    assert d.shot_intent == "emotional_beat"
    assert d.camera["angle"] == "low-angle"
    assert d.camera["movement"] == "push-in"
    assert d.lighting["palette"] == "cold_blue"
    assert len(d.emotion_curve) == 3
    assert d.emotion_curve[-1]["t"] == 3.0
    assert any("palette:cold_blue" in c for c in d.continuity["constraints"])


def test_plan_sequence_threads_previous_shot():
    agent = DirectorV2Agent()
    shots = [_shot("sh1"), _shot("sh2"), _shot("sh3")]
    ds = agent.plan_sequence(shots)
    assert ds[0].continuity["previous_shot"] == ""
    assert ds[1].continuity["previous_shot"] == "sh1"
    assert ds[2].continuity["previous_shot"] == "sh2"


def test_wide_shot_intent():
    agent = DirectorV2Agent()
    d = agent.plan_shot(_shot("w1", shot_type="wide"))
    assert d.shot_intent == "establish_space"
