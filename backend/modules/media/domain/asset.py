
"""Media asset domain."""

from dataclasses import dataclass, field
from datetime import datetime


@dataclass(slots=True)
class Asset:
    asset_id: str
    project_id: str
    name: str
    mime_type: str = ""
    file_size: int = 0
    tags: list[str] = field(default_factory=list)
    current_version_id: str | None = None
    created_at: datetime = field(default_factory=lambda: datetime.utcnow())
    updated_at: datetime = field(default_factory=lambda: datetime.utcnow())
    revision: int = 1


@dataclass(slots=True)
class AssetVersion:
    version_id: str
    asset_id: str
    version_number: int
    content_hash: str
    relative_path: str
    mime_type: str = ""
    file_size: int = 0
    metadata_json: str = "{}"
    provenance_json: str = "{}"
    created_at: datetime = field(default_factory=lambda: datetime.utcnow())
