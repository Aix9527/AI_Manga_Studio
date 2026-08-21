"""Asset Feedback Loop stores (Phase 13.4-C) — JSON persistence."""

from __future__ import annotations

import json
import threading
from pathlib import Path

from backend.feedback.model import AssetCandidate, FeedbackEvent

_ROOT = "storage/feedback"


class _JsonStore:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._data: dict[str, dict] = self._load()

    def _load(self) -> dict[str, dict]:
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

    def get(self, key: str) -> dict | None:
        with self._lock:
            raw = self._data.get(key)
        return dict(raw) if raw else None

    def all(self) -> list[dict]:
        with self._lock:
            return [dict(raw) for raw in self._data.values()]

    def put(self, key: str, value: dict) -> dict:
        with self._lock:
            self._data[key] = value
            self._save()
        return value


class FeedbackStore:
    def __init__(self, root: str | Path = _ROOT):
        root = Path(root)
        self.events = _JsonStore(root / "events.json")
        self.candidates = _JsonStore(root / "candidates.json")
        self.shot_stats = _JsonStore(root / "shot_stats.json")

    def put_event(self, event: FeedbackEvent) -> FeedbackEvent:
        self.events.put(event.id, event.to_dict())
        return event

    def list_events(self, *, target_type: str | None = None, target_id: str | None = None, kind: str | None = None) -> list[FeedbackEvent]:
        rows = [FeedbackEvent.from_dict(r) for r in self.events.all()]
        if target_type:
            rows = [r for r in rows if r.target_type == target_type]
        if target_id:
            rows = [r for r in rows if r.target_id == target_id]
        if kind:
            rows = [r for r in rows if r.kind == kind]
        return sorted(rows, key=lambda r: r.created_at, reverse=True)

    def put_candidate(self, candidate: AssetCandidate) -> AssetCandidate:
        self.candidates.put(candidate.id, candidate.to_dict())
        return candidate

    def get_candidate(self, candidate_id: str) -> AssetCandidate | None:
        raw = self.candidates.get(candidate_id)
        return AssetCandidate.from_dict(raw) if raw else None

    def list_candidates(self, *, status: str | None = None) -> list[AssetCandidate]:
        rows = [AssetCandidate.from_dict(r) for r in self.candidates.all()]
        if status:
            rows = [r for r in rows if r.status == status]
        return sorted(rows, key=lambda r: r.created_at, reverse=True)

    def pending_candidate(self, target_type: str, target_id: str) -> AssetCandidate | None:
        for candidate in self.list_candidates(status="proposed"):
            if candidate.target_type == target_type and candidate.target_id == target_id:
                return candidate
        return None