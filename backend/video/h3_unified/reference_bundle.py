from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar


MAX_REFERENCE_FILES = 12
MAX_REFERENCE_VIDEOS = 3
MAX_REFERENCE_AUDIOS = 3


@dataclass(frozen=True)
class H3ReferenceBundle:
    """Semantic H3 reference assets owned by AI Manga Studio.

    Image fields deliberately mirror production concepts (character, location,
    costume, prop, etc.) instead of exposing anonymous ``ref_image_N`` slots to
    the application layer.  Empty fields are omitted when building a runtime
    request, while populated fields keep a deterministic order.
    """

    character_identity: str = ""
    secondary_character: str = ""
    location: str = ""
    costume: str = ""
    prop: str = ""
    expression: str = ""
    style: str = ""
    lighting: str = ""
    storyboard: str = ""
    videos: tuple[str, ...] = ()
    audios: tuple[str, ...] = ()

    IMAGE_FIELDS: ClassVar[tuple[str, ...]] = (
        "character_identity",
        "secondary_character",
        "location",
        "costume",
        "prop",
        "expression",
        "style",
        "lighting",
        "storyboard",
    )

    def __post_init__(self) -> None:
        if len(self.videos) > MAX_REFERENCE_VIDEOS:
            raise ValueError(f"H3 supports at most {MAX_REFERENCE_VIDEOS} reference videos")
        if len(self.audios) > MAX_REFERENCE_AUDIOS:
            raise ValueError(f"H3 supports at most {MAX_REFERENCE_AUDIOS} reference audios")
        if self.total_reference_files > MAX_REFERENCE_FILES:
            raise ValueError(f"H3 unified reference bundle supports at most {MAX_REFERENCE_FILES} files")

    def image_references(self) -> list[tuple[str, str]]:
        return [
            (field, value)
            for field in self.IMAGE_FIELDS
            if (value := str(getattr(self, field) or "").strip())
        ]

    @property
    def total_reference_files(self) -> int:
        return len(self.image_references()) + len(self.videos) + len(self.audios)

    def is_empty(self) -> bool:
        return self.total_reference_files == 0
