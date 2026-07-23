
"""Character domain aggregate."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass(slots=True)
class Character:
    character_id: str
    project_id: str
    name: str
    role: str = ""
    personality: str = ""
    background: str = ""
    appearance: dict[str, Any] = field(default_factory=dict)
    current_version_id: str | None = None
    is_active: bool = True
    created_at: datetime = field(default_factory=lambda: datetime.utcnow())
    updated_at: datetime = field(default_factory=lambda: datetime.utcnow())
    revision: int = 1


@dataclass(slots=True)
class CharacterVersion:
    version_id: str
    character_id: str
    version_number: int
    snapshot_json: str
    change_description: str = ""
    created_at: datetime = field(default_factory=lambda: datetime.utcnow())
