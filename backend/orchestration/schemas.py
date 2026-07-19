from __future__ import annotations

import math
from datetime import datetime
from typing import Any, Literal
from unicodedata import category

from pydantic import BaseModel, Field, field_validator, model_validator

from backend.orchestration.enums import JobStatus, StepStatus


InputType = Literal["novel", "script", "storyboard"]
JobMode = Literal["automatic", "manual_review"]
_WINDOWS_DEVICE_DIGIT_TRANSLATION = str.maketrans("¹²³", "123")


def _replace_non_finite_json(value: Any) -> bool:
    invalid = False
    if isinstance(value, dict):
        for key, item in value.items():
            if isinstance(item, float) and not math.isfinite(item):
                value[key] = None
                invalid = True
            else:
                invalid = _replace_non_finite_json(item) or invalid
    elif isinstance(value, list):
        for index, item in enumerate(value):
            if isinstance(item, float) and not math.isfinite(item):
                value[index] = None
                invalid = True
            else:
                invalid = _replace_non_finite_json(item) or invalid
    return invalid


def _require_finite_json(value: Any) -> Any:
    # FastAPI includes rejected input in its 422 body. Replace invalid numbers
    # before raising so that the validation response remains valid JSON.
    if _replace_non_finite_json(value):
        raise ValueError("JSON numbers must be finite")
    return value


class FiniteJsonRequest(BaseModel):
    @model_validator(mode="before")
    @classmethod
    def require_finite_json(cls, value: Any) -> Any:
        return _require_finite_json(value)


class JobCreate(FiniteJsonRequest):
    project_id: str = Field(min_length=1, max_length=128)
    input_path: str = Field(min_length=1)
    input_type: InputType
    mode: JobMode = "automatic"
    shot_duration: float = Field(default=5.0, ge=5.0, le=15.0)
    width: int = Field(default=1080, ge=256, le=8192)
    height: int = Field(default=1920, ge=256, le=8192)
    fps: int = Field(default=24, ge=8, le=60)
    options: dict[str, Any] = Field(default_factory=dict)
    idempotency_key: str = Field(min_length=8, max_length=128)

    @field_validator("width", "height")
    @classmethod
    def require_even_dimensions(cls, value: int) -> int:
        if value % 2:
            raise ValueError("video dimensions must be even")
        return value

    @field_validator("project_id", mode="before")
    @classmethod
    def trim_project_id(cls, value: Any) -> Any:
        if isinstance(value, str):
            if any(category(char) == "Cc" for char in value):
                raise ValueError("project name contains control characters")
            return value.strip()
        return value

    @field_validator("project_id")
    @classmethod
    def require_safe_project_folder(cls, value: str) -> str:
        cleaned = value
        forbidden = '<>:"/\\|?*'
        reserved = {
            "CON",
            "PRN",
            "AUX",
            "NUL",
            *(f"COM{i}" for i in range(1, 10)),
            *(f"LPT{i}" for i in range(1, 10)),
        }
        if (
            not cleaned
            or cleaned in {".", ".."}
            or any(char in forbidden for char in cleaned)
        ):
            raise ValueError("project name contains unsafe path characters")

        reserved_stem = (
            cleaned.split(".", 1)[0]
            .rstrip(" ")
            .upper()
            .translate(_WINDOWS_DEVICE_DIGIT_TRANSLATION)
        )
        if cleaned.rstrip(" .") != cleaned or reserved_stem in reserved:
            raise ValueError("project name is not a valid Windows folder")
        return cleaned


class JobStepView(BaseModel):
    id: str
    stage_key: str
    shot_id: str | None = None
    status: StepStatus
    attempt: int = Field(ge=0)
    progress: float = Field(ge=0.0, le=1.0)
    error_code: str = ""
    error_message: str = ""


class JobView(BaseModel):
    id: str
    project_id: str
    status: JobStatus
    mode: JobMode
    desired_state: str = Field(
        default="running",
        pattern=r"^(running|paused|cancelled)$",
    )
    current_stage: str = ""
    current_shot: str = ""
    progress: float = Field(default=0.0, ge=0.0, le=1.0)
    message: str = ""
    final_video: str = ""
    created_at: datetime
    updated_at: datetime
    steps: list[JobStepView] = Field(default_factory=list)


class JobAction(FiniteJsonRequest):
    step_id: str | None = None
    comment: str = ""


class RollbackAction(FiniteJsonRequest):
    step_id: str
    confirm_invalidated_step_ids: list[str]


class ReviewAction(FiniteJsonRequest):
    action: Literal["approve", "edit", "retry", "rollback"]
    comment: str = ""
    patch: dict[str, Any] = Field(default_factory=dict)
