
"""Storyboard domain aggregates."""

from dataclasses import dataclass, field
from datetime import datetime


@dataclass(slots=True)
class StoryboardScene:
    scene_id: str
    project_id: str
    narrative_scene_id: str | None
    sequence_number: int
    title: str = ""
    description: str = ""
    created_at: datetime = field(default_factory=lambda: datetime.utcnow())
    updated_at: datetime = field(default_factory=lambda: datetime.utcnow())
    revision: int = 1


@dataclass(slots=True)
class Shot:
    shot_id: str
    scene_id: str
    project_id: str
    shot_number: int
    description: str = ""
    framing: str = ""
    camera_angle: str = ""
    camera_motion: str = ""
    duration_seconds: float = 0.0
    dialog: str = ""
    frozen_snapshot_json: str = "{}"
    created_at: datetime = field(default_factory=lambda: datetime.utcnow())
    updated_at: datetime = field(default_factory=lambda: datetime.utcnow())
    revision: int = 1


@dataclass(slots=True)
class ShotCharacterBinding:
    shot_id: str
    character_id: str
    pose: str = ""
    expression: str = ""
    position: str = ""
    scale: str = ""
