"""Phase 10.7-B: Hybrid Director LLM tests.

Covers the GPT acceptance criteria:
- Rule Provider: 100-shot run -> 100/100 valid ShotDirective
- LLM Provider (mocked): valid JSON is used, invalid JSON/schema falls back
  to the rule director automatically
- Validator unit checks for every gate
"""

from __future__ import annotations

from types import SimpleNamespace

from backend.agents.director_v2 import ShotDirective
from backend.director.director_bridge import DirectorBridge
from backend.director.hybrid import HybridDirector
from backend.director.providers import ProviderError
from backend.director.providers.base import build_directive, parse_directive_json
from backend.director.validator import ShotValidator
from backend.story.models import Shot

_SNIPPET = """At 3:17 AM, in the gene archaeology lab, Su Wan frowned at the gene sequence on the screen.
She pressed the red button; the alarm rang and the corridor lights began to flash.

In the underground tunnel, Chen Ye shone his flashlight, footsteps echoing.
He saw never-before-seen characters carved on a bronze door, his heart racing."""


def _shot(i: int) -> Shot:
    types = ["wide", "medium", "close-up", "long", "extreme-close-up"]
    emotions = ["dark", "tense", "calm", "hopeful", "dramatic"]
    return Shot(
        id=f"gx_{i + 1:03d}",
        scene_id=f"scene_{i // 10}",
        index=i,
        shot_type=types[i % len(types)],
        camera_angle="eye-level" if i % 3 else "low-angle",
        camera_movement="static",
        description=f"shot {i} action",
        emotion=emotions[i % len(emotions)],
        duration=5.0,
        character_ids=["chenye", "suwan"] if i % 2 == 0 else ["chenye"],
    )


def _section(scene_id: str):
    return SimpleNamespace(
        scene_id=scene_id,
        character_state={"chenye": "black coat", "suwan": "white lab coat"},
        visual_theme={"palette": "cold_blue", "texture": "stone"},
        emotion="tense",
    )


