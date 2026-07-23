"""
Memory System — Core modules (Part 10)

Provides layered memory for AI agents across different timescales
and scopes: Character Memory, Scene Memory, Project Memory,
Global Context, and Long Story Context.

Architecture:
- CharacterMemory: individual character identity, consistency
- SceneMemory: scene-level context, atmosphere, lighting
- ProjectMemory: project-wide settings, preferences
- GlobalContext: cross-project knowledge, style guides
- LongStoryContext: long-range narrative continuity
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Optional
from uuid import uuid4

from backend.database import DatabaseManager
from backend.database.models import MemoryRecord
from backend.repositories import MemoryRecordRepository


logger = logging.getLogger(__name__)


# ── Base Memory Types ───────────────────────────────────────────────────


@dataclass
class MemoryEntry:
    """A single memory entry with metadata."""

    key: str
    value: dict[str, Any]
    source: str = "agent"
    confidence: float = 1.0
    ttl_seconds: Optional[int] = None  # None = permanent


class BaseMemory(ABC):
    """Abstract base for all memory subsystems."""

    def __init__(self, project_id: str, db: DatabaseManager) -> None:
        self.project_id = project_id
        self.db = db

    @abstractmethod
    async def remember(self, key: str) -> Optional[dict[str, Any]]:
        """Retrieve a memory by key."""
        ...

    @abstractmethod
    async def memorize(self, key: str, value: dict[str, Any], **meta: Any) -> None:
        """Store a memory."""
        ...

    @abstractmethod
    async def forget(self, key: str) -> None:
        """Remove a memory."""
        ...

    @abstractmethod
    async def summarize(self) -> dict[str, Any]:
        """Return a summary of all memories in this scope."""
        ...


# ── Character Memory ────────────────────────────────────────────────────


class CharacterMemory(BaseMemory):
    """
    Per-character memory store.

    Tracks:
    - Appearance consistency (hair color, eye color, height, clothing)
    - Personality trait evolution
    - Relationship changes
    - Dialogue style and speech patterns
    """

    MEMORY_TYPE = "character"

    async def remember(self, key: str) -> Optional[dict[str, Any]]:
        async with self.db.session() as session:
            repo = MemoryRecordRepository(session)
            records = await repo.find_by_key(self.project_id, key)
            # Filter to character memory type
            records = [r for r in records if r.memory_type == self.MEMORY_TYPE]
            if records:
                return records[-1].value  # Latest
            return None

    async def memorize(
        self, key: str, value: dict[str, Any], **meta: Any
    ) -> None:
        async with self.db.session() as session:
            repo = MemoryRecordRepository(session)
            await repo.create(
                project_id=self.project_id,
                memory_type=self.MEMORY_TYPE,
                key=key,
                value=value,
                source=meta.get("source", "agent"),
                confidence=meta.get("confidence", 1.0),
            )

    async def forget(self, key: str) -> None:
        async with self.db.session() as session:
            repo = MemoryRecordRepository(session)
            records = await repo.find_by_key(self.project_id, key)
            for r in records:
                if r.memory_type == self.MEMORY_TYPE:
                    await repo.hard_delete(r.record_id)

    async def summarize(self) -> dict[str, Any]:
        async with self.db.session() as session:
            repo = MemoryRecordRepository(session)
            all_records = await repo.list(
                project_id=self.project_id,
                memory_type=self.MEMORY_TYPE,
            )
            keys = list({r.key for r in all_records})
            return {
                "memory_type": self.MEMORY_TYPE,
                "project_id": self.project_id,
                "entry_count": len(all_records),
                "keys": keys,
            }

    async def get_identity(
        self, character_id: str
    ) -> dict[str, Any]:
        """Get the full identity snapshot for a character."""
        identity = await self.remember(f"identity:{character_id}")
        return identity or {}

    async def update_appearance(
        self, character_id: str, appearance: dict[str, Any]
    ) -> None:
        """Update a character's appearance memory."""
        existing = await self.get_identity(character_id)
        existing["appearance"] = {
            **(existing.get("appearance", {})),
            **appearance,
        }
        await self.memorize(f"identity:{character_id}", existing)


# ── Scene Memory ────────────────────────────────────────────────────────


class SceneMemory(BaseMemory):
    """
    Scene-level memory store.

    Tracks:
    - Location consistency
    - Lighting and atmosphere continuity
    - Camera continuity (180-degree rule, eyeline)
    """

    MEMORY_TYPE = "scene"

    async def remember(self, key: str) -> Optional[dict[str, Any]]:
        async with self.db.session() as session:
            repo = MemoryRecordRepository(session)
            records = await repo.find_by_key(self.project_id, key)
            records = [r for r in records if r.memory_type == self.MEMORY_TYPE]
            return records[-1].value if records else None

    async def memorize(
        self, key: str, value: dict[str, Any], **meta: Any
    ) -> None:
        async with self.db.session() as session:
            repo = MemoryRecordRepository(session)
            await repo.create(
                project_id=self.project_id,
                memory_type=self.MEMORY_TYPE,
                key=key,
                value=value,
                source=meta.get("source", "agent"),
                confidence=meta.get("confidence", 1.0),
            )

    async def forget(self, key: str) -> None:
        async with self.db.session() as session:
            repo = MemoryRecordRepository(session)
            records = await repo.find_by_key(self.project_id, key)
            for r in records:
                if r.memory_type == self.MEMORY_TYPE:
                    await repo.hard_delete(r.record_id)

    async def summarize(self) -> dict[str, Any]:
        async with self.db.session() as session:
            repo = MemoryRecordRepository(session)
            all_records = await repo.list(
                project_id=self.project_id,
                memory_type=self.MEMORY_TYPE,
            )
            return {
                "memory_type": self.MEMORY_TYPE,
                "project_id": self.project_id,
                "entry_count": len(all_records),
            }


