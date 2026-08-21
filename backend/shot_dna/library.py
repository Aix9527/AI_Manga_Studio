"""Shot DNA Library (Phase 13.1, GPT spec).

Reusable shot-experience patterns (camera / lens / lighting / emotion /
composition) proven by past production. Categories: action / dialogue /
emotion / reveal / climax / transition. Every entry tracks success_rate
and usage_count so the director retrieves the most proven shot language.
"""

from __future__ import annotations

import json
import threading
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


@dataclass
class ShotDNA:
    id: str
    category: str                    # action | dialogue | emotion | reveal | climax | transition
    scene: str = ""
    camera: dict = field(default_factory=dict)      # {type, angle, movement}
    lens: str = ""
    lighting: str = ""
    composition: str = ""
    emotion: str = ""                # e.g. curiosity→fear
    style: str = ""
    tags: list[str] = field(default_factory=list)
    prompt_template: str = ""
    success_rate: float = 0.8
    usage_count: int = 0
    created_at: str = field(default_factory=_now)
    updated_at: str = field(default_factory=_now)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "ShotDNA":
        known = {f.name for f in cls.__dataclass_fields__.values()}
        return cls(**{k: v for k, v in data.items() if k in known})


CATEGORIES = ["action", "dialogue", "emotion", "reveal", "climax", "transition"]


