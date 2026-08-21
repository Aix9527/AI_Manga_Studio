"""Audit Log (Phase 12.9-A, GPT spec).

Append-only trace of every governance action (release, approval, rollback,
sign, certification).  Entries are never mutated or removed so the release
can always be audited end-to-end.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime
from pathlib import Path
from threading import RLock


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


class AuditLog:
    """Append-only JSON audit trail."""

    def __init__(self, path: str | Path = "storage/governance/audit_log.json"):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = RLock()
        self._entries: list[dict] = self._load()

    def _load(self) -> list[dict]:
        if not self.path.exists():
            return []
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            return data if isinstance(data, list) else []
        except Exception:  # noqa: BLE001
            return []

    def _save(self) -> None:
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self._entries, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(self.path)

    def record(self, action: str, detail: dict) -> dict:
        with self._lock:
            entry = {
                "id": f"AUD-{uuid.uuid4().hex[:10]}",
                "action": action,
                "created_at": _now(),
                "detail": detail,
            }
            self._entries.append(entry)
            self._save()
            return entry

    def entries(self) -> list[dict]:
        with self._lock:
            return list(self._entries)

    def filter(self, action: str | None = None) -> list[dict]:
        with self._lock:
            entries = self._entries
            if action:
                entries = [e for e in entries if e["action"] == action]
            return list(entries)
