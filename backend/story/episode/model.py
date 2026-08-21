"""Episode data model (Phase 13.1, GPT spec)."""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Any


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


@dataclass
class Episode:
    """One short-drama episode with the full production lifecycle."""

    id: str
    project_id: str
    episode_no: int = 1
    season: int = 1
    title: str = ""
    status: str = "draft"
    hook: str = ""
    conflict: str = ""
    climax: str = ""
    ending: str = ""
    retention_strategy: str = ""
    script_version: str = ""
    storyboard_version: str = ""
    production_progress: float = 0.0
    created_at: str = field(default_factory=_now)
    updated_at: str = field(default_factory=_now)
    approved_at: str = ""
    published_at: str = ""
    meta: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "Episode":
        known = {f.name for f in cls.__dataclass_fields__.values()}
        return cls(**{k: v for k, v in data.items() if k in known})
