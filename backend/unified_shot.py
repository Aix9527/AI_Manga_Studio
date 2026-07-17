"""
AI Manga Studio Pro V1.0 — Unified Shot JSON Schema

THE single source of truth. This JSON is read by:
  • ComfyUI workflow generator → injects params into node graph
  • Python backend            → routes, API, DB sync
  • Web frontend              → shot editor, preview

One JSON file per shot, stored under project output directory.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
from enum import Enum

from pydantic import BaseModel, Field


# ============================================================
# Enums
# ============================================================

class Camera(str, Enum):
    close = "close"
    medium = "medium"
    wide = "wide"
    drone = "drone"
    pov = "pov"
    tracking = "tracking"
    dutch = "dutch"
    overhead = "overhead"


class Emotion(str, Enum):
    neutral = "neutral"
    happy = "happy"
    sad = "sad"
    angry = "angry"
    surprised = "surprised"
    fearful = "fearful"
    disgusted = "disgusted"
    calm = "calm"
    excited = "excited"
    determined = "determined"


class Weather(str, Enum):
    clear = "clear"
    cloudy = "cloudy"
    rain = "rain"
    snow = "snow"
    fog = "fog"
    storm = "storm"
    sunset = "sunset"
    night = "night"


class TimeOfDay(str, Enum):
    dawn = "dawn"
    morning = "morning"
    noon = "noon"
    afternoon = "afternoon"
    dusk = "dusk"
    night = "night"


class Lighting(str, Enum):
    natural = "natural"
    cinematic = "cinematic"
    rim = "rim"
    soft = "soft"
    hard = "hard"
    volumetric = "volumetric"
    neon = "neon"
    candlelight = "candlelight"


class ShotStatus(str, Enum):
    waiting = "waiting"
    generating = "generating"
    success = "success"
    failed = "failed"


# ============================================================
# Character Reference
# ============================================================

class CharacterRef(BaseModel):
    """Minimal character reference inside a shot."""
    name: str = ""
    char_id: int = 0
    expression: str = "neutral"       # overrides default emotion
    action: str = ""                   # what the character is doing
    position: str = ""                 # foreground / midground / background


# ============================================================
# Unified Shot — The Core Schema
# ============================================================

class UnifiedShot(BaseModel):
    """Complete shot definition. Every module reads/writes this format.

    Minimal example:
      {
        "chapter": 1,
        "scene": 3,
        "shot": 12,
        "duration": 5.0,
        "camera": "close",
        "characters": ["林凡", "少女"],
        "background": "森林",
        "emotion": "sad",
        "voice": "male03"
      }

    Full fields below.
    """

    # ── indexing ────────────────────────────────────────────
    chapter: int = 1                         # 章节编号
    scene: int = 1                           # 场景编号 (scene_id)
    shot: int = 1                            # 镜头编号 (shot index)

    # ── timing ─────────────────────────────────────────────
    duration: float = 5.0                    # 秒

    # ── camera ─────────────────────────────────────────────
    camera: Camera = Camera.medium           # 镜头类型
    camera_angle: str = ""                   # e.g. "low angle", "dutch tilt"
    camera_motion: str = ""                  # e.g. "slow push-in", "dolly left"
    focal_length: str = ""                   # e.g. "24mm", "85mm"

    # ── composition ────────────────────────────────────────
    characters: List[str] = Field(default_factory=list)         # 角色名列表
    character_details: List[CharacterRef] = Field(default_factory=list)
    background: str = ""                                         # 背景描述
    foreground: str = ""                                         # 前景元素
    composition_notes: str = ""                                  # 构图备注
    narration: str = ""                                          # 旁白/段落原文

    # ── mood ───────────────────────────────────────────────
    emotion: Emotion = Emotion.neutral        # 整体情绪
    atmosphere: str = ""                     # e.g. "tense", "romantic", "mysterious"
    color_palette: str = ""                  # e.g. "warm earth tones", "cold blue"

    # ── lighting & environment ─────────────────────────────
    lighting: Lighting = Lighting.natural
    weather: Weather = Weather.clear
    time_of_day: TimeOfDay = TimeOfDay.noon
    light_source: str = ""                   # e.g. "window left", "lantern overhead"

    # ── audio ──────────────────────────────────────────────
    voice: str = ""                          # 配音标识 / 音色
    dialogue: str = ""                       # 对白 / 字幕
    sfx: str = ""                            # 音效描述
    bgm: str = ""                            # 背景音乐

    # ── generation params ──────────────────────────────────
    # Flux Schnell defaults: steps=4, cfg=1.0, native 1344×704
    # For SDXL: set steps=30, cfg=5.0, width=1344, height=768
    seed: int = -1                           # -1 = random
    steps: int = 4
    cfg: float = 1.0
    width: int = 1344
    height: int = 704
    negative_prompt: str = ""                # 全局负面 Prompt
    extra: Dict[str, Any] = Field(default_factory=dict)  # 扩展字段

    # ── tracking (managed by pipeline, not user) ──────────
    status: ShotStatus = ShotStatus.waiting
    shot_id: str = ""                        # e.g. "proj01_ch01_s012"
    retry_count: int = 0
    retry_max: int = 3
    error_message: str = ""

    # ── output paths (filled by pipeline) ─────────────────
    json_path: str = ""                      # path to this JSON file
    image_path: str = ""
    video_path: str = ""
    thumbnail_path: str = ""
    background_image_path: str = ""          # path to scene background image (filled by SceneStage)

    # ── metadata ──────────────────────────────────────────
    created_at: str = ""
    updated_at: str = ""

    @property
    def positive_prompt(self) -> str:
        """Compute positive prompt from shot fields at access time."""
        from backend.workflow_generator import _build_positive_prompt
        return _build_positive_prompt(self)

    @classmethod
    def from_json_file(cls, path: str) -> "UnifiedShot":
        """Load a unified shot JSON from disk."""
        import json
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        shot = cls(**data)
        shot.json_path = path
        return shot

    def to_json_file(self, path: str) -> None:
        """Write this shot to a JSON file on disk."""
        import json, os
        os.makedirs(os.path.dirname(path), exist_ok=True)
        self.updated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.json_path = path
        data = self.model_dump(mode="json", exclude_none=False)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def to_minimal_dict(self) -> Dict[str, Any]:
        """Return the minimal user-facing dict (like user's example)."""
        return {
            "chapter": self.chapter,
            "scene": self.scene,
            "shot": self.shot,
            "duration": self.duration,
            "camera": self.camera.value,
            "characters": self.characters,
            "background": self.background,
            "emotion": self.emotion.value,
            "voice": self.voice,
        }

    def mark_generating(self) -> None:
        self.status = ShotStatus.generating

    def mark_success(self, image: str = "", video: str = "") -> None:
        self.status = ShotStatus.success
        if image:
            self.image_path = image
        if video:
            self.video_path = video

    def mark_failed(self, error: str) -> None:
        self.status = ShotStatus.failed
        self.error_message = error
        self.retry_count += 1


# ============================================================
# Batch Container
# ============================================================

class ShotBatch(BaseModel):
    """A collection of unified shots for a chapter."""
    project_id: str = ""
    chapter: int = 1
    total_shots: int = 0
    shots: List[UnifiedShot] = Field(default_factory=list)

    @classmethod
    def from_directory(cls, dirpath: str) -> "ShotBatch":
        """Load all shot JSONs from a directory."""
        import json
        batch = cls()
        p = Path(dirpath)
        if not p.exists():
            return batch
        for f in sorted(p.glob("shot_*.json")):
            with open(f, "r", encoding="utf-8") as fh:
                data = json.load(fh)
                data["json_path"] = str(f)
                batch.shots.append(UnifiedShot(**data))
        batch.total_shots = len(batch.shots)
        if batch.shots:
            batch.chapter = batch.shots[0].chapter
        return batch