def _shots_and_sections(n: int = 100):
    shots = [_shot(i) for i in range(n)]
    sections = [_section(f"scene_{i}") for i in range(n // 10 + 1)]
    return shots, sections


class FakeLLMDirector:
    """Deterministic fake LLM director for router tests."""

    name = "llm-fake"
    is_available = True

    def __init__(self, payload: dict | None = None, *, raise_error: bool = False, bad_schema: bool = False):
        self.payload = payload
        self.raise_error = raise_error
        self.bad_schema = bad_schema
        self.calls = 0

    def generate_directive(self, shot, section_context=None):
        self.calls += 1
        if self.raise_error:
            raise ProviderError("network down")
        data = self.payload or {
            "shot_id": shot.id,
            "shot_intent": "emotional_beat",
            "camera": {"angle": "low-angle", "movement": "push-in", "distance": "close-up"},
            "lighting": {"style": "chiaroscuro", "key": "rim", "temperature": "cool"},
            "emotion_curve": [
                {"t": 0.0, "emotion": "tense", "intensity": 0.6},
                {"t": 2.5, "emotion": "dramatic", "intensity": 0.9},
                {"t": 5.0, "emotion": "dark", "intensity": 0.8},
            ],
            "continuity": {"previous_shot": "", "constraints": ["carry_character_state:chenye"]},
            "rationale": "fake llm directive",
        }
        if self.bad_schema:
            data = dict(data)
            data.pop("camera")  # validator must reject and fall back
        return build_directive(shot, data, director_version=self.name)


# ---------------------------------------------------------------- validator
def test_validator_accepts_rule_directive():
    shot = _shot(0)
    directive = HybridDirector(llm_provider=None).plan_shot(shot, {})
    report = ShotValidator().validate(directive, shot)
    assert report.ok, report.errors
    assert set(report.checks) >= {
        "camera_valid", "lighting_valid", "character_valid",
        "continuity_valid", "emotion_valid", "physics_valid",
    }


def test_validator_rejects_missing_camera():
    shot = _shot(0)
    directive = HybridDirector(llm_provider=None).plan_shot(shot, {})
    directive.camera = {}
    report = ShotValidator().validate(directive, shot)
    assert not report.ok
    assert "camera missing" in " ".join(report.errors)


def test_validator_rejects_impossible_camera_physics():
    shot = _shot(0)
    directive = HybridDirector(llm_provider=None).plan_shot(shot, {})
    directive.camera["movement"] = "orbit"
    directive.camera["distance"] = "extreme-close-up"
    report = ShotValidator().validate(directive, shot)
    assert not report.ok
    assert "impossible camera combo" in " ".join(report.errors)


def test_validator_rejects_bad_emotion_and_physics():
    shot = _shot(0)
    directive = HybridDirector(llm_provider=None).plan_shot(shot, {})
    directive.emotion_curve = [{"t": 0.0, "emotion": "calm", "intensity": 3.0}]
    report = ShotValidator().validate(directive, shot)
    assert not report.ok
    assert "intensity" in " ".join(report.errors)

    directive2 = HybridDirector(llm_provider=None).plan_shot(shot, {})
    directive2.emotion_curve = [
        {"t": 0.0, "emotion": "calm", "intensity": 0.5},
        {"t": 1.0, "emotion": "tense", "intensity": 0.4},
        {"t": 9.0, "emotion": "dark", "intensity": 0.8},
    ]
    report2 = ShotValidator().validate(directive2, shot)
    assert not report2.ok
    assert "monotonic" in " ".join(report2.errors) or "beyond" in " ".join(report2.errors)


def test_validator_rejects_missing_continuity_and_character_coverage():
    shot = _shot(0)  # declares chenye + suwan
    directive = HybridDirector(llm_provider=None).plan_shot(shot, {})
    directive.continuity = {"constraints": ["palette:red"]}  # no previous_shot
    report = ShotValidator().validate(directive, shot)
    assert not report.ok
    assert "previous_shot" in " ".join(report.errors)

    ctx = {"character_state": {"chenye": "black coat", "suwan": "white lab coat"}}
    directive2 = HybridDirector(llm_provider=None).plan_shot(shot, ctx)
    directive2.continuity = {"previous_shot": "", "constraints": []}
    directive2.emotion_curve = []
    report2 = ShotValidator().validate(directive2, shot, ctx)
    assert not report2.ok
    assert "characters" in " ".join(report2.errors)


def test_validate_sequence_shot_count():
    shots, sections = _shots_and_sections(10)
    hybrid = HybridDirector(llm_provider=None)
    directives = hybrid.plan_sequence(shots, sections)
    report = hybrid.last_sequence_report
    assert report.ok
    assert report.checks["shot_count"] is True

    bad_report = ShotValidator().validate_sequence(directives[:-1], shots)
    assert not bad_report.ok
    assert "shot_count mismatch" in " ".join(bad_report.errors)


# ---------------------------------------------------------------- 100-shot
def test_rule_provider_100_shots_all_valid():
    shots, sections = _shots_and_sections(100)
    hybrid = HybridDirector(llm_provider=None)
    directives = hybrid.plan_sequence(shots, sections)
    assert hybrid.last_sequence_report.ok, hybrid.last_sequence_report.errors
    validator = ShotValidator()
    for shot, directive in zip(shots, directives):
        assert directive.director_version == "rule-v2"
        assert validator.validate(directive, shot).ok


def test_hybrid_100_shots_with_llm_all_valid():
    shots, sections = _shots_and_sections(100)
    llm = FakeLLMDirector()
    hybrid = HybridDirector(llm_provider=llm)
    directives = hybrid.plan_sequence(shots, sections)
    assert hybrid.last_sequence_report.ok
    assert llm.calls == 100
    assert hybrid.stats["llm_used"] == 100
    assert hybrid.stats["rule_fallback"] == 0
    assert all(d.director_version == "llm-fake" for d in directives)
    for shot, directive in zip(shots, directives):
        assert ShotValidator().validate(directive, shot).ok


def test_llm_invalid_json_falls_back_to_rule():
    shots, sections = _shots_and_sections(5)
    llm = FakeLLMDirector(raise_error=True)
    hybrid = HybridDirector(llm_provider=llm)
    directives = hybrid.plan_sequence(shots, sections)
    assert all(d.director_version == "rule-v2" for d in directives)
    assert hybrid.stats["llm_failed"] == 5
    assert hybrid.stats["rule_fallback"] == 5
    for shot, directive in zip(shots, directives):
        assert ShotValidator().validate(directive, shot).ok


def test_llm_bad_schema_falls_back_to_rule():
    shots, sections = _shots_and_sections(3)
    llm = FakeLLMDirector(bad_schema=True)
    hybrid = HybridDirector(llm_provider=llm)
    directives = hybrid.plan_sequence(shots, sections)
    assert all(d.director_version == "rule-v2" for d in directives)
    assert hybrid.stats["llm_failed"] == 3
    assert hybrid.stats["llm_used"] == 0


# ---------------------------------------------------------------- parsing
def test_parse_directive_json_strips_markdown_fence():
    shot = _shot(0)
    content = '```json\n{"shot_id": "gx_001", "camera": {"angle": "high-angle", "movement": "tilt", "distance": "long"}}\n```'
    directive = parse_directive_json(content, shot, director_version="llm-fake")
    assert directive.camera["angle"] == "high-angle"
    assert directive.director_version == "llm-fake"


def test_parse_directive_json_bad_json_raises():
    shot = _shot(0)
    try:
        parse_directive_json("not json at all", shot, director_version="llm-fake")
        raise AssertionError("expected ProviderError")
    except ProviderError:
        pass


# ---------------------------------------------------------------- bridge
def test_bridge_plan_text_hybrid_outputs_valid_directives():
    bridge = DirectorBridge(llm_provider=None)  # force rule, deterministic
    result = bridge.plan_text(_SNIPPET, "hybrid_novel")
    assert result["shots_total"] >= 1
    for d in result["directives"]:
        assert d["director_version"] == "rule-v2"
        assert d["camera"]["angle"]
        assert "previous_shot" in d["continuity"]


