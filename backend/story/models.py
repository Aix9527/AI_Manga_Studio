"""Story data models for v0.5 Story Graph Engine."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional
from uuid import uuid4


@dataclass
class Chapter:
    id: str = field(default_factory=lambda: uuid4().hex[:12])
    novel_id: str = ""
    number: int = 0
    title: str = ""
    summary: str = ""
    raw_text: str = ""
    word_count: int = 0
    status: str = "draft"       # draft, outlined, written, polished, production
    scenes: list[str] = field(default_factory=list)  # scene IDs
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())


@dataclass
class Scene:
    id: str = field(default_factory=lambda: uuid4().hex[:12])
    chapter_id: str = ""
    number: int = 0
    title: str = ""
    summary: str = ""
    raw_text: str = ""
    location: str = ""
    time_of_day: str = ""
    mood: str = ""              # tense, calm, dramatic, comedic, dark, hopeful
    characters: list[str] = field(default_factory=list)
    shots: list[str] = field(default_factory=list)  # shot IDs
    tags: list[str] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())


@dataclass
class Shot:
    id: str = field(default_factory=lambda: uuid4().hex[:12])
    scene_id: str = ""
    index: int = 0
    shot_type: str = ""         # wide, medium, close-up, extreme-close-up, long, panorama
    camera_angle: str = ""      # eye-level, low-angle, high-angle, dutch, birds-eye, worms-eye
    camera_movement: str = "static"
    description: str = ""
    action: str = ""
    dialogue: str = ""
    narration: str = ""
    emotion: str = ""
    duration: float = 5.0
    panel_count: int = 1
    character_ids: list[str] = field(default_factory=list)
    prompt_hints: str = ""      # additional generation hints
    reference_images: list[str] = field(default_factory=list)
    positive_prompt: str = ""
    negative_prompt: str = ""
    seed: int = 0
    image_model: str = ""
    video_model: str = ""
    thumbnail_url: str = ""
    production_status: str = "pending"
    quality_status: str = "unreviewed"
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())


@dataclass
class StoryNode:
    """Graph node representing any narrative unit."""
    id: str = field(default_factory=lambda: uuid4().hex[:12])
    novel_id: str = ""
    node_type: str = ""         # chapter, scene, shot, decision_point, branch
    data_id: str = ""           # FK to Chapter/Scene/Shot
    title: str = ""
    summary: str = ""
    parent_id: str = ""
    children: list[str] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)


@dataclass
class StoryGraph:
    id: str = field(default_factory=lambda: uuid4().hex[:12])
    novel_id: str = ""
    title: str = ""
    nodes: dict[str, StoryNode] = field(default_factory=dict)
    edges: list[tuple[str, str]] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())


@dataclass
class TimelineEvent:
    id: str = field(default_factory=lambda: uuid4().hex[:12])
    novel_id: str = ""
    chapter_number: int = 0
    character_id: str = ""
    event_type: str = ""        # appearance, action, revelation, death, transformation, flashback
    description: str = ""
    relative_time: str = ""     # e.g. "chapter 3, page 5"
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())


@dataclass
class Timeline:
    novel_id: str = ""
    events: list[TimelineEvent] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "novel_id": self.novel_id,
            "events": [e.__dict__ for e in self.events],
        }