def _seed() -> list[ShotDNA]:
    rows: list[dict] = [
        # ------------------------------------------------------------ reveal
        {"id": "reveal_ancient_secret_001", "category": "reveal", "scene": "exploration", "camera": {"type": "medium", "angle": "low", "movement": "slow_push"}, "lens": "35mm", "lighting": "low_key", "composition": "subject centered, silhouette", "emotion": "curiosity→fear", "style": "cinematic", "tags": ["ancient", "secret", "discovery"], "success_rate": 0.91, "usage_count": 152},
        {"id": "reveal_identity_002", "category": "reveal", "scene": "dialogue", "camera": {"type": "close_up", "angle": "eye", "movement": "static"}, "lens": "85mm", "lighting": "rim", "composition": "face in shadow half-lit", "emotion": "shock→recognition", "style": "noir", "tags": ["identity", "face", "secret"], "success_rate": 0.89, "usage_count": 131},
        {"id": "reveal_power_003", "category": "reveal", "scene": "battle", "camera": {"type": "wide", "angle": "high", "movement": "crane_down"}, "lens": "24mm", "lighting": "backlight_blast", "composition": "power erupting, debris", "emotion": "awe→dread", "style": "spectacle", "tags": ["power", "awakening", "explosion"], "success_rate": 0.87, "usage_count": 98},
        # ------------------------------------------------------------ action
        {"id": "action_chase_001", "category": "action", "scene": "city_street", "camera": {"type": "long", "angle": "low", "movement": "dolly_forward"}, "lens": "28mm", "lighting": "neon", "composition": "runner framed left, motion blur", "emotion": "panic→determination", "style": "cyberpunk", "tags": ["chase", "run", "street"], "success_rate": 0.86, "usage_count": 176},
        {"id": "action_fight_002", "category": "action", "scene": "battle", "camera": {"type": "medium", "angle": "dutch", "movement": "handheld"}, "lens": "35mm", "lighting": "strobe", "composition": "two combatants, slash lines", "emotion": "fury→focus", "style": "martial", "tags": ["fight", "blade", "impact"], "success_rate": 0.84, "usage_count": 143},
        {"id": "action_escape_003", "category": "action", "scene": "ruins", "camera": {"type": "wide", "angle": "high", "movement": "tilt_down"}, "lens": "18mm", "lighting": "moonlight", "composition": "figure tiny under collapsing structure", "emotion": "terror→survival", "style": "epic", "tags": ["escape", "collapse", "ruins"], "success_rate": 0.83, "usage_count": 87},
        {"id": "action_sneak_004", "category": "action", "scene": "corridor", "camera": {"type": "close_up", "angle": "eye", "movement": "tracking"}, "lens": "50mm", "lighting": "practical", "composition": "shadow hugging wall", "emotion": "tension→focus", "style": "thriller", "tags": ["stealth", "corridor", "shadow"], "success_rate": 0.82, "usage_count": 64},
        # ------------------------------------------------------------ dialogue
        {"id": "dialogue_confrontation_001", "category": "dialogue", "scene": "throne_room", "camera": {"type": "close_up", "angle": "low", "movement": "slow_push"}, "lens": "50mm", "lighting": "hard_top", "composition": "two-shot over shoulder", "emotion": "anger→resolve", "style": "historical", "tags": ["confrontation", "duel_of_words"], "success_rate": 0.88, "usage_count": 121},
        {"id": "dialogue_secret_002", "category": "dialogue", "scene": "night_cafe", "camera": {"type": "medium", "angle": "eye", "movement": "static"}, "lens": "35mm", "lighting": "warm_practical", "composition": "table two-shot, shallow depth", "emotion": "intimacy→betrayal", "style": "slice_of_life", "tags": ["secret", "whisper", "cafe"], "success_rate": 0.85, "usage_count": 95},
        {"id": "dialogue_negotiation_003", "category": "dialogue", "scene": "office", "camera": {"type": "medium", "angle": "high", "movement": "static"}, "lens": "40mm", "lighting": "fluorescent", "composition": "symmetric desk shot", "emotion": "cold→calculation", "style": "corporate", "tags": ["negotiation", "deal"], "success_rate": 0.81, "usage_count": 58},
        # ------------------------------------------------------------ emotion
        {"id": "emotion_sorrow_001", "category": "emotion", "scene": "rain_street", "camera": {"type": "close_up", "angle": "eye", "movement": "slow_dolly_back"}, "lens": "85mm", "lighting": "cold_blue", "composition": "face wet with rain, empty street", "emotion": "grief→isolation", "style": "melancholic", "tags": ["sad", "rain", "lonely"], "success_rate": 0.9, "usage_count": 134},
        {"id": "emotion_joy_002", "category": "emotion", "scene": "courtyard", "camera": {"type": "medium", "angle": "low", "movement": "handheld"}, "lens": "35mm", "lighting": "golden_hour", "composition": "subject laughing, light flares", "emotion": "relief→joy", "style": "bright", "tags": ["smile", "warmth"], "success_rate": 0.87, "usage_count": 108},
        {"id": "emotion_fear_003", "category": "emotion", "scene": "dark_corridor", "camera": {"type": "close_up", "angle": "high", "movement": "push_in"}, "lens": "50mm", "lighting": "flicker", "composition": "eyes wide, breathing hard", "emotion": "fear→panic", "style": "horror", "tags": ["fear", "dark", "tension"], "success_rate": 0.86, "usage_count": 92},
        {"id": "emotion_determination_004", "category": "emotion", "scene": "cliff", "camera": {"type": "medium", "angle": "low", "movement": "static"}, "lens": "35mm", "lighting": "dawn", "composition": "figure facing horizon, wind", "emotion": "despair→resolve", "style": "epic", "tags": ["resolve", "dawn", "oath"], "success_rate": 0.84, "usage_count": 79},
        # ------------------------------------------------------------ climax
        {"id": "climax_final_blow_001", "category": "climax", "scene": "battlefield", "camera": {"type": "wide", "angle": "low", "movement": "crash_zoom"}, "lens": "24mm", "lighting": "storm", "composition": "two figures, energy clash center", "emotion": "fury→victory", "style": "spectacle", "tags": ["final_battle", "clash"], "success_rate": 0.88, "usage_count": 116},
        {"id": "climax_sacrifice_002", "category": "climax", "scene": "altar", "camera": {"type": "close_up", "angle": "high", "movement": "slow_pull_back"}, "lens": "50mm", "lighting": "god_ray", "composition": "hand reaching, light breaking", "emotion": "sorrow→grace", "style": "sacred", "tags": ["sacrifice", "light"], "success_rate": 0.89, "usage_count": 74},
        {"id": "climax_reversal_003", "category": "climax", "scene": "arena", "camera": {"type": "medium", "angle": "eye", "movement": "whip_pan"}, "lens": "35mm", "lighting": "spotlight", "composition": "sudden shift, crowd gasp", "emotion": "despair→shock→triumph", "style": "sports_drama", "tags": ["reversal", "comeback"], "success_rate": 0.85, "usage_count": 67},
        # ------------------------------------------------------------ transition
        {"id": "transition_time_jump_001", "category": "transition", "scene": "crossroads", "camera": {"type": "wide", "angle": "birds_eye", "movement": "orbit"}, "lens": "20mm", "lighting": "day_to_night", "composition": "same spot, changing seasons", "emotion": "nostalgia→forward", "style": "montage", "tags": ["time", "passing", "montage"], "success_rate": 0.83, "usage_count": 61},
        {"id": "transition_location_002", "category": "transition", "scene": "any", "camera": {"type": "medium", "angle": "eye", "movement": "match_cut"}, "lens": "35mm", "lighting": "matched", "composition": "match cut between locations", "emotion": "continuity", "style": "flow", "tags": ["match_cut", "travel"], "success_rate": 0.82, "usage_count": 55},
        {"id": "transition_emotional_003", "category": "transition", "scene": "any", "camera": {"type": "close_up", "angle": "eye", "movement": "iris_out"}, "lens": "85mm", "lighting": "fade", "composition": "face fading to memory", "emotion": "bittersweet", "style": "nostalgic", "tags": ["memory", "fade"], "success_rate": 0.81, "usage_count": 48},
    ]
    return [ShotDNA(**row) for row in rows]


