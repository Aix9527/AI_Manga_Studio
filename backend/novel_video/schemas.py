"""Strict transport contracts for the formal novel-to-video API.

The service accepts these contracts directly as well as from FastAPI routes.
They deliberately have no provider side effects: a cloud field is merely a
declaration and is rejected unless the project explicitly permits cloud use.
"""
from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from backend.novel_video.models import AspectRatio, ProductionMode, RunCommand, RunStatus, VisualStyle


_SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")


class _StrictSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ProjectCreateRequest(_StrictSchema):
    id: str
    name: str = Field(min_length=1, max_length=160)
    mode: ProductionMode = ProductionMode.ONE_CLICK
    style: VisualStyle = VisualStyle.ANIME
    aspect_ratio: AspectRatio = AspectRatio.LANDSCAPE
    width: int = Field(default=864, gt=0, multiple_of=32)
    height: int = Field(default=480, gt=0, multiple_of=32)
    megapixel_profile: float = Field(default=0.4, gt=0)
    multiple: int = Field(default=32, gt=0)
    target_duration_seconds: int = Field(default=60, ge=15)
    max_shots: int = Field(default=10, ge=1)
    base_seed: int = 20260812
    primary_video_engine: str = Field(default="minimax_h3_ref2va", min_length=1)
    allow_wan_fallback: bool = False
    allow_cloud: bool = False
    cloud_provider: str | None = None
    cloud_authorization_id: str | None = None

    @field_validator("id", "cloud_authorization_id")
    @classmethod
    def safe_identifiers(cls, value: str | None) -> str | None:
        if value is not None and not _SAFE_ID.fullmatch(value):
            raise ValueError("identifier must be safe (letters, numbers, '_' and '-')")
        return value

    @model_validator(mode="after")
    def compatible_project_settings(self) -> "ProjectCreateRequest":
        if self.width % self.multiple or self.height % self.multiple:
            raise ValueError("width and height must be divisible by multiple")
        landscape = self.width > self.height
        if (self.aspect_ratio is AspectRatio.LANDSCAPE and not landscape) or (
            self.aspect_ratio is AspectRatio.PORTRAIT and self.height <= self.width
        ):
            raise ValueError("aspect ratio and dimensions have incompatible orientation")
        if not self.allow_cloud and (self.cloud_provider or self.cloud_authorization_id):
            raise ValueError("cloud provider fields require allow_cloud=true")
        if self.allow_cloud and self.cloud_provider and not self.cloud_authorization_id:
            raise ValueError("cloud provider requires a concrete cloud authorization")
        return self


class SourceImportResponse(_StrictSchema):
    project_id: str
    asset_id: str
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    encoding: str
    chapter_count: int = Field(ge=1)


class ChapterSelectionRequest(_StrictSchema):
    chapter_indexes: list[int] = Field(min_length=1)
    target_seconds: float = Field(default=60, ge=5)
    max_shots: int | None = Field(default=None, ge=1)
    provider: str = "local"

    @field_validator("chapter_indexes")
    @classmethod
    def ordered_unique_chapters(cls, value: list[int]) -> list[int]:
        if any(index < 1 for index in value) or len(set(value)) != len(value):
            raise ValueError("chapter indexes must be positive and unique")
        return value


class PreflightResponse(_StrictSchema):
    ready: bool
    blockers: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class RunCreateRequest(_StrictSchema):
    plan_id: str
    mode: ProductionMode | None = None

    @field_validator("plan_id")
    @classmethod
    def safe_plan_id(cls, value: str) -> str:
        if not _SAFE_ID.fullmatch(value):
            raise ValueError("plan id must be safe")
        return value


class RunDetailResponse(_StrictSchema):
    id: str
    project_id: str
    chapter_indexes: list[int]
    mode: ProductionMode
    status: RunStatus
    review_gate: str | None = None
    message: str = ""
    created_at: datetime
    updated_at: datetime


class CommandRequest(_StrictSchema):
    command: RunCommand


class EmptyRequest(_StrictSchema):
    """A deliberately closed request body for command endpoints."""


class AssetApprovalRequest(_StrictSchema):
    approve_tail: bool = False


class VisualQAResult(_StrictSchema):
    score: float = Field(ge=0, le=1)
    reason: str = Field(min_length=1, max_length=2000)
    reviewer: str = Field(min_length=1, max_length=100)
    version: str = Field(min_length=1, max_length=100)
    evidence_asset_ids: list[str] = Field(min_length=1, max_length=20)

    @field_validator("evidence_asset_ids")
    @classmethod
    def safe_evidence_ids(cls, value: list[str]) -> list[str]:
        if len(set(value)) != len(value) or any(not _SAFE_ID.fullmatch(item) for item in value):
            raise ValueError("evidence asset ids must be unique safe identifiers")
        return value


class ShotReviewRequest(_StrictSchema):
    approve: bool
    candidate_video_id: str
    candidate_tail_id: str
    qa: VisualQAResult | None = None

    @model_validator(mode="after")
    def approval_needs_visual_qa(self) -> "ShotReviewRequest":
        if self.approve and self.qa is None:
            raise ValueError("approval requires visual QA evidence")
        return self


class EventPageResponse(_StrictSchema):
    events: list[dict[str, Any]]
    next_sequence: int | None = None
