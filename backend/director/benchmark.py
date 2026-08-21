"""Phase 10.8-A: Director A/B benchmark harness.

Compares director providers (rule-v2 vs LLM) on a fixed benchmark dataset
(tests/director/benchmark/scene_*.json) with the same story memory, shot
input and validator, changing only the director.

Metrics per GPT spec: camera_diversity, shot_type_distribution,
movement_quality, continuity_score, emotion quality + validation pass rate.

CLI:  python -m backend.director.benchmark --ab --limit 20
"""

from __future__ import annotations

import argparse
import json
import logging
import re
from pathlib import Path
from typing import Any

from backend.agents.director_v2 import ShotDirective
from backend.director.hybrid import HybridDirector
from backend.director.providers import RuleDirectorProvider
from backend.director.providers.qwen_provider import QwenDirectorProvider
from backend.director.validator import ShotValidator
from backend.story.models import Shot

logger = logging.getLogger(__name__)

BENCHMARK_DIR = Path("tests/director/benchmark")


def load_scenes(path: str | Path = BENCHMARK_DIR) -> list[dict]:
    path = Path(path)
    files = sorted(path.glob("scene_*.json"))
    scenes = []
    for f in files:
        scenes.append(json.loads(f.read_text(encoding="utf-8")))
    return scenes


def scene_to_shot(scene: dict) -> Shot:
    data = scene.get("shot", {})
    return Shot(
        id=str(data.get("id") or scene.get("scene_id", "")),
        scene_id=str(data.get("scene_id") or scene.get("scene_id", "")),
        index=int(data.get("index", 0)),
        shot_type=str(data.get("shot_type", "medium")),
        camera_angle=str(data.get("camera_angle", "eye-level")),
        camera_movement=str(data.get("camera_movement", "static")),
        description=str(data.get("description", "")),
        action=str(data.get("action", "")),
        dialogue=str(data.get("dialogue", "")),
        emotion=str(data.get("emotion", "")),
        duration=float(data.get("duration", 5.0)),
        character_ids=list(data.get("character_ids") or []),
    )


def run_group(
    scenes: list[dict],
    director: HybridDirector,
    validator: ShotValidator,
) -> list[ShotDirective]:
    shots = [scene_to_shot(s) for s in scenes]
    sections = [s.get("section_context", {}) for s in scenes]
    directives: list[ShotDirective] = []
    prev_id = ""
    for shot, section in zip(shots, sections):
        directive = director.plan_shot(shot, section)
        directive.continuity = dict(directive.continuity or {})
        directive.continuity["previous_shot"] = prev_id
        directives.append(directive)
        prev_id = shot.id
    return directives


def evaluate(
    name: str,
    scenes: list[dict],
    directives: list[ShotDirective],
    validator: ShotValidator,
) -> dict:
    shots = [scene_to_shot(s) for s in scenes]
    valid = 0
    camera_pairs: set[tuple[str, str]] = set()
    intents: dict[str, int] = {}
    movements = [d.camera.get("movement", "") for d in directives]
    non_static = sum(1 for m in movements if m and m != "static")
    continuity_ok = 0
    constraints_total = 0
    intensity_spans: list[float] = []
    physics_fail = 0
    for shot, scene, directive in zip(shots, scenes, directives):
        report = validator.validate(directive, shot, scene.get("section_context", {}))
        if report.ok:
            valid += 1
        if not report.checks.get("physics_valid", True):
            physics_fail += 1
        camera_pairs.add((str(directive.camera.get("angle", "")), str(directive.camera.get("distance", ""))))
        intents[str(directive.shot_intent or "")] = intents.get(str(directive.shot_intent or ""), 0) + 1
        if directive.continuity.get("previous_shot") is not None:
            continuity_ok += 1
        constraints = directive.continuity.get("constraints", []) or []
        constraints_total += len(constraints)
        intensities = [float(p.get("intensity", 0)) for p in (directive.emotion_curve or [])]
        if intensities:
            intensity_spans.append(max(intensities) - min(intensities))

    total = max(len(directives), 1)
    return {
        "group": name,
        "shots": len(directives),
        "valid_rate": round(valid / total, 4),
        "camera_diversity": round(len(camera_pairs) / total, 4),
        "unique_camera_pairs": len(camera_pairs),
        "shot_type_distribution": dict(sorted(intents.items(), key=lambda kv: -kv[1])),
        "movement_quality": round(non_static / total, 4),
        "continuity_score": round((continuity_ok + (constraints_total / total)) / 2, 4),
        "avg_constraints": round(constraints_total / total, 2),
        "emotion_span": round(sum(intensity_spans) / len(intensity_spans), 3) if intensity_spans else 0.0,
        "physics_violations": physics_fail,
        "director_version": directives[0].director_version if directives else "",
    }


