from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Dict, Any

from .ids import create_id, utc_now


@dataclass
class DomainEntity:

    id: str
    created_at: str
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class Project(DomainEntity):

    name: str = ""
    content_type: str = "anime"

    aspect_ratio: str = "9:16"

    resolution: str = "1080x1920"

    quality_strategy: str = "balanced"

    local_only: bool = True


@dataclass
class Season(DomainEntity):

    project_id: str = ""

    name: str = ""

    episode_start: int = 1

    episode_end: int = 100


@dataclass
class Episode(DomainEntity):

    season_id: str = ""

    title: str = ""

    target_duration_seconds: int = 60


@dataclass
class Scene(DomainEntity):

    episode_id: str = ""

    location: str = ""

    time_state: str = ""

    weather: str = ""


@dataclass
class Shot(DomainEntity):

    scene_id: str = ""

    shot_type: str = ""

    camera_move: str = ""

    duration_seconds: float = 5.0

    status: str = "draft"


@dataclass
class Asset(DomainEntity):

    project_id: str = ""

    asset_type: str = ""

    name: str = ""


@dataclass
class AssetVersion(DomainEntity):

    asset_id: str = ""

    version: int = 1

    content_hash: str = ""

    file_path: str = ""

    status: str = "created"


def new_project(name: str) -> Project:

    return Project(
        id=create_id("project"),
        created_at=str(utc_now()),
        name=name
    )
