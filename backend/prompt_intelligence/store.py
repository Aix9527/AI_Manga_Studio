"""Prompt Intelligence stores (Phase 13.4-A) — JSON persistence.

Mirrors the storage style of World / Shot DNA stores:
templates.json + versions.json + reviews.json + ab_tests.json under
storage/prompt_intelligence/.
"""

from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any

from backend.prompt_intelligence.model import (
    PromptABTest,
    PromptReview,
    PromptTemplate,
    PromptVersion,
)

_ROOT = "storage/prompt_intelligence"


def _read_json(path: Path) -> dict[str, dict]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return {}


class _JsonStore:
    """Thread-safe dict-of-dicts JSON store."""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._data: dict[str, dict] = _read_json(self.path)

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

    def delete(self, key: str) -> bool:
        with self._lock:
            existed = key in self._data
            if existed:
                del self._data[key]
                self._save()
        return existed


class PromptTemplateStore:
    def __init__(self, root: str | Path = _ROOT):
        root = Path(root)
        self.templates = _JsonStore(root / "templates.json")
        self.versions = _JsonStore(root / "versions.json")
        self.reviews = _JsonStore(root / "reviews.json")
        self.ab_tests = _JsonStore(root / "ab_tests.json")

    # ------------------------------------------------------------- templates
    def put_template(self, template: PromptTemplate) -> PromptTemplate:
        self.templates.put(template.id, template.to_dict())
        return template

    def get_template(self, template_id: str) -> PromptTemplate | None:
        raw = self.templates.get(template_id)
        return PromptTemplate.from_dict(raw) if raw else None

    def list_templates(self) -> list[PromptTemplate]:
        return [PromptTemplate.from_dict(r) for r in self.templates.all()]

    # ------------------------------------------------------------- versions
    def put_version(self, version: PromptVersion) -> PromptVersion:
        self.versions.put(self._version_key(version.template_id, version.version_id), version.to_dict())
        return version

    def get_version(self, template_id: str, version_id: str) -> PromptVersion | None:
        raw = self.versions.get(self._version_key(template_id, version_id))
        return PromptVersion.from_dict(raw) if raw else None

    def list_versions(self, template_id: str) -> list[PromptVersion]:
        rows = [
            PromptVersion.from_dict(r)
            for r in self.versions.all()
            if r.get("template_id") == template_id
        ]
        return sorted(rows, key=lambda v: self._version_sort_key(v.version_id))

    @staticmethod
    def _version_key(template_id: str, version_id: str) -> str:
        return f"{template_id}::{version_id}"

    @staticmethod
    def _version_sort_key(version_id: str) -> tuple[int, int]:
        digits = "".join(ch for ch in version_id if ch.isdigit())
        return (len(digits), int(digits or 0))

    # ------------------------------------------------------------- reviews
    def put_review(self, review: PromptReview) -> PromptReview:
        self.reviews.put(review.id, review.to_dict())
        return review

    def get_review(self, review_id: str) -> PromptReview | None:
        raw = self.reviews.get(review_id)
        return PromptReview.from_dict(raw) if raw else None

    def list_reviews(self, template_id: str | None = None) -> list[PromptReview]:
        rows = [
            PromptReview.from_dict(r)
            for r in self.reviews.all()
            if template_id is None or r.get("template_id") == template_id
        ]
        return sorted(rows, key=lambda r: r.created_at, reverse=True)

    # ------------------------------------------------------------- ab tests
    def put_ab_test(self, ab_test: PromptABTest) -> PromptABTest:
        self.ab_tests.put(ab_test.id, ab_test.to_dict())
        return ab_test

    def get_ab_test(self, ab_id: str) -> PromptABTest | None:
        raw = self.ab_tests.get(ab_id)
        return PromptABTest.from_dict(raw) if raw else None

    def list_ab_tests(self) -> list[PromptABTest]:
        rows = [PromptABTest.from_dict(r) for r in self.ab_tests.all()]
        return sorted(rows, key=lambda t: t.created_at, reverse=True)