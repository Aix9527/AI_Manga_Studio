"""Character Bible v2 data model (Phase 13.1, GPT spec).

On-disk layout per character (GPT)::

    characters/bible/<character_id>/
    ├── identity.yaml
    ├── versions/{v1.yaml, v2.yaml}
    ├── views/{front, side, back}
    ├── expressions/{neutral, angry, sad, fear, smile, surprise}
    └── actions/{walk, run, fight, sit, interact, emotional}
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Any


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


@dataclass
class BibleIdentity:
    name: str = ""
    age: int = 0
    gender: str = ""
    personality: list[str] = field(default_factory=list)
    background: str = ""
    source_character_id: str = ""
    appearance: dict[str, Any] = field(default_factory=dict)
    voice: dict[str, Any] = field(default_factory=dict)


@dataclass
class BibleVersion:
    id: str = "v1"
    parent: str = ""
    approved: bool = False
    locked: bool = False
    appearance: dict[str, Any] = field(default_factory=dict)
    clothing: dict[str, Any] = field(default_factory=dict)
    notes: str = ""
    created_at: str = field(default_factory=_now)


@dataclass
class BibleView:
    key: str = ""          # front | side | back
    image_path: str = ""
    prompt: str = ""
    seed: int = 0
    created_at: str = field(default_factory=_now)


@dataclass
class BibleExpression:
    key: str = ""          # neutral | angry | sad | fear | smile | surprise
    image_path: str = ""
    prompt: str = ""
    seed: int = 0
    created_at: str = field(default_factory=_now)


@dataclass
class BibleAction:
    key: str = ""          # walk | run | fight | sit | interact | emotional
    description: str = ""
    prompt: str = ""
    image_path: str = ""
    created_at: str = field(default_factory=_now)


EXPRESSION_KEYS = ["neutral", "angry", "sad", "fear", "smile", "surprise"]
ACTION_KEYS = ["walk", "run", "fight", "sit", "interact", "emotional"]
VIEW_KEYS = ["front", "side", "back"]


@dataclass
class CharacterBible:
    character_id: str
    identity: BibleIdentity = field(default_factory=BibleIdentity)
    versions: dict[str, BibleVersion] = field(default_factory=dict)
    views: dict[str, BibleView] = field(default_factory=dict)
    expressions: dict[str, BibleExpression] = field(default_factory=dict)
    actions: dict[str, BibleAction] = field(default_factory=dict)
    updated_at: str = field(default_factory=_now)

    def completeness(self) -> dict:
        """Asset completeness: views/expressions/actions + version coverage."""
        views = len(self.views)
        expressions = len(self.expressions)
        actions = len(self.actions)
        versions = len(self.versions)
        return {
            "views": views,
            "views_required": len(VIEW_KEYS),
            "expressions": expressions,
            "expressions_required": len(EXPRESSION_KEYS),
            "actions": actions,
            "actions_required": len(ACTION_KEYS),
            "versions": versions,
            "ratio": round((views + expressions + actions) / (len(VIEW_KEYS) + len(EXPRESSION_KEYS) + len(ACTION_KEYS)), 3),
        }

    def to_dict(self) -> dict:
        return {
            "character_id": self.character_id,
            "identity": asdict(self.identity),
            "versions": {k: asdict(v) for k, v in self.versions.items()},
            "views": {k: asdict(v) for k, v in self.views.items()},
            "expressions": {k: asdict(v) for k, v in self.expressions.items()},
            "actions": {k: asdict(v) for k, v in self.actions.items()},
            "updated_at": self.updated_at,
            "completeness": self.completeness(),
        }
