from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Literal


class InputType(str, Enum):
    NOVEL = "novel"
    SCRIPT = "script"
    STORYBOARD = "storyboard"
    UNKNOWN = "unknown"


@dataclass
class InputContract:
    path: str
    type: InputType
    title: str = ""
    author: str = ""
    chapter_count: int = 0
    total_words: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class Chapter:
    index: int
    title: str
    content: str = ""
    word_count: int = 0


@dataclass
class LoadedInput:
    contract: InputContract
    text: str
    chapters: list[Chapter] = field(default_factory=list)


@dataclass
class ShotSpec:
    id: str
    shot_number: int
    description: str
    duration: float = 5.0
    camera: str = ""
    characters: list[str] = field(default_factory=list)
    dialogue: list[str] = field(default_factory=list)
    sfx: list[str] = field(default_factory=list)
    positive_prompt: str = ""
    negative_prompt: str = ""
    narration: str = ""
    transition: str = "fade"
    seed: int = 0
    motion_level: int = 1  # 0 静态 / 1 微表情 / 2 人物动作 / 3 镜头运动 / 4 复杂动作


@dataclass
class ProductionPlan:
    project_id: str
    input_contract: InputContract
    chapters: list[Chapter] = field(default_factory=list)
    shots: list[ShotSpec] = field(default_factory=list)
    total_duration: float = 0.0
    settings: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class DialogueLine:
    """A single approved script line shared by audio and subtitle stages."""

    speaker: str
    text: str
    version_id: str = ""


@dataclass(frozen=True)
class ShotPlan:
    """Immutable, source-grounded plan for one generatable shot."""

    id: str
    sequence: int
    scene_id: str
    source_excerpt: str
    narrative_purpose: str
    duration_seconds: float
    continuity: Literal[
        "same_action", "same_character_new_scene", "time_jump", "location_jump"
    ]
    inherit_tail: bool
    prompt: str
    negative_prompt: str
    dialogue: tuple[DialogueLine, ...] = ()
    narration: str = ""
    ambience_prompt: str = ""


@dataclass(frozen=True)
class ScenePlan:
    """A versioned narrative scene grouping one or more immutable shots."""

    id: str
    chapter_index: int
    source_excerpt: str
    narrative_purpose: str
    shots: tuple[ShotPlan, ...]


@dataclass(frozen=True)
class ChapterPlanBundle:
    """Immutable chapter-plan artifact used by the novel-video domain."""

    plan_version: str
    source_sha256: str
    chapter_indexes: tuple[int, ...]
    target_seconds: float
    suggested_shot_count: int
    scenes: tuple[ScenePlan, ...]
    shots: tuple[ShotPlan, ...]
    # These are assigned by the formal service after planning.  Keeping them
    # in the immutable contract binds a plan to the exact imported source and
    # parameters that produced it.
    source_asset_version_id: str = ""
    plan_id: str = ""
    max_shots: int | None = None


@dataclass(frozen=True)
class NovelImportResult:
    """Traceable result of decoding a user supplied novel without editing it."""

    loaded: LoadedInput
    encoding: str
    sha256: str
    copied_path: Path
    asset: Any
