from __future__ import annotations
import json
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path

from backend.story.models import Chapter, Scene


@dataclass
class StorySection:
    """Long-term story memory for a narrative section (MangaFlow-inspired).

    Carries character state, emotion, visual theme and the previous event so
    later sections (and the Director v2) can stay consistent without re-reading
    the raw novel.
    """
    chapter_id: str
    scene_id: str
    section_key: str = ""
    title: str = ""
    summary: str = ""
    character_state: dict = field(default_factory=dict)
    emotion: str = ""
    visual_theme: dict = field(default_factory=dict)
    previous_event: str = ""
    memory_payload: dict = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())


_THEME_RULES: list[tuple[list[str], dict]] = [
    (["lab", "实验室", "医院", "office", "办公室"], {"palette": "cold_blue", "lighting": "cool_fluorescent", "texture": "clean_metal_glass"}),
    (["underground", "地下", "地底", "洞穴", "cavern", "地道"], {"palette": "dark_bronze", "lighting": "low_key_warm", "texture": "carved_stone"}),
    (["space", "深空", "太空", "月球", "moon", "signal"], {"palette": "deep_space_blue", "lighting": "high_contrast_black", "texture": "stars_vacuum"}),
    (["village", "村落", "蜀地", "聚落", "settlement"], {"palette": "warm_earth", "lighting": "soft_warm", "texture": "clay_bamboo"}),
    (["street", "街道", "公路", "road", "城"], {"palette": "night_neon", "lighting": "street_lamp", "texture": "wet_asphalt"}),
    (["bronze", "青铜", "祭坛", "altar", "归墟"], {"palette": "bronze_gold", "lighting": "golden_energy", "texture": "ritual_bronze"}),
]


def _visual_theme(scene: Scene) -> dict:
    hay = " ".join([scene.location, scene.title, " ".join(scene.tags)]).lower()
    for keywords, theme in _THEME_RULES:
        if any(k.lower() in hay for k in keywords):
            return dict(theme)
    if scene.time_of_day in ("night", "深夜", "凌晨", "夜"):
        return {"palette": "night_blue", "lighting": "moonlight", "texture": "soft_shadow"}
    return {"palette": "neutral", "lighting": "soft_day", "texture": "default"}


class StorySectionMemory:
    """Persists and recalls StorySections as JSON under ``storage/story_sections``."""

    def __init__(self, storage_dir: str | Path = "storage/story_sections"):
        self.storage_dir = Path(storage_dir)
        self.storage_dir.mkdir(parents=True, exist_ok=True)

    def build_section(
        self,
        scene: Scene,
        chapter: Chapter | None = None,
        prev_section: StorySection | None = None,
    ) -> StorySection:
        if chapter:
            section_key = f"ch{chapter.number}_sc{scene.number:02d}"
        else:
            section_key = f"sc{scene.number:02d}"
        character_state = {cid: {"present": True, "state": "unknown"} for cid in scene.characters}
        return StorySection(
            chapter_id=scene.chapter_id or (chapter.id if chapter else ""),
            scene_id=scene.id,
            section_key=section_key,
            title=scene.title,
            summary=scene.summary or scene.raw_text[:120],
            character_state=character_state,
            emotion=scene.mood or "neutral",
            visual_theme=_visual_theme(scene),
            previous_event=prev_section.summary if prev_section else "",
            memory_payload={
                "location": scene.location,
                "time_of_day": scene.time_of_day,
                "characters": scene.characters,
            },
        )

    def _path(self, novel_id: str, section_key: str) -> Path:
        return self.storage_dir / f"{novel_id}__{section_key}.json"

    def save(self, novel_id: str, section: StorySection) -> Path:
        p = self._path(novel_id, section.section_key)
        p.write_text(json.dumps(asdict(section), ensure_ascii=False, indent=2), encoding="utf-8")
        return p

    def load(self, novel_id: str, section_key: str) -> StorySection | None:
        p = self._path(novel_id, section_key)
        if not p.exists():
            return None
        data = json.loads(p.read_text(encoding="utf-8"))
        return StorySection(**{k: v for k, v in data.items() if k in StorySection.__dataclass_fields__})

    def list_sections(self, novel_id: str) -> list[StorySection]:
        out = []
        for p in sorted(self.storage_dir.glob(f"{novel_id}__*.json")):
            data = json.loads(p.read_text(encoding="utf-8"))
            out.append(StorySection(**{k: v for k, v in data.items() if k in StorySection.__dataclass_fields__}))
        return out

    def memory_context(self, novel_id: str, section_key: str) -> dict:
        sec = self.load(novel_id, section_key)
        if sec is None:
            return {"available": False}
        return {
            "available": True,
            "section_key": sec.section_key,
            "emotion": sec.emotion,
            "visual_theme": sec.visual_theme,
            "character_state": sec.character_state,
            "previous_event": sec.previous_event,
            "location": sec.memory_payload.get("location", ""),
        }
