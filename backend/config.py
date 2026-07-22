"""
AI Manga Studio Pro V1.0 — Global Configuration Loader

Loads settings from config/settings.yaml and exposes them as typed
attributes for the entire backend application.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional

import yaml
from pydantic import BaseModel, Field, field_validator, model_validator


PROJECT_ROOT = Path(__file__).resolve().parent.parent


# ============================================================
# Sub-models
# ============================================================

class ServerConfig(BaseModel):
    host: str = "0.0.0.0"
    port: int = 8000
    reload: bool = True
    workers: int = 1
    log_level: str = "info"


class ComfyUIInstance(BaseModel):
    """Configuration for a single ComfyUI instance bound to a GPU."""
    gpu_id: int = 0
    port: int = 8188
    base_url: str = "http://127.0.0.1:8188"


class ComfyUIConfig(BaseModel):
    base_url: str = "http://127.0.0.1:8188"
    ws_url: str = "ws://127.0.0.1:8188/ws"
    output_dir: str = ""
    timeout: int = 600
    poll_interval: float = 1.0
    max_retries: int = 3
    instances: Dict[str, ComfyUIInstance] = Field(default_factory=dict)


class DatabaseConfig(BaseModel):
    type: str = "sqlite"
    base_dir: str = "D:/AI_Manga_Studio/database"
    databases: Dict[str, str] = Field(default_factory=dict)
    redis_url: str = "redis://127.0.0.1:6379/0"

    @property
    def characters_path(self) -> str:
        return self.databases.get("characters", self._default_path("characters"))

    @property
    def scenes_path(self) -> str:
        return self.databases.get("scenes", self._default_path("scenes"))

    @property
    def projects_path(self) -> str:
        return self.databases.get("projects", self._default_path("projects"))

    @property
    def tasks_path(self) -> str:
        return self.databases.get("tasks", self._default_path("tasks"))

    @property
    def cache_path(self) -> str:
        return self.databases.get("cache", self._default_path("cache"))

    def _default_path(self, name: str) -> str:
        import os
        return os.path.join(self.base_dir.replace("/", "\\"), f"{name}.db")


class ModelsConfig(BaseModel):
    base_path: str = "D:/AI_Manga_Studio/models"
    checkpoint: str = "sd_xl_base_1.0.safetensors"
    vae: str = "sdxl_vae.safetensors"
    upscaler: str = "4x-UltraSharp.pth"
    face_detector: str = "yolov8n-face.pt"
    lipsync: str = "MuseTalk"
    tts: str = "CosyVoice-300M"


class ProjectConfig(BaseModel):
    root_path: str = "D:/AI_Manga_Studio/project"
    cache_path: str = "D:/AI_Manga_Studio/cache"
    output_path: str = "D:/AI_Manga_Studio/output"


class LoggingConfig(BaseModel):
    level: str = "DEBUG"
    path: str = "D:/AI_Manga_Studio/logs"
    rotation: str = "50 MB"
    retention: str = "30 days"
    format: str = "{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | {name}:{function}:{line} - {message}"


class QualityEngineCheckConfig(BaseModel):
    """Per-check configuration for the Quality Engine."""
    enabled: bool = True
    threshold: float = 0.5


class QualityEngineConfig(BaseModel):
    """Quality Engine master configuration.

    Runs entirely on Python side, never inside ComfyUI.
    Failed shots are automatically re-queued with mutated parameters.
    """
    enabled: bool = True
    max_retries: int = 3
    score_threshold: float = 0.65
    checks: Dict[str, QualityEngineCheckConfig] = Field(default_factory=dict)


class SchedulerConfig(BaseModel):
    max_concurrent_shots: int = 4
    retry_max: int = 3
    retry_delay_seconds: int = 30
    gpu_memory_threshold: float = 0.9
    queue_poll_interval: float = 2.0


class RuntimeConfig(BaseModel):
    data_root: str = "."
    local_only: Literal[True] = True


class OrchestrationConfig(BaseModel):
    database_path: str = Field(
        default="database/orchestration.db",
        min_length=1,
    )
    worker_poll_seconds: float = Field(default=0.5, gt=0)
    lease_seconds: int = Field(default=30, gt=0)
    heartbeat_seconds: int = Field(default=10, gt=0)
    max_retries: int = Field(default=3, ge=0)
    retry_delays_seconds: List[int] = Field(default_factory=lambda: [5, 15, 45])

    @field_validator("database_path", mode="before")
    @classmethod
    def trim_database_path(cls, value: Any) -> Any:
        return value.strip() if isinstance(value, str) else value

    @field_validator("retry_delays_seconds")
    @classmethod
    def require_nonnegative_retry_delays(cls, value: List[int]) -> List[int]:
        if any(delay < 0 for delay in value):
            raise ValueError("retry delays must be nonnegative")
        return value

    @model_validator(mode="after")
    def validate_timing_and_retry_policy(self) -> "OrchestrationConfig":
        if self.max_retries > 0 and not self.retry_delays_seconds:
            raise ValueError("retry delays are required when retries are enabled")
        if self.heartbeat_seconds >= self.lease_seconds:
            raise ValueError("heartbeat_seconds must be less than lease_seconds")
        return self


class PathsConfig(BaseModel):
    """Filesystem paths used across the application."""
    workflow: str = "D:\\AI_Manga_Studio\\workflow"
    cache: str = "D:\\AI_Manga_Studio\\storage\\cache"
    logs: str = "D:\\AI_Manga_Studio\\logs"
    plugins: str = "D:\\AI_Manga_Studio\\plugins"
    storage: str = "D:\\AI_Manga_Studio\\storage"
    scripts: str = "D:\\AI_Manga_Studio\\scripts"
    tests: str = "D:\\AI_Manga_Studio\\tests"
    docs: str = "D:\\AI_Manga_Studio\\docs"


class PluginConfig(BaseModel):
    """Active plugin selection for each pipeline stage."""
    image: str = "flux"        # Image generation: flux / sd / ...
    video: str = "wan"         # I2V: wan / ltx / animatediff / ...
    tts: str = "tts"           # TTS: tts / bark / cosyvoice / ...
    subtitle: str = "subtitle" # Subtitles: subtitle / ass / ...
    music: str = "music"       # Music: music / suno / udio / ...
    quality: str = "quality"   # Enhancement: quality / realesrgan / ...


class LLMConfigModel(BaseModel):
    """LLM provider configuration for prompt refinement."""
    provider: str = "deepseek"  # deepseek|qwen|glm|ollama
    api_key: str = ""           # 留空则读 DEEPSEEK_API_KEY 环境变量
    model: str = "deepseek-chat"
    max_tokens: int = 500
    temperature: float = 0.7
    endpoint: str = "https://api.deepseek.com/v1"


class GenerationConfig(BaseModel):
    default_style: str = "anime"
    default_resolution: List[int] = [1344, 768]
    default_steps: int = 30
    default_cfg: float = 5.0
    default_sampler: str = "dpmpp_2m"
    image_format: str = "png"
    video_fps: int = 24
    default_duration_seconds: int = 60

    @property
    def width(self) -> int:
        return self.default_resolution[0]

    @property
    def height(self) -> int:
        return self.default_resolution[1]


# ============================================================
# Root Config
# ============================================================

class AppConfig(BaseModel):
    """Root configuration aggregating all sub-sections."""
    runtime: RuntimeConfig = Field(default_factory=RuntimeConfig)
    server: ServerConfig = Field(default_factory=ServerConfig)
    comfyui: ComfyUIConfig = Field(default_factory=ComfyUIConfig)
    database: DatabaseConfig = Field(default_factory=DatabaseConfig)
    models: ModelsConfig = Field(default_factory=ModelsConfig)
    project: ProjectConfig = Field(default_factory=ProjectConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)
    quality_engine: QualityEngineConfig = Field(default_factory=QualityEngineConfig)
    scheduler: SchedulerConfig = Field(default_factory=SchedulerConfig)
    orchestration: OrchestrationConfig = Field(default_factory=OrchestrationConfig)
    generation: GenerationConfig = Field(default_factory=GenerationConfig)
    llm: LLMConfigModel = Field(default_factory=LLMConfigModel)
    plugins: PluginConfig = Field(default_factory=PluginConfig)
    paths: PathsConfig = Field(default_factory=PathsConfig)


# ============================================================
# Loader
# ============================================================

# Top-level LLM_CONFIG for direct import (compatibility with prompt_refiner.py)
LLM_CONFIG = {
    "provider": "deepseek",
    "api_key": "",  # 留空则读 DEEPSEEK_API_KEY 环境变量
    "model": "deepseek-chat",
    "max_tokens": 500,
    "temperature": 0.7,
    "endpoint": "https://api.deepseek.com/v1",
}

# ============================================================
# Director LLM Configuration (V2.0 — Model Dispatch)
# ============================================================

DIRECTOR_LLM_CONFIG = {
    "qwen_235b": {
        "endpoint": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "model": "qwen3-235b-a22b",
        "role": "story_director",
    },
    "deepseek_r1": {
        "endpoint": "https://api.deepseek.com/v1",
        "model": "deepseek-reasoner",
        "role": "shot_planner",
    },
    "qwen_32b": {
        "endpoint": "http://localhost:11434/v1",
        "model": "qwen3:32b",
        "role": "local_fallback",
    },
}

# ============================================================
# Pipeline Configuration (V2.0 — 全架构升级)
# ============================================================

PIPELINE_CONFIG = {
    "flux_engine": "comfyui",
    "sdxl_engine": "comfyui",
    "controlnet_enabled": True,
    "upscaler": "realesrgan",      # realesrgan | pil_lanczos
    "upscale_factor": 4,
    "tts_engine": "cosyvoice2",
    "voice_cloning": "gpt_sovits",
    "lip_sync": "musetalk",
    "video_primary": "wan2.2",
    "video_secondary": "hunyuan",
    "kolors_effects": False,        # 默认关闭，按需开启
}

# ============================================================
# Model Router Configuration (V2.0 — 智能模型路由器)
# ============================================================

MODEL_ROUTER_CONFIG = {
    "character_portrait": "flux",
    "anime_character": "noobai",       # NoobAI / Illustrious
    "ancient_architecture": "flux",
    "city_scene": "sdxl",
    "scifi_scene": "flux",
    "landscape_scene": "sdxl",
    "dialogue_video": "wan2.2",
    "battle_video": "hunyuan",
    "landscape_video": "ltx",
    "camera_video": "wan2.2",
    "slow_motion_video": "hunyuan",
    "super_resolution": "supir",
    "face_restoration": "codeformer",
    "character_consistency": "pulid",
    "dubbing": "cosyvoice2",
    "voice_cloning": "gpt_sovits",
    "lip_sync": "musetalk",
    "subtitles": "whisper",
    "post_production": "ffmpeg",
}

# ============================================================
# Resource Configuration (V2.0 — 轻重分离)
# ============================================================

RESOURCE_CONFIG = {
    "target_vram_gb": 12,
    "cooldown_seconds": 3,           # 模型卸载后冷却时间
    "lazy_unload": True,             # 仅显存不足时才卸载模型
    "heavy_models": [                # 高显存模型（不可并行的重型组）
        "flux",
        "pulid",
        "wan2.2",
        "hunyuan",
    ],
    "light_models": [                # 低显存模型（可与重型组交替）
        "sdxl",
        "ltx",
        "musetalk",
    ],
    "cpu_only": [                    # 纯 CPU，不占 GPU
        "ffmpeg",
        "whisper",
        "cosyvoice2",
        "gpt_sovits",
    ],
}

_CONFIG: Optional[AppConfig] = None
_CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "settings.yaml"


def load_config(config_path: Optional[str] = None) -> AppConfig:
    """Load and cache the global configuration.

    Args:
        config_path: Optional override for the YAML config file path.

    Returns:
        AppConfig instance populated from YAML.
    """
    global _CONFIG
    if _CONFIG is not None and config_path is None:
        return _CONFIG

    path = Path(config_path) if config_path else _CONFIG_PATH

    raw: Dict[str, Any] = {}
    if path.exists():
        with open(path, "r", encoding="utf-8") as fh:
            raw = yaml.safe_load(fh) or {}

    _CONFIG = AppConfig(**raw)
    return _CONFIG


def get_config() -> AppConfig:
    """Return the cached configuration, loading it if necessary."""
    if _CONFIG is None:
        return load_config()
    return _CONFIG
