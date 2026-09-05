from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

from backend.orchestration.enums import JobStatus, JobCommand


class JobOptions(BaseModel):
    style: str = "anime"
    local_first: bool = True
    chapter: int | None = None
    max_shots: int = 30
    tts_enabled: bool = True
    lipsync_enabled: bool = True
    subtitles_enabled: bool = True
    sfx_enabled: bool = True
    bgm_enabled: bool = True
    video_workflow: str = "auto"
    bgm_dir: str = "assets/bgm"
    sfx_dir: str = "assets/sfx"
    forbid_fallback_artifacts: bool = True
    template_context: dict[str, Any] = Field(default_factory=dict, exclude=True)
    stage_policy_context: list[dict[str, Any]] = Field(default_factory=list, exclude=True)


class JobSettings(BaseModel):
    width: int = 1080
    height: int = 1920
    fps: int = 24
    shot_duration: float = 5.0
    options: JobOptions = Field(default_factory=JobOptions)
    stage_policy: list[dict[str, Any]] = Field(default_factory=list)
    template: dict[str, Any] = Field(default_factory=dict)
    timeline: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def promote_runtime_context(self) -> "JobSettings":
        if self.options.template_context:
            self.template = dict(self.options.template_context)
        if self.options.stage_policy_context:
            self.stage_policy = [dict(item) for item in self.options.stage_policy_context]
        return self


class JobCreate(BaseModel):
    project_id: str
    input_path: str
    input_type: str = "novel"
    mode: str = "automatic"  # automatic | manual_review
    shot_duration: float = 5.0
    width: int = 1080
    height: int = 1920
    fps: int = 24
    options: dict[str, Any] = Field(default_factory=dict)
    idempotency_key: str = ""


class JobCommandRequest(BaseModel):
    command: JobCommand
    step_id: str | None = None
    comment: str = ""
    patch: dict[str, Any] = Field(default_factory=dict)
    confirm_invalidated_step_ids: list[str] = Field(default_factory=list)


class RetryRequest(BaseModel):
    step_id: str | None = None
    comment: str = ""


class ReviewRequest(BaseModel):
    action: Literal["approve", "edit", "retry", "rollback"]
    comment: str = ""
    patch: dict[str, Any] = Field(default_factory=dict)


StageExecutionMode = Literal["rerun_node", "continue"]


class StageExecutionRequest(BaseModel):
    stage_key: str = Field(min_length=1)
    shot_id: str = ""
    mode: StageExecutionMode


class RollbackPreview(BaseModel):
    step_id: str
    invalidated_step_ids: list[str]


class JobSummary(BaseModel):
    id: str
    project_id: str
    status: JobStatus
    mode: str
    desired_state: str
    current_stage: str
    current_shot: str
    progress: float
    message: str
    final_video: str
    created_at: str
    updated_at: str
    finished_at: str | None = None

    class Config:
        from_attributes = True


class StepInfo(BaseModel):
    id: str
    stage_key: str
    shot_id: str | None = None
    status: str
    attempt: int
    progress: float
    error_code: str
    error_message: str
    quality_attempt: int = 0
    ui_stage_key: str = ""
    quality_report: dict[str, Any] = Field(default_factory=dict)
    started_at: str | None = None
    finished_at: str | None = None

    class Config:
        from_attributes = True


class ArtifactInfo(BaseModel):
    id: int | None = None
    project_id: str = ""
    kind: str
    path: str
    sha256: str
    stage_key: str = ""
    scene_id: str = ""
    shot_id: str = ""
    version: int = 1
    parent_artifact_id: int | None = None
    active: bool = True
    quality_status: str = "unreviewed"
    metadata: dict[str, Any] = Field(default_factory=dict)
    media_url: str = ""

    class Config:
        from_attributes = True


class JobDetail(JobSummary):
    steps: list[StepInfo] = Field(default_factory=list)
    artifacts: list[ArtifactInfo] = Field(default_factory=list)

    class Config:
        from_attributes = True


class JobListResponse(BaseModel):
    items: list[JobSummary]


# ---------------------------------------------------------------------------
# Phase 10.7-A: Production task queue schemas
# ---------------------------------------------------------------------------


class TaskType(str, Enum):
    IMAGE_GENERATION = "image_generation"
    VIDEO_GENERATION = "video_generation"
    VIDEO_CHAIN = "video_chain"


class RetryPolicy(BaseModel):
    max_attempts: int = 3
    backoff_seconds: float = 2.0


class TaskCreate(BaseModel):
    task_type: TaskType
    project_id: str = "default"
    priority: int = 0
    retry_policy: RetryPolicy = Field(default_factory=RetryPolicy)
    checkpoint_id: str = ""
    payload: dict[str, Any] = Field(default_factory=dict)


class TaskInfo(BaseModel):
    task_id: str
    task_type: str
    project_id: str
    priority: int
    retry_policy: dict[str, Any] = Field(default_factory=dict)
    checkpoint_id: str = ""
    status: str
    attempts: int
    worker_id: str = ""
    shot_id: str = ""
    stage: str = ""
    progress: float = 0.0
    gpu_time_s: float = 0.0
    checkpoint: dict[str, Any] = Field(default_factory=dict)
    error: str = ""
    result: dict[str, Any] = Field(default_factory=dict)
    created_at: str = ""
    updated_at: str = ""
    finished_at: str = ""


class TaskListResponse(BaseModel):
    items: list[TaskInfo]
    total: int
