from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any


class H3Mode(str, Enum):
    T2VA = "T2VA"
    I2VA = "I2VA"
    FL2VA = "FL2VA"
    L2VA = "L2VA"
    REF2VA = "Ref2VA"


class H3ImageRole(str, Enum):
    CHARACTER_IDENTITY = "character_identity"
    SECONDARY_CHARACTER = "secondary_character"
    LOCATION = "location"
    COSTUME = "costume"
    PROP = "prop"
    EXPRESSION = "expression"
    STYLE = "style"
    LIGHTING = "lighting"
    STORYBOARD = "storyboard"


class H3VideoRole(str, Enum):
    ACTION_RHYTHM = "action_rhythm"
    CAMERA_EDITING = "camera_editing"
    CHARACTER_MOTION = "character_motion"


class H3AudioRole(str, Enum):
    PROTAGONIST_VOICE = "protagonist_voice"
    SECONDARY_VOICE = "secondary_voice"
    NARRATOR_VOICE = "narrator_voice"


ReferenceRole = H3ImageRole | H3VideoRole | H3AudioRole


@dataclass(frozen=True)
class H3ReferenceItem:
    kind: str
    role: ReferenceRole
    path: str
    include_audio: bool = False
    duration_seconds: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "role": self.role.value,
            "path": self.path,
            "include_audio": self.include_audio,
            "duration_seconds": float(self.duration_seconds),
        }


@dataclass(frozen=True)
class H3ReferenceBundle:
    images: tuple[H3ReferenceItem, ...] = ()
    videos: tuple[H3ReferenceItem, ...] = ()
    audios: tuple[H3ReferenceItem, ...] = ()

    def __post_init__(self) -> None:
        if len(self.images) > 9:
            raise ValueError("H3 supports at most 9 reference images")
        if len(self.videos) > 3:
            raise ValueError("H3 supports at most 3 reference videos")
        if len(self.audios) > 3:
            raise ValueError("H3 supports at most 3 reference audios")
        if self.total_files > 12:
            raise ValueError("H3 supports at most 12 reference files")

    @property
    def total_files(self) -> int:
        return len(self.images) + len(self.videos) + len(self.audios)

    def to_dict(self) -> dict[str, list[dict[str, Any]]]:
        return {
            "images": [item.to_dict() for item in self.images],
            "videos": [item.to_dict() for item in self.videos],
            "audios": [item.to_dict() for item in self.audios],
        }


@dataclass(frozen=True)
class H3SegmentSpec:
    index: int
    prompt: str
    duration_seconds: float
    frames: int
    fps: int
    seed: int
    continuity_from_index: int | None = None

    @property
    def clip_index(self) -> int:
        return self.index + 1


@dataclass(frozen=True)
class H3UnifiedOptions:
    mode: H3Mode = H3Mode.FL2VA
    runtime: str = "auto"
    allow_fallback: bool = True

    def validate_inputs(
        self,
        first_frame: str,
        last_frame: str,
        references: H3ReferenceBundle,
    ) -> None:
        if self.mode is H3Mode.I2VA and not first_frame:
            raise ValueError("I2VA requires first_frame")
        if self.mode is H3Mode.FL2VA and (not first_frame or not last_frame):
            raise ValueError("FL2VA requires first_frame and last_frame")
        if self.mode is H3Mode.L2VA and not last_frame:
            raise ValueError("L2VA requires last_frame")
        if self.mode is H3Mode.REF2VA and references.total_files == 0:
            raise ValueError("Ref2VA requires at least one reference")
