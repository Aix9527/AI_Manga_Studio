"""Version Registry (Phase 12.9-A, GPT spec).

Tracks every versioned component of a production release: pipeline, director,
policy, model, workflow.  Deterministic, JSON-backed, single source of truth
for the release manager and the audit chain.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from threading import RLock
from typing import Any


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


class VersionRegistry:
    """JSON-backed registry of component versions."""

    def __init__(self, path: str | Path = "storage/governance/version_registry.json"):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = RLock()
        self._data: dict = self._load()

    def _load(self) -> dict:
        if not self.path.exists():
            return {"components": {}, "releases": []}
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {"components": {}, "releases": []}
        except Exception:  # noqa: BLE001
            return {"components": {}, "releases": []}

    def _save(self) -> None:
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self._data, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(self.path)

    # ---------------------------------------------------------- components
    def set_component(self, name: str, version: str, detail: dict | None = None) -> dict:
        with self._lock:
            entry = {
                "name": name,
                "version": version,
                "detail": detail or {},
                "updated_at": _now(),
            }
            self._data.setdefault("components", {})[name] = entry
            self._save()
            return entry

    def get_component(self, name: str) -> dict | None:
        with self._lock:
            return (self._data.get("components") or {}).get(name)

    def components(self) -> dict:
        with self._lock:
            return dict(self._data.get("components") or {})

    # ---------------------------------------------------------- releases
    def create_release(self, release_id: str, components: dict[str, str], meta: dict | None = None) -> dict:
        with self._lock:
            record = {
                "release_id": release_id,
                "components": components,
                "meta": meta or {},
                "created_at": _now(),
            }
            self._data.setdefault("releases", []).append(record)
            self._save()
            return record

    def releases(self) -> list[dict]:
        with self._lock:
            return list(self._data.get("releases") or [])

    def summary(self) -> dict:
        with self._lock:
            return {
                "components": self.components(),
                "releases": len(self._data.get("releases") or []),
            }
