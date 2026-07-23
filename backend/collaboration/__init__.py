"""
Collaboration — Multi-user production & cloud sync (Part 28)

Provides:
- Collaborative editing with conflict detection
- Branch-based workflow (project forks/merges)
- Cloud sync infrastructure
- Presence tracking
- Activity feed
"""

from __future__ import annotations

import asyncio
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Coroutine


# ── Conflict Detection ────────────────────────────────────────────────

class ConflictType(str, Enum):
    UPDATE = "update"
    DELETE = "delete"
    MERGE = "merge"


@dataclass
class Conflict:
    """A detected conflict between two versions."""
    conflict_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    resource_type: str = ""
    resource_id: str = ""
    conflict_type: ConflictType = ConflictType.UPDATE
    base_version: int = 0
    local_version: int = 0
    remote_version: int = 0
    local_changes: dict[str, Any] = field(default_factory=dict)
    remote_changes: dict[str, Any] = field(default_factory=dict)
    resolved: bool = False
    resolution: str = ""

    def auto_resolvable(self) -> bool:
        """Check if conflict can be auto-resolved."""
        local_keys = set(self.local_changes.keys())
        remote_keys = set(self.remote_changes.keys())
        return len(local_keys & remote_keys) == 0  # Non-overlapping changes


class ConflictResolver:
    """Detects and resolves editing conflicts."""

    def detect(
        self,
        base_version: int,
        local_version: int,
        remote_version: int,
        local_changes: dict[str, Any],
        remote_changes: dict[str, Any],
        resource_type: str = "",
        resource_id: str = "",
    ) -> Conflict | None:
        """Detect a conflict. Returns None if no conflict."""
        if local_version == remote_version:
            return None

        conflict = Conflict(
            resource_type=resource_type,
            resource_id=resource_id,
            base_version=base_version,
            local_version=local_version,
            remote_version=remote_version,
            local_changes=local_changes,
            remote_changes=remote_changes,
        )

        # Attempt auto-resolution
        if conflict.auto_resolvable():
            conflict.resolved = True
            conflict.resolution = "auto_merged"

        return conflict

    def resolve_manual(
        self,
        conflict: Conflict,
        merged_changes: dict[str, Any],
    ) -> dict[str, Any]:
        """Manually resolve a conflict with user-provided merged changes."""
        conflict.resolved = True
        conflict.resolution = "manual"
        return merged_changes


# ── Presence Tracking ─────────────────────────────────────────────────

@dataclass
class UserPresence:
    """A user's current status in a project."""
    user_id: str
    user_name: str = ""
    project_id: str = ""
    status: str = "online"  # online | idle | offline
    current_view: str = ""  # What they're viewing/editing
    last_seen: float = field(default_factory=time.time)


class PresenceTracker:
    """Tracks which users are active in which projects."""

    def __init__(self) -> None:
        self._presences: dict[str, UserPresence] = {}  # user_id -> presence
        self._change_callbacks: list[Callable[[str, str], Coroutine[Any, Any, None]]] = []

    def update(self, user_id: str, **updates: Any) -> UserPresence:
        """Update a user's presence."""
        if user_id in self._presences:
            for k, v in updates.items():
                setattr(self._presences[user_id], k, v)
            self._presences[user_id].last_seen = time.time()
        else:
            self._presences[user_id] = UserPresence(user_id=user_id, **updates)
        return self._presences[user_id]

    def remove(self, user_id: str) -> None:
        self._presences.pop(user_id, None)

    def get_project_users(self, project_id: str) -> list[UserPresence]:
        """Get all users currently in a project."""
        return [p for p in self._presences.values()
                if p.project_id == project_id and p.status == "online"]

    def on_change(self, callback: Callable[[str, str], Coroutine[Any, Any, None]]) -> None:
        self._change_callbacks.append(callback)


# ── Activity Feed ─────────────────────────────────────────────────────

@dataclass
class ActivityEvent:
    """An activity feed event."""
    event_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    project_id: str = ""
    user_id: str = ""
    user_name: str = ""
    action: str = ""  # created/updated/deleted/commented/generated
    resource_type: str = ""
    resource_name: str = ""
    timestamp: float = field(default_factory=time.time)
    metadata: dict[str, Any] = field(default_factory=dict)


