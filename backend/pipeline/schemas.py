"""Pipeline schemas for the v0.5 production pipeline."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional
from uuid import uuid4


class PipelineStage(str, Enum):
    EXTRACT_CHARACTERS = "extract_characters"
    PARSE_STORY = "parse_story"
    BUILD_GRAPH = "build_graph"
    DIRECTOR_PLAN = "director_plan"
    DIRECTOR_V2_PLAN = "director_v2_plan"   # Phase 10.2-A: Director v2 directives
    WRITER_ENHANCE = "writer_enhance"
    CHARACTER_CONTEXT = "character_context"
    CRITIC_REVIEW = "critic_review"
    COMPILE_PROMPTS = "compile_prompts"
    VISUAL_FEEDBACK = "visual_feedback"     # Sprint 7.1: Vision Critic + Feedback Loop
    COMPLETE = "complete"


@dataclass
class PipelineRequest:
    id: str = field(default_factory=lambda: uuid4().hex[:12])
    novel_id: str = ""
    title: str = ""
    text: str = ""             # raw novel text or chapter text
    chapters: list[str] = field(default_factory=list)  # split chapter texts
    target_chapters: list[int] = field(default_factory=list)
    skip_character_extraction: bool = False
    skip_story_parsing: bool = False
    template_name: str = "manga_page"
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())


@dataclass
class StageResult:
    stage: PipelineStage
    status: str = ""           # pending, running, completed, failed, skipped
    message: str = ""
    data: dict = field(default_factory=dict)
    duration_ms: float = 0.0
    completed_at: str = ""


@dataclass
class PipelineResponse:
    id: str = field(default_factory=lambda: uuid4().hex[:12])
    request_id: str = ""
    status: str = ""           # pending, running, completed, failed
    stages: list[StageResult] = field(default_factory=list)
    characters_found: int = 0
    scenes_parsed: int = 0
    shots_planned: int = 0
    prompts_compiled: int = 0
    directives: list[dict] = field(default_factory=list)  # Phase 10.2-A: ShotDirective JSON
    directive_sections: list[dict] = field(default_factory=list)  # Phase 10.2-A: StorySection summaries
    # Sprint 7.1: Vision feedback loop
    feedback_applied: int = 0
    feedback_actions: int = 0
    total_duration_ms: float = 0.0
    completed_at: str = ""
