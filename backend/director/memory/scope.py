"""Memory Scope (Phase 12.3, GPT spec).

Multi-project experience isolation: director memory must not let a sci-fi
project's learned preferences pollute a historical/wuxia project. Every
record is scoped by::

    (project_scope, genre, scene_type, director, style_profile)

``project_scope`` falls back to ``genre`` so cross-project data inside the
same genre can still share experience when no project is set.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

DEFAULT_SCOPE = "default"


@dataclass(frozen=True)
class MemoryScope:
    """The isolation dimensions of one director experience."""

    project: str = ""
    genre: str = ""
    style: str = ""                     # visual style profile (e.g. cold_blue, warm_light)
    episode: str = ""
    character_universe: str = ""

    @property
    def project_scope(self) -> str:
        return self.project or self.genre or DEFAULT_SCOPE

    def scope_key(self) -> str:
        """(project_scope, genre, style) — the isolation prefix for a record."""
        return f"{self.project_scope}|{self.genre or ''}|{self.style or ''}"

    def policy_key(self, scene_type: str, director: str) -> str:
        """Full Phase 12.3 key: project_scope|genre|scene_type|director|style."""
        return f"{self.scope_key()}|{scene_type or ''}|{director or ''}"

    def to_dict(self) -> dict:
        return {
            "project": self.project,
            "genre": self.genre,
            "style": self.style,
            "episode": self.episode,
            "character_universe": self.character_universe,
            "project_scope": self.project_scope,
            "scope_key": self.scope_key(),
        }

    @classmethod
    def from_context(cls, context: dict | None) -> "MemoryScope":
        """Build a scope from a section/pipeline context dict."""
        context = context or {}
        return cls(
            project=str(context.get("project_id") or context.get("project") or ""),
            genre=str(context.get("genre") or ""),
            style=str(context.get("style") or context.get("style_profile") or ""),
            episode=str(context.get("episode") or ""),
            character_universe=str(context.get("character_universe") or ""),
        )


def scope_from_experience(exp: Any) -> MemoryScope:
    return MemoryScope(
        project=getattr(exp, "project_id", "") or "",
        genre=getattr(exp, "genre", "") or "",
        style=getattr(exp, "style", "") or "",
        episode=getattr(exp, "episode", "") or "",
        character_universe=getattr(exp, "character_universe", "") or "",
    )
