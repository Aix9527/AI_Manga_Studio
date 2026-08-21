"""Director provider interface (Phase 10.7-B)."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from backend.agents.director_v2 import ShotDirective
from backend.story.models import Shot


class DirectorProvider(ABC):
    """A source of :class:`ShotDirective` decisions.

    Implementations must be deterministic-or-nothing: an LLM provider either
    returns a directive from structured JSON or raises ``ProviderError`` so
    the HybridDirector can fall back to the rule provider.
    """

    name: str = "base"

    @abstractmethod
    def generate_directive(
        self,
        shot: Shot,
        section_context: dict | None = None,
    ) -> ShotDirective:
        """Produce a directive for one shot from its story context."""
        raise NotImplementedError


class ProviderError(RuntimeError):
    """Raised when an LLM director provider fails (network/JSON/schema)."""


def build_directive(shot: Shot, data: dict[str, Any], *, director_version: str) -> ShotDirective:
    """Build a ShotDirective from parsed JSON with safe defaults for optional fields.

    Required fields (camera/lighting/emotion_curve/continuity) are kept
    exactly as returned so the validator can reject incomplete output.
    """
    return ShotDirective(
        shot_id=str(data.get("shot_id") or shot.id),
        shot_intent=str(data.get("shot_intent") or ""),
        camera=dict(data.get("camera") or {}),
        lighting=dict(data.get("lighting") or {}),
        emotion_curve=list(data.get("emotion_curve") or []),
        continuity=dict(data.get("continuity") or {}),
        rationale=str(data.get("rationale") or ""),
        directive_id=f"DIR-{shot.id}-v1",
        director_version=director_version,
        created_at=shot.created_at,
    )


# ---------------------------------------------------------------------------
# Shared LLM prompt / parsing helpers
# ---------------------------------------------------------------------------

DIRECTOR_SCHEMA_PROMPT = """You are a professional film director for AI manga drama (AI漫剧).
Given one shot and its story section context, output ONLY a strict JSON object
with EXACTLY this schema (no markdown, no commentary):

{
  "shot_id": "shot id string",
  "shot_intent": "one of establish_space|establish_world|context_action|dialogue_beat|emotional_beat|reveal_detail",
  "camera": {"angle": "eye-level|low-angle|high-angle|dutch|overhead|POV|aerial", "movement": "static|pan|tilt|dolly|tracking|push-in|pull-out|handheld|orbit|crane", "distance": "extreme-close-up|close-up|medium|long|wide|extreme-wide|establishing"},
  "lighting": {"style": "string", "key": "string", "temperature": "warm|cool|neutral|warm_gold|neutral_cool"},
  "emotion_curve": [{"t": seconds_from_shot_start, "emotion": "string", "intensity": 0.0_to_1.0}],
  "continuity": {"previous_shot": "shot id or empty", "constraints": ["string constraints for continuity/physics/characters"]},
  "rationale": "one-sentence justification"
}

Rules:
- t values must be monotonically increasing starting at 0 and never exceed the shot duration.
- intensity must be in [0, 1].
- camera movement must be physically plausible for the chosen distance (e.g. orbit/crane cannot be extreme-close-up).

CAMERA MOTION CONSTRAINTS (strict, obey the scene_type):
- action: require one of tracking | handheld | crane | dolly | push-in
- environment / world: require one of dolly | aerial push-in | orbit | pan
- dialogue: allow static | slow push-in | pan | tilt
- emotion: allow static | slow push-in | pull-out | handheld
- transition: allow static | whip-pan | dolly

CHARACTER BEHAVIOR CONSTRAINTS (strict):
- Match every declared character to its Bible role; never use forbidden behaviors.
- If character_bible is provided in the context, follow its allowed/forbidden lists exactly.
- Include every declared character id inside continuity.constraints (this is mandatory for alignment)."""

def _motion_requirement(scene_type: str) -> str:
    table = {
        "action": "tracking | handheld | crane | dolly | push-in",
        "environment": "dolly | aerial push-in | orbit | pan",
        "world": "dolly | aerial push-in | orbit | pan",
        "dialogue": "static | slow push-in | pan | tilt",
        "emotion": "static | slow push-in | pull-out | handheld",
        "transition": "static | whip-pan | dolly",
        "revelation": "static | slow push-in | dolly",
        "exploration": "static | slow push-in | dolly",
    }
    return table.get(str(scene_type or "").lower(), "static | slow push-in | pan | tilt | dolly")


def director_user_prompt(shot: Shot, section_context: dict | None) -> str:
    ctx = section_context or {}
    lines = [
        f"shot_id: {shot.id}",
        f"shot_type: {shot.shot_type or 'medium'}",
        f"camera_angle: {shot.camera_angle or 'eye-level'}",
        f"emotion: {shot.emotion or 'neutral'}",
        f"duration_seconds: {shot.duration}",
        f"characters: {', '.join(shot.character_ids) if shot.character_ids else 'none'}",
        f"description: {shot.description or shot.action or ''}",
    ]
    scene_type = str(ctx.get("scene_type") or "")
    if scene_type:
        lines.append(f"scene_type: {scene_type}")
        lines.append(f"camera_motion_requirement: {_motion_requirement(scene_type)}")
    if ctx.get("visual_theme"):
        lines.append(f"visual_theme: {ctx['visual_theme']}")
    if ctx.get("character_state"):
        lines.append(f"character_state: {ctx['character_state']}")
    if ctx.get("character_bible"):
        lines.append(f"character_bible: {ctx['character_bible']}")
    if ctx.get("emotion"):
        lines.append(f"section_emotion: {ctx['emotion']}")
    return "\n".join(lines)


def parse_directive_json(content: str, shot: Shot, *, director_version: str) -> ShotDirective:
    """Parse raw LLM output into a ShotDirective. Raises ProviderError on bad JSON."""
    import json

    text = (content or "").strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    try:
        data = json.loads(text)
    except Exception as exc:  # noqa: BLE001 - any parse failure falls back to rule
        raise ProviderError(f"LLM output is not valid JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise ProviderError("LLM output is not a JSON object")
    return build_directive(shot, data, director_version=director_version)
