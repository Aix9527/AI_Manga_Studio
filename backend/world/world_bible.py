"""World Bible (Phase 13.1, GPT spec).

world:
  era, technology, civilization, power_system, physics_rules,
  visual_style, color_language
"""

from __future__ import annotations

import json
import threading
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


@dataclass
class WorldBible:
    id: str
    project_id: str = ""
    name: str = ""
    era: str = ""
    technology: str = ""
    civilization: str = ""
    power_system: str = ""
    physics_rules: list[str] = field(default_factory=list)
    visual_style: str = ""
    color_language: str = ""
    description: str = ""
    created_at: str = field(default_factory=_now)
    updated_at: str = field(default_factory=_now)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "WorldBible":
        known = {f.name for f in cls.__dataclass_fields__.values()}
        return cls(**{k: v for k, v in data.items() if k in known})


class WorldBibleStore:
    def __init__(self, root: str | Path = "storage/world"):
        self.path = Path(root) / "worlds.json"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._data: dict[str, dict] = self._load()

    def _load(self) -> dict:
        if not self.path.exists():
            return {}
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            return {}

    def _save(self) -> None:
        with self._lock:
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps(self._data, ensure_ascii=False, indent=2), encoding="utf-8")
            tmp.replace(self.path)

    def put(self, world: WorldBible) -> WorldBible:
        with self._lock:
            self._data[world.id] = world.to_dict()
            self._save()
        return world

    def get(self, world_id: str) -> WorldBible | None:
        with self._lock:
            raw = self._data.get(world_id)
        return WorldBible.from_dict(raw) if raw else None

    def by_project(self, project_id: str) -> list[WorldBible]:
        with self._lock:
            rows = [WorldBible.from_dict(r) for r in self._data.values() if r.get("project_id") == project_id]
        return sorted(rows, key=lambda w: w.updated_at, reverse=True)

    def all(self) -> list[WorldBible]:
        with self._lock:
            return [WorldBible.from_dict(r) for r in self._data.values()]

    def delete(self, world_id: str) -> bool:
        with self._lock:
            existed = world_id in self._data
            if existed:
                del self._data[world_id]
                self._save()
        return existed
