from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from .reference_bundle import H3ReferenceBundle


CONTROL_DESK_SCHEMA = "ltoj-manga/control-desk-v1.0"
ALLOWED_STEPS = (8, 10, 12, 15, 20)
ALLOWED_RESOLUTIONS = ("360p", "480p", "720p", "1080p")
ASPECT_RATIO_LABELS = {
    "16:9": "16:9 横屏",
    "9:16": "9:16 竖屏",
    "1:1": "1:1 方形",
}
IMAGE_ROLE_LABELS = {
    "character_identity": "主角身份",
    "secondary_character": "配角/对手",
    "location": "场景环境",
    "costume": "服装造型",
    "prop": "关键道具",
    "expression": "表情状态",
    "style": "画风材质",
    "lighting": "光影色调",
    "storyboard": "分镜图/N宫格",
}
VIDEO_ROLE_LABELS = ("动作与节奏", "运镜与剪辑", "人物动作")
AUDIO_ROLE_LABELS = ("主角声线", "配角/对手声线", "旁白/第三角色声线")


class H3Mode(str, Enum):
    T2VA = "T2VA"
    I2VA = "I2VA"
    FL2VA = "FL2VA"
    L2VA = "L2VA"
    REF2VA = "Ref2VA"


def _gpu_profile(vram_gb: float) -> str:
    if vram_gb <= 16:
        return "balanced_offload_16gb"
    if vram_gb <= 24:
        return "balanced_offload"
    if vram_gb <= 36:
        return "balanced"
    return "high_vram"


def _slot(role: str, filename: str = "", *, include_audio: bool = False) -> dict[str, Any]:
    clean = str(filename or "").strip()
    return {
        "filename": clean,
        "enabled": bool(clean),
        "role": role,
        "include_audio": bool(include_audio),
        "duration_seconds": 0.0,
        "bound_image_alias": "",
    }


@dataclass(frozen=True)
class H3UnifiedRequest:
    mode: H3Mode
    prompt: str
    references: H3ReferenceBundle = field(default_factory=H3ReferenceBundle)
    first_frame: str = ""
    last_frame: str = ""
    aspect_ratio: str = "9:16"
    resolution: str = "480p"
    duration_seconds: float = 5.0
    steps: int = 12
    seed: int = -1
    gpu_vram_gb: float = 16.0
    model_profile: str = "standard"
    scheduler: str = "官方基准（推荐先测）"
    reference_quality: str = "match"
    input_style: str = "natural"
    shot_size: str = "中景"
    camera_movement: str = "固定镜头"
    camera_speed: str = "正常"
    motion_strength: str = "自然"
    environment_sound: str = ""
    music: str = ""
    dialogue: str = ""
    sound_enabled: bool = True
    negative_prompt: str = "人物复制、脸部漂移、肢体变形、道具重复、画面闪烁、字幕和水印"
    advanced_supplement: str = ""
    shot_project: str = "未命名项目"
    shot_episode: int = 1
    shot_scene: int = 1
    shot_number: int = 1
    shot_take: int = 1

    def __post_init__(self) -> None:
        if not isinstance(self.mode, H3Mode):
            try:
                object.__setattr__(self, "mode", H3Mode(str(self.mode)))
            except ValueError as error:
                raise ValueError(f"unsupported H3 mode: {self.mode}") from error
        if not str(self.prompt or "").strip():
            raise ValueError("H3 unified prompt must not be empty")
        if not 2 <= float(self.duration_seconds) <= 15:
            raise ValueError("H3 unified duration_seconds must be between 2 and 15 seconds")
        if int(self.steps) not in ALLOWED_STEPS:
            raise ValueError(f"H3 unified steps must be one of {ALLOWED_STEPS}")
        if self.resolution not in ALLOWED_RESOLUTIONS:
            raise ValueError(f"unsupported H3 resolution: {self.resolution}")
        if self.aspect_ratio not in ASPECT_RATIO_LABELS:
            raise ValueError(f"unsupported H3 aspect ratio: {self.aspect_ratio}")


def build_ui_state(request: H3UnifiedRequest) -> dict[str, Any]:
    image_values = dict(request.references.image_references())
    image_slots = [
        _slot(IMAGE_ROLE_LABELS[field], image_values.get(field, ""))
        for field in H3ReferenceBundle.IMAGE_FIELDS
    ]
    video_slots = [
        _slot(role, request.references.videos[index] if index < len(request.references.videos) else "", include_audio=True)
        for index, role in enumerate(VIDEO_ROLE_LABELS)
    ]
    audio_slots = [
        _slot(role, request.references.audios[index] if index < len(request.references.audios) else "")
        for index, role in enumerate(AUDIO_ROLE_LABELS)
    ]

    return {
        "schema": CONTROL_DESK_SCHEMA,
        "product_version": "ai-manga-adapter-v1",
        "director": {
            "schema": "ai-manga/h3-director-v1",
            "mode": request.mode.value,
            "input_style": request.input_style,
            "prompt_text": request.prompt,
            "camera": {
                "shot_size": request.shot_size,
                "movement": request.camera_movement,
                "speed": request.camera_speed,
                "motion_strength": request.motion_strength,
                "n_grid": "不使用N宫格",
                "grid_order": "从左到右、从上到下",
            },
            "sound": {
                "enabled": request.sound_enabled,
                "environment": request.environment_sound,
                "music": request.music,
                "dialogue": request.dialogue,
            },
            "negative": request.negative_prompt,
            "advanced_supplement": request.advanced_supplement,
            "production": {
                "aspect_ratio": ASPECT_RATIO_LABELS[request.aspect_ratio],
                "resolution": request.resolution,
                "duration_seconds": float(request.duration_seconds),
                "steps": int(request.steps),
                "seed": int(request.seed),
                "gpu_profile": "自动检测GPU",
                "model_profile": request.model_profile,
                "reference_quality": request.reference_quality,
                "scheduler": request.scheduler,
            },
            "shot": {
                "project": request.shot_project,
                "episode": int(request.shot_episode),
                "scene": int(request.shot_scene),
                "shot": int(request.shot_number),
                "take": int(request.shot_take),
            },
        },
        "assets": {
            "images": image_slots,
            "videos": video_slots,
            "audios": audio_slots,
            "first_frame": _slot("首帧", request.first_frame),
            "last_frame": _slot("尾帧", request.last_frame),
        },
        "runtime": {
            "acceleration": "自动（推荐）",
            "profile": _gpu_profile(float(request.gpu_vram_gb)),
        },
        "ui": {"active_asset_tab": "images", "advanced_open": False},
        "outputs": [],
    }
