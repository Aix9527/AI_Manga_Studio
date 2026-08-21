"""Prompt Intelligence data model (Phase 13.4-A, GPT spec).

Versionable prompt templates for Character / World / Shot composing, with
review and A/B-test records. The version governance (parent / approved /
locked) mirrors Character Bible v2 so prompt assets evolve under the same
human-approval + rollback + audit discipline.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


TEMPLATE_KINDS = ["character", "world", "shot", "generic"]
VERSION_STATUSES = ["draft", "approved", "locked"]
REVIEW_STATUSES = ["pending", "approved", "rejected"]
AB_STATUSES = ["draft", "running", "completed"]


@dataclass
class PromptTemplate:
    """A logical, versioned prompt template family."""

    id: str
    name: str = ""                  # logical name, e.g. character_portrait
    kind: str = "generic"           # character | world | shot | generic
    description: str = ""
    active_version: str = ""        # locked (production) version id
    created_at: str = field(default_factory=_now)
    updated_at: str = field(default_factory=_now)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "PromptTemplate":
        known = {f.name for f in cls.__dataclass_fields__.values()}
        return cls(**{k: v for k, v in data.items() if k in known})


@dataclass
class PromptVersion:
    """One immutable-ish version of a prompt template."""

    template_id: str
    version_id: str = "v1"
    parent_version: str = ""
    base_template: str = ""
    negative_prompt: str = ""
    quality_tags: str = ""
    variables: list[str] = field(default_factory=list)
    notes: str = ""
    status: str = "draft"           # draft | approved | locked
    approved_by: str = ""
    approved_at: str = ""
    content_hash: str = ""
    created_at: str = field(default_factory=_now)
    updated_at: str = field(default_factory=_now)

    def content(self) -> str:
        """Canonical content used for hashing and diffing."""
        return "\n".join(
            [
                self.base_template,
                self.negative_prompt,
                self.quality_tags,
                ",".join(self.variables),
            ]
        )

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "PromptVersion":
        known = {f.name for f in cls.__dataclass_fields__.values()}
        return cls(**{k: v for k, v in data.items() if k in known})


@dataclass
class PromptReview:
    """Human review record attached to a template version."""

    id: str
    template_id: str
    version_id: str
    reviewer: str = ""
    status: str = "pending"         # pending | approved | rejected
    comments: str = ""
    created_at: str = field(default_factory=_now)
    resolved_at: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "PromptReview":
        known = {f.name for f in cls.__dataclass_fields__.values()}
        return cls(**{k: v for k, v in data.items() if k in known})


@dataclass
class PromptABTest:
    """A/B test between a base and a variant template version."""

    id: str
    name: str = ""
    template_id: str = ""
    base_version: str = ""
    variant_version: str = ""
    status: str = "draft"           # draft | running | completed
    metric: str = "success_rate"
    results: dict = field(default_factory=dict)   # {base: {...}, variant: {...}}
    winner: str = ""
    created_at: str = field(default_factory=_now)
    decided_at: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "PromptABTest":
        known = {f.name for f in cls.__dataclass_fields__.values()}
        return cls(**{k: v for k, v in data.items() if k in known})