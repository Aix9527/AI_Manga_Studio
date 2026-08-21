from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from backend.story.models import Shot


@dataclass
class ShotDirective:
    """Director v2 production directive for one shot (BigBanana-inspired).

    Extends the legacy DirectorAgent brief with camera language, lighting,
    an emotion curve and explicit continuity constraints.
    """
    shot_id: str
    shot_intent: str = ""
    camera: dict = field(default_factory=dict)          # angle / movement / distance
    lighting: dict = field(default_factory=dict)        # style / key / temperature
    emotion_curve: list[dict] = field(default_factory=list)  # [{t, emotion, intensity}]
    continuity: dict = field(default_factory=dict)      # previous_shot / constraints
    rationale: str = ""
    directive_id: str = ""            # e.g. DIR-gx081-v1 (traceability)
    director_version: str = "rule-v2" # rule-v2 | llm-* (A/B + evolution)
    source_memory_hash: str = ""      # stable hash of section memory context
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())


_INTENT_BY_TYPE = {
    "wide": "establish_space",
    "panorama": "establish_world",
    "long": "context_action",
    "medium": "dialogue_beat",
    "close-up": "emotional_beat",
    "extreme-close-up": "reveal_detail",
}
_DEFAULT_CAMERA = {"angle": "eye-level", "movement": "static", "distance": "medium"}
_LIGHTING_BY_MOOD = {
    "dark": {"style": "low_key", "key": "single_source", "temperature": "cool"},
    "tense": {"style": "hard_contrast", "key": "practical", "temperature": "neutral"},
    "calm": {"style": "soft", "key": "diffuse", "temperature": "warm"},
    "hopeful": {"style": "soft_glow", "key": "backlight", "temperature": "warm_gold"},
    "dramatic": {"style": "chiaroscuro", "key": "rim", "temperature": "neutral_cool"},
}
_EMOTION_RAMP = {"calm": 0.3, "tense": 0.7, "dramatic": 0.9, "hopeful": 0.6, "dark": 0.8, "neutral": 0.5}


class DirectorV2Agent:
    """Director Agent v2: shot intent + camera + lighting + emotion + continuity.

    Rule-based first version, deterministic for tests; the same interface can
    later be backed by an LLM while keeping ShotDirective as the contract.
    """

    def plan_shot(self, shot: Shot, section_context: dict | None = None) -> ShotDirective:
        section_context = section_context or {}
        intent = _INTENT_BY_TYPE.get(shot.shot_type, "dialogue_beat")
        camera = {
            "angle": shot.camera_angle or _DEFAULT_CAMERA["angle"],
            "movement": shot.camera_movement or _DEFAULT_CAMERA["movement"],
            "distance": shot.shot_type or _DEFAULT_CAMERA["distance"],
        }
        lighting = dict(_LIGHTING_BY_MOOD.get(shot.emotion or "", {"style": "natural", "key": "ambient", "temperature": "neutral"}))
        if section_context.get("visual_theme"):
            lighting["palette"] = section_context["visual_theme"].get("palette", "")
            lighting["theme_texture"] = section_context["visual_theme"].get("texture", "")
        base = _EMOTION_RAMP.get(shot.emotion or "", 0.5)
        dur = max(shot.duration, 1.0)
        emotion_curve = [
            {"t": 0.0, "emotion": shot.emotion or "neutral", "intensity": round(base * 0.7, 2)},
            {"t": round(dur * 0.5, 2), "emotion": shot.emotion or "neutral", "intensity": round(base, 2)},
            {"t": round(dur, 2), "emotion": shot.emotion or "neutral", "intensity": round(base * 0.8, 2)},
        ]
        constraints = []
        if section_context.get("character_state"):
            constraints.append("carry_character_state:" + ",".join(sorted(section_context["character_state"].keys())[:6]))
        if section_context.get("visual_theme"):
            constraints.append("palette:" + section_context["visual_theme"].get("palette", "neutral"))
        if shot.reference_images:
            constraints.append("reference_images:" + str(len(shot.reference_images)))
        memory_hash = _memory_hash(section_context)
        return ShotDirective(
            shot_id=shot.id,
            shot_intent=intent,
            directive_id=f"DIR-{shot.id}-v1",
            director_version="rule-v2",
            source_memory_hash=memory_hash,
            camera=camera,
            lighting=lighting,
            emotion_curve=emotion_curve,
            continuity={"previous_shot": "", "constraints": constraints},
            rationale=f"type={shot.shot_type};emotion={shot.emotion or 'neutral'};theme={section_context.get('visual_theme', {}).get('palette', '')}",
        )

    def plan_sequence(
        self,
        shots: list[Shot],
        sections: list | None = None,
    ) -> list[ShotDirective]:
        """Plan a shot list, threading previous_shot continuity and section memory."""
        sections = sections or []
        section_by_scene = {s.scene_id: s for s in sections}
        directives: list[ShotDirective] = []
        prev_id = ""
        for shot in shots:
            ctx = {}
            sec = section_by_scene.get(shot.scene_id)
            if sec is not None:
                ctx = {
                    "character_state": sec.character_state,
                    "visual_theme": sec.visual_theme,
                    "emotion": sec.emotion,
                }
            d = self.plan_shot(shot, ctx)
            d.continuity["previous_shot"] = prev_id
            directives.append(d)
            prev_id = shot.id
        return directives

def _memory_hash(section_context: dict | None) -> str:
    """Stable short hash of the section-memory inputs that shaped the shot.

    Lets future A/B runs see *why* a directive was designed the way it was
    (character_state / visual_theme / emotion all feed the directive).
    """
    import hashlib
    import json

    if not section_context:
        return ""
    blob = json.dumps(
        section_context, ensure_ascii=False, sort_keys=True, default=str
    )
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:8]