class ShotDNALibrary:
    def __init__(self, path: str | Path = "storage/shot_dna/library.json"):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._data: dict[str, dict] = self._load()

    def _load(self) -> dict:
        if not self.path.exists():
            data = {dna.id: dna.to_dict() for dna in _seed()}
            self.path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
            return data
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            return {}

    def _save(self) -> None:
        with self._lock:
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps(self._data, ensure_ascii=False, indent=2), encoding="utf-8")
            tmp.replace(self.path)

    def all(self) -> list[ShotDNA]:
        with self._lock:
            return [ShotDNA.from_dict(raw) for raw in self._data.values()]

    def by_category(self, category: str) -> list[ShotDNA]:
        return [dna for dna in self.all() if dna.category == category]

    def get(self, dna_id: str) -> ShotDNA | None:
        with self._lock:
            raw = self._data.get(dna_id)
        return ShotDNA.from_dict(raw) if raw else None

    def add(self, dna: ShotDNA) -> ShotDNA:
        with self._lock:
            self._data[dna.id] = dna.to_dict()
            self._save()
        return dna

    def add_from_dict(self, data: dict) -> ShotDNA:
        data = dict(data)
        data.setdefault("id", "")
        dna = ShotDNA.from_dict(data)
        if not dna.id:
            dna.id = f"dna_{uuid.uuid4().hex[:8]}"
        return self.add(dna)

    def apply_feedback_stats(
        self,
        dna_id: str,
        *,
        success_count: int,
        usage_count: int,
        quality_sum: float = 0.0,
        human_score_sum: float = 0.0,
        prior_weight: int = 5,
    ) -> None:
        """Apply a human-approved feedback promotion (Phase 13.4-C).

        Recomputes success_rate from the accumulated statistical basis with
        a prior weight, then merges usage counts. The raw stats remain in the
        feedback store for audit; this is the audited promotion step.
        """
        with self._lock:
            raw = self._data.get(dna_id)
            if not raw:
                raise KeyError(f"shot dna not found: {dna_id}")
            prior = float(raw.get("success_rate", 0.8))
            total_usage = int(raw.get("usage_count", 0)) + int(usage_count)
            if int(usage_count) > 0:
                smoothed = (prior * prior_weight + float(success_count)) / (prior_weight + float(usage_count))
                raw["success_rate"] = round(min(1.0, max(0.0, smoothed)), 3)
            raw["usage_count"] = total_usage
            raw["updated_at"] = _now()
            self._save()

    def register_use(self, dna_id: str, success: bool | None = None) -> None:
        with self._lock:
            raw = self._data.get(dna_id)
            if not raw:
                return
            raw["usage_count"] = int(raw.get("usage_count", 0)) + 1
            if success is not None:
                current = float(raw.get("success_rate", 0.8))
                uses = int(raw.get("usage_count", 1))
                raw["success_rate"] = round((current * (uses - 1) + (1.0 if success else 0.0)) / uses, 3)
            raw["updated_at"] = _now()
            self._save()

    def stats(self) -> dict:
        items = self.all()
        by_category: dict[str, int] = {}
        for dna in items:
            by_category[dna.category] = by_category.get(dna.category, 0) + 1
        return {
            "total": len(items),
            "by_category": by_category,
            "avg_success_rate": round(sum(d.success_rate for d in items) / len(items), 3) if items else 0.0,
            "total_usage": sum(d.usage_count for d in items),
        }
