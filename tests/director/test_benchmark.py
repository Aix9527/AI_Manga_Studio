"""Phase 10.8-A: benchmark harness tests (no network)."""

from __future__ import annotations

from backend.director.benchmark import evaluate, load_scenes, run_ab, run_group, scene_to_shot
from backend.director.hybrid import HybridDirector
from backend.director.validator import ShotValidator


class FakeLLMBenchmark:
    """Deterministic LLM for benchmark tests (diverse camera + rich continuity)."""

    name = "llm-bench"
    is_available = True

    def generate_directive(self, shot, section_context=None):
        from backend.director.providers.base import build_directive

        data = {
            "shot_id": shot.id,
            "shot_intent": "reveal_detail",
            "camera": {"angle": "low-angle", "movement": "tracking", "distance": "long"},
            "lighting": {"style": "chiaroscuro", "key": "rim", "temperature": "cool"},
            "emotion_curve": [
                {"t": 0.0, "emotion": "calm", "intensity": 0.2},
                {"t": shot.duration / 2, "emotion": "tense", "intensity": 0.8},
                {"t": shot.duration, "emotion": "dark", "intensity": 0.9},
            ],
            "continuity": {"previous_shot": "", "constraints": ["carry_character_state:suwan", "palette:cold_blue"]},
            "rationale": "benchmark fake",
        }
        return build_directive(shot, data, director_version=self.name)


def test_load_scenes_returns_20_benchmark_scenes():
    scenes = load_scenes()
    assert len(scenes) >= 10
    first = scenes[0]
    assert first["scene_id"]
    assert first["shot"]["id"]
    shot = scene_to_shot(first)
    assert shot.id == first["shot"]["id"]
    assert shot.character_ids is not None


def test_run_ab_rule_vs_fake_llm_metrics_structure():
    scenes = load_scenes()[:10]
    report = run_ab(
        provider_b=FakeLLMBenchmark(),
        scenes=scenes,
        limit=10,
    )
    assert report["scenes_used"] == 10
    assert report["metrics_a"]["director_version"] == "rule-v2"
    assert report["metrics_b"]["director_version"] == "llm-bench"
    assert report["metrics_a"]["valid_rate"] == 1.0
    assert report["metrics_b"]["valid_rate"] == 1.0
    assert report["metrics_b"]["physics_violations"] == 0
    for key in ("camera_diversity", "movement_quality", "continuity_score", "emotion_span"):
        assert key in report["metrics_a"]
        assert key in report["metrics_b"]
    assert set(report["comparison"]["winners"]) == {
        "valid_rate", "camera_diversity", "movement_quality", "continuity_score", "emotion_span",
    }


def test_evaluate_reports_shot_type_distribution():
    scenes = load_scenes()[:5]
    validator = ShotValidator()
    hybrid = HybridDirector(llm_provider=FakeLLMBenchmark())
    directives = run_group(scenes, hybrid, validator)
    metrics = evaluate("B", scenes, directives, validator)
    assert metrics["shot_type_distribution"]  # non-empty
    assert metrics["avg_constraints"] >= 1.0
    assert metrics["valid_rate"] == 1.0


# ---------------------------------------------------------------- 100-shot
def test_load_100_shot_scenes_full_coverage():
    from backend.director.benchmark import load_100_shot_scenes

    scenes = load_100_shot_scenes()
    assert len(scenes) == 100
    assert scenes[0]["shot"]["id"] == "gx_001"
    assert scenes[-1]["shot"]["id"] == "gx_100"


def test_run_100_ab_fake_llm_writes_manifests(tmp_path):
    from backend.director.benchmark import run_100_ab

    summary = run_100_ab(provider_b=FakeLLMBenchmark(), out_dir=tmp_path / "ab", limit=10)
    assert summary["shots"] == 10
    assert (tmp_path / "ab" / "rule_v2" / "gx_001.json").exists()
    assert (tmp_path / "ab" / "qwen" / "gx_001.json").exists()
    assert (tmp_path / "ab" / "human_review_20.json").exists()
    assert "director_entropy" in summary["metrics_b"]
    assert "camera_entropy" in summary["metrics_b"]["director_entropy"]
    assert summary["metrics_b"]["character_intent_alignment"] >= 0.0
    assert "phase11_entry" in summary
    assert "qwen_lead_pct" in summary["phase11_entry"]


def test_mixture_pick_routes_by_scene_type():
    from backend.director.benchmark import mixture_pick
    from backend.director.providers.base import build_directive
    from backend.story.models import Shot

    shot = Shot(id="gx_001", duration=6.0)
    rule_d = build_directive(shot, {"shot_intent": "context_action"}, director_version="rule-v2")
    llm_d = build_directive(shot, {"shot_intent": "reveal_detail"}, director_version="llm-qwen")

    action_scene = {"section_context": {"scene_type": "action"}}
    emotion_scene = {"section_context": {"scene_type": "emotion"}}
    world_scene = {"section_context": {"scene_type": "world"}}
    assert mixture_pick(action_scene, rule_d, llm_d).director_version == "rule-v2"
    assert mixture_pick(emotion_scene, rule_d, llm_d).director_version == "llm-qwen"
    # world -> hybrid -> LLM side of the manifest
    assert mixture_pick(world_scene, rule_d, llm_d).director_version == "llm-qwen"


def test_run_mixture_eval_on_fake_manifests(tmp_path):
    from backend.director.benchmark import load_100_shot_scenes, run_100_ab, run_mixture_eval

    scenes = load_100_shot_scenes()[:10]
    run_100_ab(provider_b=FakeLLMBenchmark(), out_dir=tmp_path / "ab", limit=10)
    result = run_mixture_eval(scenes, tmp_path / "ab")
    metrics = result["metrics"]
    assert metrics["shots"] == 10
    assert metrics["valid_rate"] == 1.0
    assert sum(metrics["routed"].values()) == 10
    assert len(result["directives"]) == 10


# ---------------------------------------------------------------- router
def test_director_router_policy_yaml():
    from backend.director.policy_router import DirectorRouter

    router = DirectorRouter()
    assert router.route_for("action") == "rule"
    assert router.route_for("emotion") == "qwen"
    assert router.route_for("dialogue") == "qwen"
    assert router.route_for("world") == "hybrid"
    assert router.route_for("unknown_scene") == "hybrid"  # default


def test_policy_director_routes_action_to_rule_and_emotion_to_llm():
    from backend.director.policy_router import PolicyDirector

    from backend.story.models import Shot

    director = PolicyDirector(llm_provider=FakeLLMBenchmark())
    action_shot = Shot(id="gx_001", shot_type="wide", emotion="tense", duration=6.0)
    emotion_shot = Shot(id="gx_002", shot_type="close-up", emotion="hopeful", duration=6.0)
    d_action = director.plan_shot(action_shot, {"scene_type": "action", "character_state": {"chenye": "x"}})
    d_emotion = director.plan_shot(emotion_shot, {"scene_type": "emotion", "character_state": {"chenye": "x"}})
    assert d_action.director_version == "rule-v2"
    assert d_emotion.director_version == "llm-bench"
    assert director.routed == {"rule": 1, "qwen": 1}

