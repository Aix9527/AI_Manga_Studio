import json
from collections.abc import Mapping
from datetime import datetime, timedelta, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from backend.novel_video.h3_frames import legal_h3_frames


class _FrozenDict(dict[str, Any]):
    """JSON-compatible mapping whose contents cannot change after validation."""

    @staticmethod
    def _immutable(*args, **kwargs):
        raise TypeError("metadata is immutable")

    __setitem__ = _immutable
    __delitem__ = _immutable
    clear = _immutable
    pop = _immutable
    popitem = _immutable
    setdefault = _immutable
    update = _immutable
    __ior__ = _immutable


def _metadata_sort_key(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def _freeze_metadata(value: Any) -> Any:
    if isinstance(value, Mapping):
        return _FrozenDict(
            (key, _freeze_metadata(item)) for key, item in sorted(value.items())
        )
    if isinstance(value, (list, tuple)):
        return tuple(_freeze_metadata(item) for item in value)
    if isinstance(value, (set, frozenset)):
        frozen_items = [_freeze_metadata(item) for item in value]
        return tuple(sorted(frozen_items, key=_metadata_sort_key))
    return value


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class _UTCDateTimeModel(BaseModel):
    @field_validator(
        "created_at", "updated_at", "lease_expires_at", check_fields=False
    )
    @classmethod
    def utc_timestamps_only(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return value
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("timestamp must be timezone-aware")
        if value.utcoffset() != timedelta(0):
            raise ValueError("timestamp must use a UTC offset of zero")
        return value


class ProductionMode(str, Enum):
    ONE_CLICK = "one_click"
    PROFESSIONAL = "professional"


class VisualStyle(str, Enum):
    ANIME = "anime"
    LIVE_ACTION = "live_action"


class AspectRatio(str, Enum):
    LANDSCAPE = "16:9"
    PORTRAIT = "9:16"


class RunStatus(str, Enum):
    DRAFT = "draft"
    PLANNING = "planning"
    AWAITING_REVIEW = "awaiting_review"
    RENDERING = "rendering"
    MIXING = "mixing"
    VALIDATING = "validating"
    PAUSED = "paused"
    INTERRUPTED = "interrupted"
    BLOCKED = "blocked"
    CANCELLED = "cancelled"
    COMPLETED = "completed"


class ShotStatus(str, Enum):
    DRAFT = "draft"
    LOCKED = "locked"
    QUEUED = "queued"
    RUNNING = "running"
    VALIDATING = "validating"
    APPROVED = "approved"
    INCLUDED = "included"
    FAILED = "failed"
    BLOCKED = "blocked"


class RunCommand(str, Enum):
    START = "start"
    PAUSE = "pause"
    RESUME = "resume"
    CANCEL = "cancel"
    RETRY = "retry"


class H3ReferencePackage(BaseModel):
    shot_id: str = Field(min_length=1)
    prompt_version: str
    prompt_text: str
    negative_prompt: str = ""
    base_seed: int
    effective_seed: int
    duration_seconds: float = Field(ge=5, le=15)
    fps: Literal[24] = 24
    legal_frame_count: int
    width: int = Field(gt=0)
    height: int = Field(gt=0)
    aspect_ratio: AspectRatio
    megapixel_profile: float = Field(default=0.4, gt=0)
    multiple: int = Field(default=32, gt=0)
    picture_asset_version_ids: list[str] = Field(default_factory=list, max_length=3)
    video_reference_asset_version_ids: list[str]
    audio_reference_asset_version_ids: list[str]
    workflow_version: str
    model_registry_ids: dict[str, str] = Field(default_factory=dict)
    continuity_reason: str = ""
    actual_duration_seconds: float | None = Field(default=None, gt=0)

    @field_validator("legal_frame_count")
    @classmethod
    def legal_h3_frames(cls, value: int) -> int:
        if value < 5 or (value - 5) % 17:
            raise ValueError("H3 frame count must satisfy 17n+5")
        return value

    @model_validator(mode="after")
    def validate_traceability_contract(self) -> "H3ReferencePackage":
        nearest_legal_frame_count = legal_h3_frames(
            self.duration_seconds, self.fps
        )
        if self.legal_frame_count != nearest_legal_frame_count:
            raise ValueError(
                "legal_frame_count must be the nearest legal 17n+5 frame count "
                f"({nearest_legal_frame_count})"
            )
        if self.width % self.multiple or self.height % self.multiple:
            raise ValueError("width and height must be divisible by multiple")
        is_landscape = self.width > self.height
        if (
            self.aspect_ratio is AspectRatio.LANDSCAPE and not is_landscape
        ) or (
            self.aspect_ratio is AspectRatio.PORTRAIT and self.height <= self.width
        ):
            raise ValueError("aspect ratio does not match width/height orientation")
        return self


class GenerationIdentity(BaseModel):
    """The one immutable identity for a queued formal generation attempt.

    H3's provider prompt binding deliberately uses only the first four keys;
    the package hash remains a scheduler/repository asset-lineage fact.
    """

    task_id: str = Field(min_length=1)
    run_id: str = Field(min_length=1)
    shot_id: str = Field(min_length=1)
    attempt_id: str = Field(min_length=1)
    package_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    def canonical(self) -> dict[str, str]:
        return self.model_dump(mode="json")

    def provider_binding(self) -> dict[str, str]:
        return {key: getattr(self, key) for key in ("task_id", "run_id", "shot_id", "attempt_id")}

    def package_binding(self) -> dict[str, str]:
        return {key: getattr(self, key) for key in ("run_id", "shot_id", "package_sha256")}


class NovelVideoProject(_UTCDateTimeModel):
    id: str
    name: str
    root: Path
    owner_principal: str = "local"
    mode: ProductionMode = ProductionMode.ONE_CLICK
    style: VisualStyle = VisualStyle.ANIME
    aspect_ratio: AspectRatio = AspectRatio.LANDSCAPE
    width: int = Field(default=864, gt=0)
    height: int = Field(default=480, gt=0)
    megapixel_profile: float = Field(default=0.4, gt=0)
    multiple: int = Field(default=32, gt=0)
    target_duration_seconds: int = Field(default=60, ge=15)
    max_shots: int = Field(default=10, ge=1)
    base_seed: int = 20260812
    primary_video_engine: str = "minimax_h3_ref2va"
    allow_wan_fallback: bool = False
    allow_cloud: bool = False
    source_asset_version_id: str | None = None
    created_at: datetime = Field(default_factory=_utc_now)
    updated_at: datetime = Field(default_factory=_utc_now)


class ProductionRun(_UTCDateTimeModel):
    id: str
    project_id: str
    chapter_indexes: list[int]
    mode: ProductionMode
    status: RunStatus = RunStatus.DRAFT
    review_gate: str | None = None
    comfy_prompt_id: str | None = None
    lease_id: str | None = None
    lease_expires_at: datetime | None = None
    export_asset_id: str | None = None
    message: str = ""
    settings: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=_utc_now)
    updated_at: datetime = Field(default_factory=_utc_now)


class ShotRecord(_UTCDateTimeModel):
    id: str
    run_id: str
    chapter_id: str
    sequence: int = Field(ge=1)
    status: ShotStatus = ShotStatus.DRAFT
    plan: dict[str, Any] = Field(default_factory=dict)
    reference_package: H3ReferencePackage | None = None
    approved_video_asset_id: str | None = None
    approved_tail_asset_id: str | None = None
    current_attempt: int = 0
    retry_nonce: int = 0
    created_at: datetime = Field(default_factory=_utc_now)
    updated_at: datetime = Field(default_factory=_utc_now)


class AssetVersion(_UTCDateTimeModel):
    model_config = ConfigDict(frozen=True)

    id: str
    project_id: str
    run_id: str
    shot_id: str | None = None
    parent_id: str | None = None
    kind: str
    state: Literal["candidate", "approved", "rejected"] = "candidate"
    path: Path
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=_utc_now)

    @field_validator("metadata", mode="after")
    @classmethod
    def immutable_metadata(cls, value: dict[str, Any]) -> dict[str, Any]:
        return _freeze_metadata(value)


class RunEvent(_UTCDateTimeModel):
    run_id: str
    event_type: str
    payload: dict[str, Any] = Field(default_factory=dict)
    sequence: int | None = None
    created_at: datetime = Field(default_factory=_utc_now)