def compare(metrics_a: dict, metrics_b: dict) -> dict:
    keys = ["valid_rate", "camera_diversity", "movement_quality", "continuity_score", "emotion_span"]
    winners: dict[str, str] = {}
    for key in keys:
        va, vb = metrics_a.get(key, 0), metrics_b.get(key, 0)
        winners[key] = "a" if va > vb else ("b" if vb > va else "tie")
    return {
        "keys": keys,
        "winners": winners,
        "a_wins": sum(1 for w in winners.values() if w == "a"),
        "b_wins": sum(1 for w in winners.values() if w == "b"),
        "ties": sum(1 for w in winners.values() if w == "tie"),
        "conclusion": "B (LLM) better" if sum(1 for w in winners.values() if w == "b")
                      > sum(1 for w in winners.values() if w == "a") else "A (rule) better or tie",
    }


def run_ab(
    provider_a: Any = None,
    provider_b: Any = None,
    scenes: list[dict] | None = None,
    limit: int = 20,
) -> dict:
    scenes = scenes or load_scenes()
    scenes = scenes[:limit]
    validator = ShotValidator()
    rule_hybrid = HybridDirector(rule_provider=provider_a or RuleDirectorProvider(), llm_provider=None)
    llm_hybrid = HybridDirector(llm_provider=provider_b or QwenDirectorProvider())

    directives_a = run_group(scenes, rule_hybrid, validator)
    directives_b = run_group(scenes, llm_hybrid, validator)
    metrics_a = evaluate("A: rule-v2", scenes, directives_a, validator)
    metrics_b = evaluate("B: llm", scenes, directives_b, validator)
    return {
        "phase": "10.8-A",
        "scenes_used": len(scenes),
        "metrics_a": metrics_a,
        "metrics_b": metrics_b,
        "comparison": compare(metrics_a, metrics_b),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Director A/B benchmark (Phase 10.8-A)")
    parser.add_argument("--ab", action="store_true", help="run rule-v2 vs LLM A/B")
    parser.add_argument("--ab100", action="store_true", help="run full 100-shot A/B (Phase 10.8-B)")
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--out", default="docs/benchmark_ab_report.json")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO if args.verbose else logging.WARNING)
    if args.ab100:
        report = run_100_ab(limit=args.limit)
        out = Path(args.out)
        out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(report["comparison"], ensure_ascii=False, indent=2))
        print("phase11_entry:", json.dumps(report["phase11_entry"], ensure_ascii=False))
        print("manifests + summary saved under outputs/director_ab/")
        return
    report = run_ab(limit=args.limit)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report["comparison"], ensure_ascii=False, indent=2))
    print("report saved:", out)



# ---------------------------------------------------------------------------
# Phase 10.8-B: full 100-shot A/B (gx001-gx100) + entropy + human review
# ---------------------------------------------------------------------------

NAME_TO_ID = {
    "苏晚": "suwan", "方觉明": "fangjueming", "陈夜": "chenye",
    "苏澜": "sulan", "白泽": "baize", "陆沉": "luchen", "顾长风": "guchangfeng",
    "江离": "jiangli", "墨渊": "moyuan", "云汐": "yunxi", "秦霜": "qinshuang",
}

_TYPE_EMOTION = {"world": "calm", "environment": "calm", "action": "tense",
                 "dialogue": "dramatic", "emotion": "hopeful"}


def _parse_camera(camera: str) -> tuple[str, str, str]:
    c = (camera or "").lower()
    if "close-up" in c or "close up" in c:
        shot_type = "close-up"
    elif "wide" in c or "establish" in c or "panorama" in c:
        shot_type = "wide"
    elif "long" in c:
        shot_type = "long"
    else:
        shot_type = "medium"
    if "aerial" in c or "bird" in c or "top" in c:
        angle = "high-angle"
    elif "low" in c or "worm" in c:
        angle = "low-angle"
    elif "dutch" in c:
        angle = "dutch"
    else:
        angle = "eye-level"
    movement = "static"
    for m in ("push-in", "pull-out", "tracking", "pan", "tilt", "dolly", "handheld", "orbit", "crane"):
        if m in c:
            movement = m
            break
    return shot_type, angle, movement


