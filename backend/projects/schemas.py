from __future__ import annotations

from typing import Any, Literal

from pydantic import Field, field_validator, model_validator

from backend.orchestration.schemas import FiniteJsonRequest


class ProjectCreate(FiniteJsonRequest):
    name: str = Field(min_length=1, max_length=128)
    description: str = Field(default='', max_length=2000)
    mode: Literal['automatic', 'manual_review'] = 'automatic'
    target_duration_seconds: int = Field(default=60, ge=30, le=90)
    width: int = Field(default=1080, ge=256, le=8192)
    height: int = Field(default=1920, ge=256, le=8192)
    fps: int = Field(default=24, ge=8, le=60)

    @field_validator('name')
    @classmethod
    def trim_name(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError('project name cannot be blank')
        return cleaned


class SourceCreate(FiniteJsonRequest):
    kind: Literal['idea', 'document', 'video', 'url']
    original_name: str = Field(min_length=1, max_length=512)
    original_location: str = Field(min_length=1, max_length=8192)
    managed_path: str = ''
    sha256: str = Field(default='', pattern=r'^$|^[0-9a-f]{64}$')
    rights_confirmed: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode='after')
    def require_rights_confirmation_for_url(self) -> 'SourceCreate':
        if self.kind == 'url' and not self.rights_confirmed:
            raise ValueError('URL sources require rights confirmation')
        return self