# ── Project Memory ──────────────────────────────────────────────────────


class ProjectMemory(BaseMemory):
    """
    Project-wide memory store.

    Tracks:
    - Art style preferences
    - Model/provider settings
    - Export preferences
    - Review feedback history
    """

    MEMORY_TYPE = "project"

    async def remember(self, key: str) -> Optional[dict[str, Any]]:
        async with self.db.session() as session:
            repo = MemoryRecordRepository(session)
            records = await repo.find_by_key(self.project_id, key)
            records = [r for r in records if r.memory_type == self.MEMORY_TYPE]
            return records[-1].value if records else None

    async def memorize(
        self, key: str, value: dict[str, Any], **meta: Any
    ) -> None:
        async with self.db.session() as session:
            repo = MemoryRecordRepository(session)
            await repo.create(
                project_id=self.project_id,
                memory_type=self.MEMORY_TYPE,
                key=key,
                value=value,
                source=meta.get("source", "agent"),
                confidence=meta.get("confidence", 1.0),
            )

    async def forget(self, key: str) -> None:
        async with self.db.session() as session:
            repo = MemoryRecordRepository(session)
            records = await repo.find_by_key(self.project_id, key)
            for r in records:
                if r.memory_type == self.MEMORY_TYPE:
                    await repo.hard_delete(r.record_id)

    async def summarize(self) -> dict[str, Any]:
        async with self.db.session() as session:
            repo = MemoryRecordRepository(session)
            all_records = await repo.list(
                project_id=self.project_id,
                memory_type=self.MEMORY_TYPE,
            )
            return {
                "memory_type": self.MEMORY_TYPE,
                "project_id": self.project_id,
                "entry_count": len(all_records),
            }


# ── Global Context ──────────────────────────────────────────────────────


class GlobalContext(BaseMemory):
    """
    Cross-project, global knowledge store.

    Tracks:
    - Style guides (global art style definitions)
    - Model performance benchmarks
    - Common prompt templates
    - Provider capability registry
    """

    MEMORY_TYPE = "global"

    async def remember(self, key: str) -> Optional[dict[str, Any]]:
        async with self.db.session() as session:
            repo = MemoryRecordRepository(session)
            records = await repo.list(
                project_id=self.project_id,
                memory_type=self.MEMORY_TYPE,
            )
            for r in records:
                if r.key == key:
                    return r.value
            return None

    async def memorize(
        self, key: str, value: dict[str, Any], **meta: Any
    ) -> None:
        async with self.db.session() as session:
            repo = MemoryRecordRepository(session)
            await repo.create(
                project_id=self.project_id,
                memory_type=self.MEMORY_TYPE,
                key=key,
                value=value,
                source=meta.get("source", "agent"),
                confidence=meta.get("confidence", 1.0),
            )

    async def forget(self, key: str) -> None:
        async with self.db.session() as session:
            repo = MemoryRecordRepository(session)
            records = await repo.list(
                project_id=self.project_id,
                memory_type=self.MEMORY_TYPE,
            )
            for r in records:
                if r.key == key:
                    await repo.hard_delete(r.record_id)

    async def summarize(self) -> dict[str, Any]:
        async with self.db.session() as session:
            repo = MemoryRecordRepository(session)
            all_records = await repo.list(
                project_id=self.project_id,
                memory_type=self.MEMORY_TYPE,
            )
            return {
                "memory_type": self.MEMORY_TYPE,
                "project_id": self.project_id,
                "entry_count": len(all_records),
            }


# ── Long Story Context ──────────────────────────────────────────────────


class LongStoryContext(BaseMemory):
    """
    Long-range narrative continuity store.

    Tracks:
    - Plot events across chapters (timeline)
    - Foreshadowing and callbacks
    - Character arcs across the entire story
    - World-building consistency
    """

    MEMORY_TYPE = "story"

    async def remember(self, key: str) -> Optional[dict[str, Any]]:
        async with self.db.session() as session:
            repo = MemoryRecordRepository(session)
            records = await repo.find_by_key(self.project_id, key)
            records = [r for r in records if r.memory_type == self.MEMORY_TYPE]
            return records[-1].value if records else None

    async def memorize(
        self, key: str, value: dict[str, Any], **meta: Any
    ) -> None:
        async with self.db.session() as session:
            repo = MemoryRecordRepository(session)
            await repo.create(
                project_id=self.project_id,
                memory_type=self.MEMORY_TYPE,
                key=key,
                value=value,
                source=meta.get("source", "agent"),
                confidence=meta.get("confidence", 1.0),
            )

    async def forget(self, key: str) -> None:
        async with self.db.session() as session:
            repo = MemoryRecordRepository(session)
            records = await repo.find_by_key(self.project_id, key)
            for r in records:
                if r.memory_type == self.MEMORY_TYPE:
                    await repo.hard_delete(r.record_id)

    async def summarize(self) -> dict[str, Any]:
        async with self.db.session() as session:
            repo = MemoryRecordRepository(session)
            all_records = await repo.list(
                project_id=self.project_id,
                memory_type=self.MEMORY_TYPE,
            )
            return {
                "memory_type": self.MEMORY_TYPE,
                "project_id": self.project_id,
                "entry_count": len(all_records),
            }

    async def get_story_timeline(self) -> list[dict[str, Any]]:
        """Retrieve chronologically ordered plot events."""
        timeline = await self.remember("story_timeline")
        return timeline.get("events", []) if timeline else []

    async def add_plot_event(self, event: dict[str, Any]) -> None:
        """Add a plot event to the story timeline."""
        timeline = await self.remember("story_timeline") or {"events": []}
        timeline["events"].append(event)
        await self.memorize("story_timeline", timeline)
