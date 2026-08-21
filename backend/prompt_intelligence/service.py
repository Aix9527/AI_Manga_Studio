"""Prompt Intelligence service (Phase 13.4-A, GPT spec).

Governs versioned prompt templates: create / version / diff / review /
approve / lock / A/B test, and composes Character / World / Shot prompts
against the frozen 13.1 data contracts (read-only consumption).
"""

from __future__ import annotations

import difflib
import hashlib
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from backend.prompt_intelligence.model import (
    AB_STATUSES,
    PromptABTest,
    PromptReview,
    PromptTemplate,
    PromptVersion,
    REVIEW_STATUSES,
    TEMPLATE_KINDS,
    VERSION_STATUSES,
)
from backend.prompt_intelligence.store import PromptTemplateStore


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _new_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:10]}"


class PromptIntelligenceService:
    """Version + review + approval + A/B governance for prompt templates."""

    def __init__(self, root: str | Path = "storage/prompt_intelligence"):
        self.store = PromptTemplateStore(root)

    # ------------------------------------------------------------- templates
    def create_template(
        self,
        name: str,
        kind: str = "generic",
        base_template: str = "",
        negative_prompt: str = "",
        quality_tags: str = "",
        variables: list[str] | None = None,
        description: str = "",
        version_id: str = "v1",
    ) -> dict:
        if kind not in TEMPLATE_KINDS:
            raise ValueError(f"invalid template kind: {kind} (allowed: {TEMPLATE_KINDS})")
        if not name.strip():
            raise ValueError("template name is required")
        for existing in self.store.list_templates():
            if existing.name == name:
                raise ValueError(f"template already exists: {name}")
        template = PromptTemplate(
            id=_new_id("PT"), name=name, kind=kind, description=description,
        )
        self.store.put_template(template)
        version = self._build_version(
            template.id, version_id, "", base_template, negative_prompt,
            quality_tags, variables or [], "",
        )
        self.store.put_version(version)
        return self.get_template(template.id)

    def get_template(self, template_id: str) -> dict:
        template = self.store.get_template(template_id)
        if not template:
            raise KeyError(f"template not found: {template_id}")
        return {
            **template.to_dict(),
            "versions": [v.to_dict() for v in self.store.list_versions(template_id)],
        }

    def list_templates(self, kind: str | None = None) -> list[dict]:
        rows = []
        for template in self.store.list_templates():
            if kind and template.kind != kind:
                continue
            rows.append(
                {
                    **template.to_dict(),
                    "versions": [v.to_dict() for v in self.store.list_versions(template.id)],
                }
            )
        return rows

    def delete_template(self, template_id: str) -> bool:
        """Rollback helper — removes a template and its version records."""
        template = self.store.get_template(template_id)
        if not template:
            return False
        for version in self.store.list_versions(template_id):
            self.store.versions.delete(self.store._version_key(template_id, version.version_id))
        for review in self.store.list_reviews(template_id):
            self.store.reviews.delete(review.id)
        return self.store.templates.delete(template_id)

    # ------------------------------------------------------------- versions
    def create_version(
        self,
        template_id: str,
        base_template: str,
        negative_prompt: str = "",
        quality_tags: str = "",
        variables: list[str] | None = None,
        notes: str = "",
        parent_version: str | None = None,
    ) -> dict:
        template = self.store.get_template(template_id)
        if not template:
            raise KeyError(f"template not found: {template_id}")
        versions = self.store.list_versions(template_id)
        if parent_version is None and versions:
            # default parent = current approved/locked version, else latest
            candidates = [v for v in versions if v.status in ("approved", "locked")]
            parent_version = (
                candidates[-1].version_id
                if candidates
                else versions[-1].version_id
            )
        next_id = self._next_version_id(versions)
        version = self._build_version(
            template_id, next_id, parent_version or "", base_template,
            negative_prompt, quality_tags, variables or [], notes,
        )
        self.store.put_version(version)
        return self.get_template(template_id)

    def set_version_status(
        self,
        template_id: str,
        version_id: str,
        status: str,
        approved_by: str = "human",
    ) -> dict:
        if status not in VERSION_STATUSES:
            raise ValueError(f"invalid status: {status} (allowed: {VERSION_STATUSES})")
        template = self.store.get_template(template_id)
        if not template:
            raise KeyError(f"template not found: {template_id}")
        version = self.store.get_version(template_id, version_id)
        if not version:
            raise KeyError(f"version not found: {template_id}/{version_id}")
        if status == "locked":
            if version.status != "approved":
                raise ValueError(f"cannot lock {version_id}: status is {version.status}, must be approved")
            template.active_version = version_id
        if status == "approved":
            version.approved_by = approved_by
            version.approved_at = _now()
        version.status = status
        version.updated_at = _now()
        self.store.put_version(version)
        self.store.put_template(template)
        return self.get_template(template_id)

    def diff_versions(self, template_id: str, version_a: str, version_b: str) -> dict:
        a = self.store.get_version(template_id, version_a)
        b = self.store.get_version(template_id, version_b)
        if not a or not b:
            raise KeyError(f"version not found: {template_id}/{version_a} or {version_b}")
        lines = list(
            difflib.unified_diff(
                a.content().splitlines(), b.content().splitlines(),
                fromfile=f"{version_a}", tofile=f"{version_b}", lineterm="",
            )
        )
        return {
            "template_id": template_id,
            "from_version": version_a,
            "to_version": version_b,
            "diff": lines,
            "changed": bool(lines),
        }

    def list_versions(self, template_id: str) -> list[dict]:
        return [v.to_dict() for v in self.store.list_versions(template_id)]

    # ------------------------------------------------------------- reviews
    def add_review(
        self,
        template_id: str,
        version_id: str,
        reviewer: str,
        status: str = "pending",
        comments: str = "",
    ) -> dict:
        if status not in REVIEW_STATUSES:
            raise ValueError(f"invalid review status: {status} (allowed: {REVIEW_STATUSES})")
        version = self.store.get_version(template_id, version_id)
        if not version:
            raise KeyError(f"version not found: {template_id}/{version_id}")
        review = PromptReview(
            id=_new_id("RV"), template_id=template_id, version_id=version_id,
            reviewer=reviewer, status=status, comments=comments,
        )
        if status in ("approved", "rejected"):
            review.resolved_at = _now()
        self.store.put_review(review)
        if status == "approved":
            self.set_version_status(template_id, version_id, "approved", approved_by=reviewer)
        return review.to_dict()

    def list_reviews(self, template_id: str | None = None) -> list[dict]:
        return [r.to_dict() for r in self.store.list_reviews(template_id)]

    # ------------------------------------------------------------- A/B tests
    def create_ab_test(
        self,
        template_id: str,
        base_version: str,
        variant_version: str,
        name: str = "",
        metric: str = "success_rate",
    ) -> dict:
        for version_id in (base_version, variant_version):
            if not self.store.get_version(template_id, version_id):
                raise KeyError(f"version not found: {template_id}/{version_id}")
        if base_version == variant_version:
            raise ValueError("base and variant versions must differ")
        ab = PromptABTest(
            id=_new_id("AB"), name=name or f"{template_id} {base_version} vs {variant_version}",
            template_id=template_id, base_version=base_version,
            variant_version=variant_version, metric=metric, status="running",
        )
        self.store.put_ab_test(ab)
        return self.get_ab_test(ab.id)

    def record_ab_result(self, ab_id: str, arm: str, success: bool) -> dict:
        if arm not in ("base", "variant"):
            raise ValueError("arm must be base or variant")
        ab = self.store.get_ab_test(ab_id)
        if not ab:
            raise KeyError(f"ab test not found: {ab_id}")
        if ab.status == "completed":
            raise ValueError("ab test already completed")
        if ab.status == "draft":
            ab.status = "running"
        arm_data = ab.results.setdefault(arm, {"samples": 0, "wins": 0, "score": 0.0})
        arm_data["samples"] = int(arm_data.get("samples", 0)) + 1
        arm_data["wins"] = int(arm_data.get("wins", 0)) + (1 if success else 0)
        arm_data["score"] = round(arm_data["wins"] / arm_data["samples"], 4)
        ab.results[arm] = arm_data
        self.store.put_ab_test(ab)
        return self.get_ab_test(ab_id)

    def decide_ab(self, ab_id: str, min_samples: int = 3) -> dict:
        ab = self.store.get_ab_test(ab_id)
        if not ab:
            raise KeyError(f"ab test not found: {ab_id}")
        base = ab.results.get("base", {})
        variant = ab.results.get("variant", {})
        if base.get("samples", 0) < min_samples or variant.get("samples", 0) < min_samples:
            raise ValueError(
                f"ab test not ready: need >= {min_samples} samples per arm "
                f"(base={base.get('samples', 0)}, variant={variant.get('samples', 0)})"
            )
        base_score = base.get("score", 0.0)
        variant_score = variant.get("score", 0.0)
        ab.winner = "base" if base_score >= variant_score else "variant"
        ab.status = "completed"
        ab.decided_at = _now()
        self.store.put_ab_test(ab)
        return self.get_ab_test(ab_id)

    def get_ab_test(self, ab_id: str) -> dict:
        ab = self.store.get_ab_test(ab_id)
        if not ab:
            raise KeyError(f"ab test not found: {ab_id}")
        return ab.to_dict()

    def list_ab_tests(self) -> list[dict]:
        return [t.to_dict() for t in self.store.list_ab_tests()]

    # ------------------------------------------------------------- stats
    def stats(self) -> dict:
        templates = self.store.list_templates()
        versions = [v for t in templates for v in self.store.list_versions(t.id)]
        return {
            "templates": len(templates),
            "versions": len(versions),
            "by_kind": {k: sum(1 for t in templates if t.kind == k) for k in TEMPLATE_KINDS},
            "approved_versions": sum(1 for v in versions if v.status == "approved"),
            "locked_versions": sum(1 for v in versions if v.status == "locked"),
            "reviews": len(self.store.list_reviews()),
            "ab_tests": len(self.store.list_ab_tests()),
        }

    # ------------------------------------------------------------- internal
    @staticmethod
    def _build_version(
        template_id: str,
        version_id: str,
        parent_version: str,
        base_template: str,
        negative_prompt: str,
        quality_tags: str,
        variables: list[str],
        notes: str,
    ) -> PromptVersion:
        version = PromptVersion(
            template_id=template_id, version_id=version_id,
            parent_version=parent_version, base_template=base_template,
            negative_prompt=negative_prompt, quality_tags=quality_tags,
            variables=variables, notes=notes,
        )
        version.content_hash = hashlib.sha256(version.content().encode("utf-8")).hexdigest()[:16]
        return version

    @staticmethod
    def _next_version_id(versions: list[PromptVersion]) -> str:
        numbers = []
        for version in versions:
            digits = "".join(ch for ch in version.version_id if ch.isdigit())
            if digits:
                numbers.append(int(digits))
        return f"v{max(numbers, default=0) + 1}"