def load_100_shot_scenes(project_dir: str | Path = "projects/归墟觉醒·天倾") -> list[dict]:
    """Aggregate gx_phase*_plan.json into 100 benchmark scenes (gx_001-gx_100)."""
    base = Path(project_dir)
    all_shots: dict[str, dict] = {}
    for f in sorted(base.glob("gx_phase*_plan.json")):
        data = json.loads(f.read_text(encoding="utf-8"))
        for shot in data.get("shots", []):
            if shot.get("id"):
                all_shots[shot["id"]] = shot

    scenes: list[dict] = []
    for i in range(1, 101):
        sid = f"gx_{i:03d}"
        shot = all_shots.get(sid, {})
        raw_chars = str(shot.get("characters") or "").strip()
        char_ids: list[str] = []
        char_state: dict[str, str] = {}
        if raw_chars:
            for name in re.split(r"[、,，/]", raw_chars):
                name = name.strip()
                if not name:
                    continue
                cid = NAME_TO_ID.get(name, f"char_{len(char_ids) + 1:02d}")
                if cid not in char_ids:
                    char_ids.append(cid)
                    char_state[cid] = name
        stype, angle, movement = _parse_camera(shot.get("camera", ""))
        emotion = _TYPE_EMOTION.get(str(shot.get("type") or ""), "neutral")
        scene_type = str(shot.get("type") or "")
        character_bible = {
            cid: {
                "role": "investigator" if cid in ("suwan", "chenye") else "character",
                "allowed": ["observation", "analysis"] if cid in ("suwan", "chenye") else [],
                "forbidden": ["heroic_pose", "leader_pose", "combat_stance"] if cid in ("suwan", "chenye") else [],
            }
            for cid in char_ids
        }
        scenes.append({
            "scene_id": f"scene_{i:03d}",
            "source_shot_id": sid,
            "scene_type": scene_type,
            "shot": {
                "id": sid,
                "scene_id": f"scene_{i:03d}",
                "index": i - 1,
                "shot_type": stype,
                "camera_angle": angle,
                "camera_movement": movement,
                "description": str(shot.get("description") or shot.get("prompt_tail") or "")[:400],
                "action": "",
                "dialogue": "",
                "emotion": emotion,
                "duration": 6.0,
                "character_ids": char_ids,
            },
            "section_context": {
                "character_state": char_state,
                "character_bible": character_bible,
                "visual_theme": {"palette": "冷蓝夜色", "texture": "剧情场景"},
                "emotion": emotion,
                "scene_type": scene_type,
            },
        })
    return scenes


def _shannon(values: list[str], total: int) -> float:
    import math
    counts: dict[str, int] = {}
    for v in values:
        counts[v] = counts.get(v, 0) + 1
    return round(-sum((c / total) * math.log2(c / total) for c in counts.values() if c), 3)


def director_entropy(directives: list[ShotDirective]) -> dict:
    """Template-ness: higher entropy = less templated direction."""
    n = max(len(directives), 1)
    return {
        "camera_entropy": _shannon(
            [f"{d.camera.get('angle', '')}|{d.camera.get('distance', '')}" for d in directives], n),
        "movement_entropy": _shannon([str(d.camera.get("movement", "")) for d in directives], n),
        "shot_type_entropy": _shannon([str(d.shot_intent or "") for d in directives], n),
    }


def character_intent_alignment(scenes: list[dict], directives: list[ShotDirective]) -> float:
    """Ratio of shots whose directive covers the declared characters/emotion."""
    aligned = 0
    for scene, directive in zip(scenes, directives):
        chars = scene.get("shot", {}).get("character_ids") or []
        constraints = " ".join(str(c) for c in (directive.continuity.get("constraints") or []))
        has_char = any(cid and cid in constraints for cid in chars)
        emotions = [str(p.get("emotion", "")) for p in (directive.emotion_curve or [])]
        shot_emo = scene.get("shot", {}).get("emotion", "")
        sec_emo = (scene.get("section_context") or {}).get("emotion", "")
        has_emo = (shot_emo and shot_emo in emotions) or (sec_emo and sec_emo in emotions)
        if (not chars) or has_char or has_emo:
            aligned += 1
    return round(aligned / max(len(directives), 1), 4)


HUMAN_REVIEW_IDS = ["gx_010", "gx_023", "gx_026", "gx_050", "gx_060",
                    "gx_068", "gx_069", "gx_080", "gx_092", "gx_100"]


