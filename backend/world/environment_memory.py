"""Environment memory (Phase 13.1, GPT spec).

Remembers environment constraints per project so the director never breaks
world rules: forbidden elements, continuity notes, physics rules enforced.
"""

from __future__ import annotations

import json
import threading
from datetime import datetime
from pathlib import Path
from typing import Any


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


class EnvironmentMemory:
    def __init__(self, root: str | Path = "storage/world"):
        self.path = Path(root) / "environment_memory.json"
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

    def note(self, project_id: str, entry: dict) -> None:
        with self._lock:
            self._data.setdefault(project_id, {"entries": [], "updated_at": _now()})
            record = dict(entry)
            record["created_at"] = _now()
            self._data[project_id]["entries"].append(record)
            self._data[project_id]["updated_at"] = _now()
            self._save()

    def constraints(self, project_id: str) -> list[dict]:
        with self._lock:
            return list(self._data.get(project_id, {}).get("entries", []))

    def summary(self, project_id: str) -> dict:
        with self._lock:
            data = self._data.get(project_id, {})
            entries = data.get("entries", [])
            kinds: dict[str, int] = {}
            for entry in entries:
                kinds[entry.get("kind", "note")] = kinds.get(entry.get("kind", "note"), 0) + 1
            return {
                "project_id": project_id,
                "entries": len(entries),
                "by_kind": kinds,
                "updated_at": data.get("updated_at", ""),
            }
