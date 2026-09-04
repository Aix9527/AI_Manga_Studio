from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class StageKey(str, Enum):
    IMPORT = "import"
    STORY = "story"
    CHARACTER = "character"
    STORYBOARD = "storyboard"
    KEYFRAME = "keyframe"
    VIDEO = "video"
    AUDIO = "audio"
    COMPOSE = "compose"
    EXPORT = "export"


class StageAutomation(BaseModel):
    stage_key: StageKey
    auto_produce: bool = True
    quality_threshold: float = Field(0.82, ge=0, le=1)
    max_quality_retries: int = Field(2, ge=0, le=2)
    auto_advance: bool = True
    provider_settings: dict[str, object] = Field(default_factory=dict)


class DirectorSettings(BaseModel):
    composition: str = "三分构图"
    shot_size: str = "中近景"
    camera_movement: str = "推镜"
    movement_strength: int = Field(65, ge=0, le=100)
    focal_length: str = "35mm"
    lighting: str = "电影逆光"
    emotion: list[str] = Field(default_factory=list)
    prompt: str = ""


class ProductionTemplateVersion(BaseModel):
    id: str
    project_id: str
    version: int
    name: str = ""
    schema_version: int = 1
    content_json: str
    content_sha256: str
    compiled_json: str
    compiled_sha256: str
    status: str = "active"
    created_at: str
    published_at: str | None = None


class ProductionTemplateList(BaseModel):
    project_id: str
    latest_version: int = 0
    published_version: int | None = None
    versions: list[ProductionTemplateVersion] = Field(default_factory=list)


class StageSummary(BaseModel):
    stage_key: StageKey
    status: str = "pending"
    progress: float = 0
    waiting_review: int = 0
    automation: StageAutomation


class WorkspaceSnapshot(BaseModel):
    project_id: str
    title: str
    source_path: str = ""
    version: str = "v01"
    progress: float = 0
    pending_reviews: int = 0
    active_jobs: int = 0
    estimated_minutes: int | None = None
    stages: list[StageSummary]
    system_health: dict[str, object] = Field(default_factory=dict)


class ProjectAsset(BaseModel):
    id: int
    project_id: str
    job_id: str
    step_id: str
    kind: str
    path: str
    media_url: str
    stage_key: str | None = None
    scene_id: str = ""
    shot_id: str = ""
    version: int
    parent_artifact_id: int | None = None
    active: bool
    quality_status: str = "unreviewed"
    quality_attempt: int = 0
    quality_report: dict[str, object] = Field(default_factory=dict)
    metadata: dict[str, object] = Field(default_factory=dict)
    created_at: str
