"""Location registry (Phase 13.1, GPT spec)."""

from __future__ import annotations

import json
import threading
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


@dataclass
class Location:
    id: str
    project_id: str = ""
    world_id: str = ""
    name: str = ""
    description: str = ""
    geography: str = ""
    architecture: str = ""
    landmarks: list[str] = field(default_factory=list)
    connected_to: list[str] = field(default_factory=list)
    created_at: str = field(default_factory=_now)
    updated_at: str = field(default_factory=_now)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "Location":
        known = {f.name for f in cls.__dataclass_fields__.values()}
        return cls(**{k: v for k, v in data.items() if k in known})


class LocationStore:
    def __init__(self, root: str | Path = "storage/world"):
        self.path = Path(root) / "locations.json"
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

    def put(self, location: Location) -> Location:
        with self._lock:
            self._data[location.id] = location.to_dict()
            self._save()
        return location

    def get(self, location_id: str) -> Location | None:
        with self._lock:
            raw = self._data.get(location_id)
        return Location.from_dict(raw) if raw else None

    def by_project(self, project_id: str) -> list[Location]:
        with self._lock:
            rows = [Location.from_dict(r) for r in self._data.values() if r.get("project_id") == project_id]
        return sorted(rows, key=lambda loc: loc.updated_at, reverse=True)

    def all(self) -> list[Location]:
        with self._lock:
            return [Location.from_dict(r) for r in self._data.values()]

    def delete(self, location_id: str) -> bool:
        with self._lock:
            existed = location_id in self._data
            if existed:
                del self._data[location_id]
                self._save()
        return existed
