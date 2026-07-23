
"""Narrative domain - StoryDocument & NarrativeScene."""

from dataclasses import dataclass, field
from datetime import datetime


@dataclass(slots=True)
class StoryDocument:
    story_id: str
    project_id: str
    title: str
    content: str
    created_at: datetime = field(default_factory=lambda: datetime.utcnow())
    updated_at: datetime = field(default_factory=lambda: datetime.utcnow())
    revision: int = 1


@dataclass(slots=True)
class NarrativeScene:
    scene_id: str
    project_id: str
    story_id: str
    sequence_number: int
    title: str = ""
    description: str = ""
    location: str = ""
    time_of_day: str = ""
    mood: str = ""
    created_at: datetime = field(default_factory=lambda: datetime.utcnow())
    updated_at: datetime = field(default_factory=lambda: datetime.utcnow())
    revision: int = 1
