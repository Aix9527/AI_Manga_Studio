
"""Character snapshot injection into prompts."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class CharacterSceneState:
    character_id: str
    narrative_scene_id: str
    wardrobe_variant_id: str | None = None
    expression: str | None = None
    physical_condition: tuple[str, ...] = ()
    held_items: tuple[str, ...] = ()
    temporary_traits: tuple[str, ...] = ()
    continuity_source_shot_id: str | None = None


@dataclass(frozen=True, slots=True)
class SubjectAction:
    actor_subject_id: str
    action: str
    target_subject_id: str | None = None
    intensity: str | None = None
    phase: str | None = None


@dataclass(frozen=True, slots=True)
class SubjectPromptScope:
    subject_id: str
    role: str
    screen_position: str | None
    nodes: tuple