def _deterministic_extra_review_ids(shots: list[str], count: int = 10) -> list[str]:
    import hashlib
    candidates = [
        (hashlib.md5(("review:" + sid).encode("utf-8")).hexdigest(), sid)
        for sid in shots if sid not in HUMAN_REVIEW_IDS
    ]
    return [sid for _, sid in sorted(candidates)[:count]]


def run_100_ab(
    provider_b: Any = None,
    project_dir: str | Path = "projects/归墟觉醒·天倾",
    out_dir: str | Path = "outputs/director_ab",
    limit: int = 100,
) -> dict:
    scenes = load_100_shot_scenes(project_dir)[:limit]
    validator = ShotValidator()
    rule_hybrid = HybridDirector(rule_provider=RuleDirectorProvider(), llm_provider=None)
    llm_hybrid = HybridDirector(llm_provider=provider_b or QwenDirectorProvider())

    directives_a = run_group(scenes, rule_hybrid, validator)
    directives_b = run_group(scenes, llm_hybrid, validator)
    metrics_a = evaluate("A: rule-v2", scenes, directives_a, validator)
    metrics_b = evaluate("B: llm", scenes, directives_b, validator)
    metrics_a["director_entropy"] = director_entropy(directives_a)
    metrics_b["director_entropy"] = director_entropy(directives_b)
    metrics_a["character_intent_alignment"] = character_intent_alignment(scenes, directives_a)
    metrics_b["character_intent_alignment"] = character_intent_alignment(scenes, directives_b)

    # Per-shot manifests: outputs/director_ab/{rule_v2,qwen}/gx_001.json
    out = Path(out_dir)
    for label, directives in (("rule_v2", directives_a), ("qwen", directives_b)):
        group_dir = out / label
        group_dir.mkdir(parents=True, exist_ok=True)
        for scene, directive in zip(scenes, directives):
            sid = scene["shot"]["id"]
            report = validator.validate(
                directive, scene_to_shot(scene), scene.get("section_context", {}))
            (group_dir / f"{sid}.json").write_text(
                json.dumps({
                    "shot_id": sid,
                    "director_version": directive.director_version,
                    "directive": {
                        "shot_intent": directive.shot_intent,
                        "camera": directive.camera,
                        "lighting": directive.lighting,
                        "emotion_curve": directive.emotion_curve,
                        "continuity": directive.continuity,
                        "rationale": directive.rationale,
                    },
                    "validation": report.to_dict(),
                }, ensure_ascii=False, indent=2),
                encoding="utf-8")

    # Human review manifest: GPT-specified 10 + deterministic random 10
    shot_ids = [s["shot"]["id"] for s in scenes]
    extra = _deterministic_extra_review_ids(shot_ids, count=10)
    review_ids = HUMAN_REVIEW_IDS + extra
    review = {
        "criteria": {"narrative_25": 25, "camera_20": 20, "emotion_20": 20,
                     "character_20": 20, "innovation_15": 15},
        "shots": [
            {
                "shot_id": sid,
                "rule_directive": f"outputs/director_ab/rule_v2/{sid}.json",
                "qwen_directive": f"outputs/director_ab/qwen/{sid}.json",
                "score_rule": None, "score_qwen": None, "comment": "",
            }
            for sid in review_ids
        ],
    }
    (out / "human_review_20.json").write_text(
        json.dumps(review, ensure_ascii=False, indent=2), encoding="utf-8")

    # Phase 11 entry condition check
    a_score = _normalized_avg(metrics_a)
    b_score = _normalized_avg(metrics_b)
    qwen_lead_pct = round((b_score / a_score - 1) * 100, 1) if a_score else 0.0
    phase11 = {
        "valid_rate_b_ge_99": metrics_b["valid_rate"] >= 0.99,
        "physics_b_zero": metrics_b["physics_violations"] == 0,
        "qwen_lead_pct_ge_10": qwen_lead_pct >= 10.0,
        "qwen_lead_pct": qwen_lead_pct,
        "ready": (metrics_b["valid_rate"] >= 0.99 and metrics_b["physics_violations"] == 0
                  and qwen_lead_pct >= 10.0),
    }

    summary = {
        "phase": "10.8-B",
        "shots": len(scenes),
        "metrics_a": metrics_a,
        "metrics_b": metrics_b,
        "comparison": compare(metrics_a, metrics_b),
        "phase11_entry": phase11,
        "human_review_20": str(out / "human_review_20.json"),
    }
    (out / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return summary


def _normalized_avg(metrics: dict) -> float:
    """Average of [0,1]-bounded director metrics (continuity via constraint cap)."""
    cons = min(float(metrics.get("avg_constraints", 0)) / 3.0, 1.0)
    return (float(metrics.get("valid_rate", 0)) + float(metrics.get("camera_diversity", 0)) +
            float(metrics.get("movement_quality", 0)) + float(metrics.get("emotion_span", 0)) +
            cons + float(metrics.get("character_intent_alignment", 0))) / 6.0

# ---------------------------------------------------------------------------
# Phase 10.8-B+: Director Mixture evaluation (uses generated manifests, no LLM)
# ---------------------------------------------------------------------------

RULE_TYPES = {"action", "world", "environment", "chase"}
LLM_TYPES = {"emotion", "dialogue", "revelation", "establish", "transition"}


def _policy_router():
    from backend.director.policy_router import DirectorRouter

    return DirectorRouter()


def mixture_pick(
    scene: dict,
    rule_directive: ShotDirective,
    llm_directive: ShotDirective,
    router=None,
) -> ShotDirective:
    """Pick the directive per the configurable router policy (Phase 10.8-C)."""
    scene_type = str(scene.get("scene_type") or (scene.get("section_context") or {}).get("scene_type") or "")
    router = router or _policy_router()
    if router.route_for(scene_type) == "rule":
        return rule_directive
    return llm_directive


def run_mixture_eval(
    scenes: list[dict],
    manifests_dir: str | Path,
    validator: ShotValidator | None = None,
) -> dict:
    """Evaluate the policy-driven mixture by recombining saved manifests.

    Returns {"metrics": ..., "directives": [...]} so callers can compute the
    entropy / alignment metrics without another LLM run.
    """
    from backend.director.policy_router import DirectorRouter

    manifests_dir = Path(manifests_dir)
    validator = validator or ShotValidator()
    router = DirectorRouter()
    directives_mix: list[ShotDirective] = []
    routed: dict[str, int] = {}
    for scene in scenes:
        sid = scene["shot"]["id"]
        rule_raw = json.loads((manifests_dir / "rule_v2" / f"{sid}.json").read_text(encoding="utf-8"))
        qwen_raw = json.loads((manifests_dir / "qwen" / f"{sid}.json").read_text(encoding="utf-8"))
        rule_d = _directive_from_manifest(rule_raw)
        qwen_d = _directive_from_manifest(qwen_raw)
        picked = mixture_pick(scene, rule_d, qwen_d, router)
        picked.continuity = dict(picked.continuity or {})
        scene_type = (scene.get("section_context") or {}).get("scene_type", "")
        route = router.route_for(scene_type)
        routed[route] = routed.get(route, 0) + 1
        directives_mix.append(picked)
    metrics = evaluate("C: mixture", scenes, directives_mix, validator)
    metrics["routed"] = routed
    return {"metrics": metrics, "directives": directives_mix}


def evaluate_mixture_from_manifests(manifests_dir: str | Path) -> dict:
    """Recompute mixture metrics from saved manifests (no LLM calls)."""
    scenes = load_100_shot_scenes()
    result = run_mixture_eval(scenes, manifests_dir)
    metrics_c = result["metrics"]
    metrics_c["director_entropy"] = director_entropy(result["directives"])
    metrics_c["character_intent_alignment"] = character_intent_alignment(scenes, result["directives"])
    return {
        "metrics_c": metrics_c,
        "comparison_c_vs_a": compare(metrics_c, _metrics_from_summary(manifests_dir, "metrics_a")),
        "comparison_c_vs_b": compare(metrics_c, _metrics_from_summary(manifests_dir, "metrics_b")),
    }


def _metrics_from_summary(manifests_dir: str | Path, key: str) -> dict:
    summary = json.loads((Path(manifests_dir) / "summary.json").read_text(encoding="utf-8"))
    return summary.get(key, {})


def _directive_from_manifest(raw: dict) -> ShotDirective:
    from backend.director.providers.base import build_directive
    from backend.story.models import Shot

    d = raw.get("directive", {})
    shot = Shot(id=raw.get("shot_id", ""), duration=6.0)
    return build_directive(
        shot,
        {
            "shot_id": raw.get("shot_id", ""),
            "shot_intent": d.get("shot_intent", ""),
            "camera": d.get("camera", {}),
            "lighting": d.get("lighting", {}),
            "emotion_curve": d.get("emotion_curve", []),
            "continuity": d.get("continuity", {}),
            "rationale": d.get("rationale", ""),
        },
        director_version=raw.get("director_version", "mixture"),
    )

if __name__ == "__main__":
    main()