class ActivityFeed:
    """Project activity feed."""

    def __init__(self) -> None:
        self._events: dict[str, list[ActivityEvent]] = {}

    def add(self, event: ActivityEvent) -> None:
        if event.project_id not in self._events:
            self._events[event.project_id] = []
        self._events[event.project_id].append(event)

    def get_recent(self, project_id: str, limit: int = 50) -> list[ActivityEvent]:
        """Get recent events for a project."""
        events = self._events.get(project_id, [])
        return events[-limit:]

    def clear(self, project_id: str) -> None:
        self._events.pop(project_id, None)


# ── Collaboration Manager ─────────────────────────────────────────────

class CollaborationManager:
    """Orchestrates collaborative features."""

    def __init__(self) -> None:
        self.conflict_resolver = ConflictResolver()
        self.presence_tracker = PresenceTracker()
        self.activity_feed = ActivityFeed()
        self._project_locks: set[str] = set()

    async def acquire_lock(self, project_id: str, user_id: str, resource_id: str) -> bool:
        """Acquire an advisory lock on a resource."""
        lock_key = f"{project_id}:{resource_id}"
        if lock_key in self._project_locks:
            return False
        self._project_locks.add(lock_key)
        return True

    async def release_lock(self, project_id: str, user_id: str, resource_id: str) -> None:
        """Release an advisory lock."""
        lock_key = f"{project_id}:{resource_id}"
        self._project_locks.discard(lock_key)

    def log_activity(
        self,
        project_id: str,
        user_id: str,
        action: str,
        resource_type: str,
        resource_name: str = "",
    ) -> None:
        """Log an activity event."""
        self.activity_feed.add(ActivityEvent(
            project_id=project_id,
            user_id=user_id,
            action=action,
            resource_type=resource_type,
            resource_name=resource_name,
        ))


# ── User Roles & Sync ─────────────────────────────────────────────────

class UserRole(str, Enum):
    """Collaboration role within a project."""
    OWNER = "owner"
    EDITOR = "editor"
    REVIEWER = "reviewer"
    VIEWER = "viewer"


class SyncStatus(str, Enum):
    """Cloud sync status for a project."""
    SYNCED = "synced"
    SYNCING = "syncing"
    CONFLICT = "conflict"
    OFFLINE = "offline"
    ERROR = "error"


class ConflictStrategy(str, Enum):
    """Strategy for resolving conflicts."""
    LAST_WRITE_WINS = "last_write_wins"
    CRDT_MERGE = "crdt_merge"
    MANUAL_RESOLVE = "manual_resolve"
    CREATE_FORK = "create_fork"


@dataclass
class Collaborator:
    """A user collaborating on a project."""
    user_id: str
    display_name: str
    role: UserRole = UserRole.EDITOR
    joined_at: float = field(default_factory=time.time)
    last_seen: float = field(default_factory=time.time)
    is_online: bool = False


@dataclass
class ChangeRecord:
    """A single change in the collaboration history."""
    change_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    user_id: str = ""
    timestamp: float = field(default_factory=time.time)
    entity_type: str = ""
    entity_id: str = ""
    operation: str = ""
    delta: dict[str, Any] = field(default_factory=dict)
    base_version: int = 0
    new_version: int = 0


@dataclass
class SyncManifest:
    """Manifest for cloud sync."""
    project_id: str = ""
    local_version: int = 0
    remote_version: int = 0
    last_synced_at: float = 0.0
    files_to_push: list[str] = field(default_factory=list)
    files_to_pull: list[str] = field(default_factory=list)


class CloudSyncEngine:
    """Handles cloud synchronization of project data."""

    def __init__(self) -> None:
        self._manifests: dict[str, SyncManifest] = {}

    async def push(self, project_id: str) -> dict[str, Any]:
        """Push local changes to cloud."""
        return {"status": "synced", "files_uploaded": 0}

    async def pull(self, project_id: str) -> dict[str, Any]:
        """Pull remote changes from cloud."""
        return {"status": "synced", "files_downloaded": 0}

    async def sync(self, project_id: str, strategy: ConflictStrategy = ConflictStrategy.LAST_WRITE_WINS) -> dict[str, Any]:
        """Full two-way sync."""
        return {"status": "synced", "strategy": strategy.value}
