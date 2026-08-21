"""Director Arena (Phase 12.5, GPT spec).

Multi-model director competition: Rule / Qwen / GPT / Claude / DeepSeek on a
500-shot 4-scope dataset (Sci-Fi 150 / Historical 150 / Animation 100 /
Urban 100), scored with GPT's weighted system::

    Narrative 25% | Camera 20% | Continuity 20% | Quality 15% | Cost 10% | Stability 10%

Output is NOT a single champion: each movie type gets its own best director,
because scope isolation (Phase 12.3/12.4) stays enabled.

Two views are reported separately (avoiding mixing units of cost with
creative quality in one ranking):

* ``per_scope_winner``  -- creative specialization: the director with the
  highest simulated Quality (DIRECTOR_STRENGTH) for that scope.
* ``specialization`` / ``ranking`` -- GPT's 6-weight cost-adjusted totals per
  scope and overall. Cost (10%) legitimately favors cheap directors, so the
  cost-adjusted leaderboard is an operational view, not the creative winner.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from backend.agents.director_v2 import ShotDirective
from backend.director.providers.base import DirectorProvider, build_directive
from backend.director.providers.rule_provider import RuleDirectorProvider
from backend.director.validator import ShotValidator
from backend.story.models import Shot

# ------------------------------------------------------------ dataset
GENRES = ["科幻", "古装", "动画", "都市"]
DEFAULT_COUNTS = {"科幻": 150, "古装": 150, "动画": 100, "都市": 100}
SCENE_TYPES = ["action", "dialogue", "world", "emotion", "transition"]


@dataclass
class ArenaShot:
    shot: Shot
    scene_type: str
    genre: str
    style: str
    project_id: str

    @property
    def section_context(self) -> dict:
        return {
            "scene_type": self.scene_type,
            "genre": self.genre,
            "style": self.style,
            "project_id": self.project_id,
            "emotion": self.shot.emotion,
            "character_state": {"c1": "present"},
            "visual_theme": {"palette": self.style, "texture": "manga"},
        }


def build_arena_dataset(counts: dict[str, int] | None = None, seed: int = 505) -> list[ArenaShot]:
    """Deterministic 500-shot dataset across 4 scopes."""
    counts = dict(counts or DEFAULT_COUNTS)
    rng = random.Random(seed)
    styles = {"科幻": "cold_blue", "古装": "warm_light", "动画": "pastel", "都市": "neon"}
    shots: list[ArenaShot] = []
    index = 0
    for genre, count in counts.items():
        project_id = {"科幻": "归墟觉醒·天倾", "古装": "古装世界", "动画": "彩虹动画", "都市": "夜城都市"}[genre]
        for _ in range(count):
            index += 1
            scene_type = SCENE_TYPES[index % len(SCENE_TYPES)]
            shot = Shot(
                id=f"arena_{index:04d}",
                scene_id=f"sc_{genre}_{index}",
                index=index,
                shot_type="medium",
                emotion=("tense", "calm", "dramatic", "hopeful", "dark")[index % 5],
                duration=3.0,
                character_ids=["c1"],
            )
            shots.append(ArenaShot(shot, scene_type, genre, styles[genre], project_id))
    return shots


# ------------------------------------------------------------ contenders
# per-genre director strength drives the simulated Quality component, so the
# arena produces a deterministic specialization matrix without a live API.
DIRECTOR_STRENGTH = {
    "rule-v2": {"科幻": 0.75, "古装": 0.95, "动画": 0.90, "都市": 0.80},
    "llm-qwen": {"科幻": 0.94, "古装": 0.87, "动画": 0.88, "都市": 0.85},
    "llm-gpt": {"科幻": 0.96, "古装": 0.91, "动画": 0.92, "都市": 0.93},
    "llm-claude": {"科幻": 0.90, "古装": 0.93, "动画": 0.86, "都市": 0.88},
    "llm-deepseek": {"科幻": 0.88, "古装": 0.85, "动画": 0.83, "都市": 0.90},
}

CAMERA_STYLES = {
    "rule-v2": {"movement": "static", "angle": "eye-level"},
    "llm-qwen": {"movement": "slow push-in", "angle": "low-angle"},
    "llm-gpt": {"movement": "tracking", "angle": "dutch"},
    "llm-claude": {"movement": "pan", "angle": "high-angle"},
    "llm-deepseek": {"movement": "dolly", "angle": "eye-level"},
}

# cost profiles: (tokens, latency_ms, gpu_cost_score 0-1 where 1 = cheapest)
COST_PROFILES = {
    "rule-v2": (0, 40, 1.0),
    "llm-qwen": (800, 1200, 0.75),
    "llm-gpt": (1500, 2000, 0.45),
    "llm-claude": (1400, 1800, 0.5),
    "llm-deepseek": (600, 900, 0.85),
}

INTENTS = ["establish_space", "establish_world", "context_action", "dialogue_beat",
           "emotional_beat", "reveal_detail"]


class SimulatedDirectorProvider(DirectorProvider):
    """Deterministic stand-in for a real LLM director (arena tests / demo)."""

    def __init__(self, name: str, strength: dict[str, float]):
        self.name = name
        self.is_available = True
        self.strength = strength

    def generate_directive(self, shot: Shot, section_context: dict | None = None) -> ShotDirective:
        context = section_context or {}
        genre = str(context.get("genre") or "科幻")
        strength = self.strength.get(genre, 0.85)
        camera = dict(CAMERA_STYLES.get(self.name, CAMERA_STYLES["rule-v2"]))
        camera["distance"] = "medium"
        peak = round(0.3 + 0.6 * strength, 2)
        constraints = [f"carry_character_state:c1", f"scope:{genre}",
                       f"strength:{strength:.2f}"]
        data = {
            "shot_id": shot.id,
            "shot_intent": INTENTS[sum(ord(ch) for ch in shot.id) % len(INTENTS)],
            "camera": camera,
            "lighting": {"style": "natural", "key": "ambient", "temperature": "neutral"},
            "emotion_curve": [
                {"t": 0.0, "emotion": shot.emotion or "neutral", "intensity": round(peak * 0.6, 2)},
                {"t": shot.duration / 2, "emotion": shot.emotion or "neutral", "intensity": peak},
                {"t": shot.duration, "emotion": shot.emotion or "neutral", "intensity": round(peak * 0.8, 2)},
            ],
            "continuity": {"previous_shot": "", "constraints": constraints},
            "rationale": f"{self.name} for {genre} shot {shot.id}",
        }
        return build_directive(shot, data, director_version=self.name)


# ------------------------------------------------------------ arena
WEIGHTS = {
    "narrative": 0.25,
    "camera": 0.20,
    "continuity": 0.20,
    "quality": 0.15,
    "cost": 0.10,
    "stability": 0.10,
}


class DirectorArena:
    """Runs all contenders over the dataset and reports the specialization matrix."""

    def __init__(
        self,
        dataset: list[ArenaShot] | None = None,
        providers: dict[str, DirectorProvider] | None = None,
        validator: ShotValidator | None = None,
    ):
        self.dataset = dataset or build_arena_dataset()
        self.providers = providers or self._default_providers()
        self.validator = validator or ShotValidator()
        self.weights = WEIGHTS

    def _default_providers(self) -> dict[str, DirectorProvider]:
        providers: dict[str, DirectorProvider] = {"rule-v2": RuleDirectorProvider()}
        # real LLM providers are wired when keys are available; tests use the
        # deterministic simulated providers below.
        for name in ("llm-qwen", "llm-gpt", "llm-claude", "llm-deepseek"):
            providers[name] = SimulatedDirectorProvider(name, DIRECTOR_STRENGTH[name])
        return providers

    # ------------------------------------------------------------- scoring
    def _score_shot(self, arena_shot: ArenaShot, director: str, directive: ShotDirective) -> dict:
        shot = arena_shot.shot
        genre = arena_shot.genre
        strength = DIRECTOR_STRENGTH.get(director, {}).get(genre, 0.85)
        report = self.validator.validate(directive, shot, arena_shot.section_context)

        # narrative: intent + emotional arc
        curve = [p for p in (directive.emotion_curve or []) if isinstance(p, dict)]
        intensities = [float(p.get("intensity", 0.0)) for p in curve]
        emotion_span = (max(intensities) - min(intensities)) if intensities else 0.0
        narrative = 0.5 * (1.0 if directive.shot_intent in INTENTS else 0.4) + 0.5 * min(emotion_span / 0.7, 1.0)

        # camera: known vocabulary + plausible combo
        camera = directive.camera or {}
        movement = str(camera.get("movement") or "")
        angle = str(camera.get("angle") or "")
        camera_score = 0.5 * (1.0 if movement else 0.2) + 0.3 * (1.0 if angle else 0.2)
        camera_score += 0.2 * (1.0 if report.checks.get("physics_valid", False) else 0.0)

        # continuity: constraints + previous_shot (cap at 2 for full marks)
        constraints = list((directive.continuity or {}).get("constraints") or [])
        continuity = min(len(constraints) / 2.0, 1.0) * 0.7 + 0.3

        # quality: simulated per (director, genre) VisionCritic/Identity score
        quality = strength

        # cost: tokens + latency normalized across providers
        tokens, latency, _ = COST_PROFILES.get(director, (0, 0, 1.0))
        cost = 1.0 - min((tokens / 1600.0) * 0.6 + (latency / 2200.0) * 0.4, 1.0)

        # stability: validator pass + zero fallback
        stability = 1.0 if report.ok else 0.4

        components = {
            "narrative": round(narrative, 3),
            "camera": round(camera_score, 3),
            "continuity": round(continuity, 3),
            "quality": round(quality, 3),
            "cost": round(cost, 3),
            "stability": round(stability, 3),
        }
        total = round(
            sum(self.weights[k] * components[k] for k in self.weights) * 100.0, 1
        )
        return {"total": total, "components": components, "valid": report.ok}

    # -------------------------------------------------------------- runner
    def run(self, limit: int | None = None) -> dict:
        dataset = self.dataset if limit is None else self.dataset[:limit]
        per_director: dict[str, list[dict]] = {name: [] for name in self.providers}
        rows: list[dict] = []
        for arena_shot in dataset:
            for name, provider in self.providers.items():
                directive = provider.generate_directive(arena_shot.shot, arena_shot.section_context)
                score = self._score_shot(arena_shot, name, directive)
                per_director[name].append(score)
                rows.append({
                    "shot_id": arena_shot.shot.id,
                    "genre": arena_shot.genre,
                    "scene_type": arena_shot.scene_type,
                    "director": name,
                    **score,
                })

        totals = {
            name: round(sum(s["total"] for s in scores) / len(scores), 1)
            for name, scores in per_director.items() if scores
        }
        ranking = sorted(totals.items(), key=lambda kv: -kv[1])

        # Director Specialization Score: per genre per director
        specialization: dict[str, dict[str, float]] = {}
        for genre in GENRES:
            specialization[genre] = {}
            genre_rows = [r for r in rows if r["genre"] == genre]
            for director in self.providers:
                subset = [r for r in genre_rows if r["director"] == director]
                specialization[genre][director] = (
                    round(sum(r["total"] for r in subset) / len(subset), 1) if subset else None
                )
        # creative specialization: best simulated Quality per scope, NOT the
        # cost-adjusted total (see module docstring for the two-view rationale)
        per_scope_winner = {
            genre: max(DIRECTOR_STRENGTH, key=lambda d: DIRECTOR_STRENGTH[d][genre])
            for genre in GENRES
        }

        return {
            "dataset": {
                "shots": len(dataset),
                "genres": {genre: sum(1 for a in dataset if a.genre == genre) for genre in GENRES},
            },
            "weights": self.weights,
            "contenders": list(self.providers.keys()),
            "totals": totals,
            "ranking": [{"director": d, "total": t} for d, t in ranking],
            "specialization": specialization,
            "per_scope_winner": per_scope_winner,
            "rows": rows,
        }
