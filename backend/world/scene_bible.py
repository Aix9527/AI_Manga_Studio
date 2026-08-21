"""Scene Bible (Phase 13.1, GPT spec).

scene:
  location, time, weather, architecture, camera_rules,
  lighting_rules, forbidden_elements
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
class SceneBible:
    id: str
    project_id: str = ""
    world_id: str = ""
    name: str = ""
    location: str = ""
    time: str = ""
    weather: str = ""
    architecture: str = ""
    camera_rules: list[str] = field(default_factory=list)
    lighting_rules: list[str] = field(default_factory=list)
    forbidden_elements: list[str] = field(default_factory=list)
    environment_prompt: str = ""
    reference_image: str = ""
    created_at: str = field(default_factory=_now)
    updated_at: str = field(default_factory=_now)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "SceneBible":
        known = {f.name for f in cls.__dataclass_fields__.values()}
        return cls(**{k: v for k, v in data.items() if k in known})


class SceneBibleStore:
    def __init__(self, root: str | Path = "storage/world"):
        self.path = Path(root) / "scenes.json"
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

    def put(self, scene: SceneBible) -> SceneBible:
        with self._lock:
            self._data[scene.id] = scene.to_dict()
            self._save()
        return scene

    def get(self, scene_id: str) -> SceneBible | None:
        with self._lock:
            raw = self._data.get(scene_id)
        return SceneBible.from_dict(raw) if raw else None

    def by_project(self, project_id: str) -> list[SceneBible]:
        with self._lock:
            rows = [SceneBible.from_dict(r) for r in self._data.values() if r.get("project_id") == project_id]
        return sorted(rows, key=lambda s: s.updated_at, reverse=True)

    def all(self) -> list[SceneBible]:
        with self._lock:
            return [SceneBible.from_dict(r) for r in self._data.values()]

    def delete(self, scene_id: str) -> bool:
        with self._lock:
            existed = scene_id in self._data
            if existed:
                del self._data[scene_id]
                self._save()
        return existed
