"""
Plugin Permissions — Permission model and access control (Part 18)

Defines the permission system for plugins. Each plugin declares required
and optional permissions. The platform enforces that plugins cannot
access resources without explicit grants.

Permission format: "scope:action"
Examples: "projects:read", "assets:write", "providers:invoke"
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class PermissionLevel(str, Enum):
    READ = "read"
    WRITE = "write"
    INVOKE = "invoke"
    ADMIN = "admin"


class PermissionScope(str, Enum):
    """Predefined permission scopes."""
    PROJECTS = "projects"
    ASSETS = "assets"
    PROVIDERS = "providers"
    REVIEWS = "reviews"
    WORKFLOWS = "workflows"
    JOBS = "jobs"
    PLUGINS = "plugins"
    SYSTEM = "system"
    EXPORTS = "exports"
    AGENTS = "agents"
    MEMORY = "memory"
    STORAGE = "storage"


@dataclass
class Permission:
    """A single permission grant."""

    scope: str
    action: str  # read | write | invoke | admin
    description: str = ""

    @classmethod
    def from_string(cls, perm_str: str, description: str = "") -> Permission:
        """Parse 'scope:action' into Permission."""
        if ":" not in perm_str:
            raise ValueError(f"Invalid permission format: '{perm_str}'. Expected 'scope:action'")
        scope, action = perm_str.split(":", 1)
        return cls(scope=scope.strip(), action=action.strip(), description=description)

    @property
    def permission_id(self) -> str:
        return f"{self.scope}:{self.action}"

    def __hash__(self) -> int:
        return hash(self.permission_id)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Permission):
            return NotImplemented
        return self.permission_id == other.permission_id


@dataclass
class PermissionSet:
    """A set of permissions granted to a plugin."""

    plugin_id: str
    permissions: set[Permission] = field(default_factory=set)
    metadata: dict[str, Any] = field(default_factory=dict)

    def has(self, permission_id: str) -> bool:
        """Check if the plugin has a specific permission."""
        return any(p.permission_id == permission_id for p in self.permissions)

    def has_any(self, permission_ids: list[str]) -> bool:
        """Check if the plugin has any of the given permissions."""
        return any(self.has(pid) for pid in permission_ids)

    def add(self, perm: Permission) -> None:
        self.permissions.add(perm)

    def remove(self, permission_id: str) -> bool:
        to_remove = [p for p in self.permissions if p.permission_id == permission_id]
        for p in to_remove:
            self.permissions.discard(p)
        return len(to_remove) > 0

    def list_ids(self) -> list[str]:
        return sorted(p.permission_id for p in self.permissions)


class PermissionDeniedError(Exception):
    """Raised when a plugin attempts an action without required permission."""

    def __init__(self, plugin_id: str, required: str) -> None:
        super().__init__(f"Plugin '{plugin_id}' lacks permission '{required}'")
        self.plugin_id = plugin_id
        self.required = required
