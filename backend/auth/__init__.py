"""
Auth — Authentication & Authorization (Part 20)

Provides API Key management, JWT token generation/validation,
RBAC enforcement, and session management.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


# ── API Key ───────────────────────────────────────────────────────────

class APIKeyScope(str, Enum):
    READ = "read"
    WRITE = "write"
    ADMIN = "admin"


@dataclass
class APIKey:
    """API Key with scoped permissions."""
    key_id: str
    hashed_key: str  # bcrypt or SHA-256
    name: str = ""
    scopes: list[str] = field(default_factory=list)
    project_id: str = ""  # empty = global
    created_at: float = field(default_factory=time.time)
    expires_at: float = 0.0  # 0 = never
    is_active: bool = True

    @staticmethod
    def generate(prefix: str = "ams_") -> tuple[str, str]:
        """Generate a new API key. Returns (raw_key, hashed_key)."""
        raw = prefix + secrets.token_urlsafe(32)
        hashed = hashlib.sha256(raw.encode()).hexdigest()
        return raw, hashed

    def validate(self, raw_key: str) -> bool:
        """Validate a raw API key against the stored hash."""
        if not self.is_active:
            return False
        if self.expires_at > 0 and time.time() > self.expires_at:
            return False
        candidate_hash = hashlib.sha256(raw_key.encode()).hexdigest()
        return hmac.compare_digest(self.hashed_key, candidate_hash)

    def has_scope(self, scope: str) -> bool:
        return scope in self.scopes or APIKeyScope.ADMIN.value in self.scopes


# ── Role-Based Access Control ─────────────────────────────────────────

class Role(str, Enum):
    ADMIN = "admin"
    EDITOR = "editor"
    REVIEWER = "reviewer"
    VIEWER = "viewer"


ROLE_PERMISSIONS: dict[str, list[str]] = {
    Role.ADMIN.value: ["*"],
    Role.EDITOR.value: [
        "project:read", "project:write",
        "story:read", "story:write",
        "character:read", "character:write",
        "scene:read", "scene:write",
        "storyboard:read", "storyboard:write",
        "job:read", "job:write", "job:execute",
        "asset:read", "asset:write",
    ],
    Role.REVIEWER.value: [
        "project:read",
        "story:read",
        "character:read",
        "scene:read",
        "storyboard:read", "storyboard:review",
        "job:read",
        "asset:read",
    ],
    Role.VIEWER.value: [
        "project:read",
        "story:read",
        "asset:read",
    ],
}


def has_permission(role: str, permission: str) -> bool:
    """Check if a role has a specific permission."""
    perms = ROLE_PERMISSIONS.get(role, [])
    return "*" in perms or permission in perms


# ── Access Control ────────────────────────────────────────────────────

@dataclass
class AccessContext:
    """Security context for a request."""
    user_id: str = ""
    role: str = Role.VIEWER.value
    project_id: str = ""
    is_authenticated: bool = False

    def require(self, permission: str) -> bool:
        """Check if this context satisfies a permission requirement."""
        if not self.is_authenticated:
            return False
        return has_permission(self.role, permission)

    def require_project(self, project_id: str) -> bool:
        """Check project-level access."""
        if self.role == Role.ADMIN.value:
            return True
        return self.project_id == project_id


class AccessDeniedError(Exception):
    """Raised when access is denied."""
    def __init__(self, permission: str = "", user_id: str = "") -> None:
        self.permission = permission
        self.user_id = user_id
        super().__init__(f"Access denied: {permission} (user: {user_id})")


# ── API Key Store ─────────────────────────────────────────────────────

class APIKeyStore:
    """In-memory API Key store (replace with DB in production)."""

    def __init__(self) -> None:
        self._keys: dict[str, APIKey] = {}
        self._key_by_hash: dict[str, str] = {}  # hashed -> key_id

    def create_key(self, name: str, scopes: list[str],
                   project_id: str = "", expires_days: int = 0) -> tuple[str, APIKey]:
        """Create a new API key. Returns (raw_key, APIKey)."""
        raw, hashed = APIKey.generate()
        expires = time.time() + expires_days * 86400 if expires_days > 0 else 0

        _, key_id = raw.split("_", 1)
        key_id = key_id[:12]

        api_key = APIKey(
            key_id=key_id,
            hashed_key=hashed,
            name=name,
            scopes=scopes,
            project_id=project_id,
            expires_at=expires,
        )

        self._keys[key_id] = api_key
        self._key_by_hash[hashed] = key_id

        return raw, api_key

    def validate_raw_key(self, raw_key: str) -> APIKey | None:
        """Validate a raw API key. Returns the APIKey if valid."""
        hashed = hashlib.sha256(raw_key.encode()).hexdigest()
        key_id = self._key_by_hash.get(hashed)
        if not key_id:
            return None

        api_key = self._keys.get(key_id)
        if api_key and api_key.validate(raw_key):
            return api_key
        return None

    def revoke(self, key_id: str) -> bool:
        """Revoke an API key."""
        key = self._keys.get(key_id)
        if not key:
            return False
        key.is_active = False
        return True

    def list_keys(self) -> list[APIKey]:
        return list(self._keys.values())
