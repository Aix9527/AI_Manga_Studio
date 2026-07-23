"""
Security — Data encryption, privacy, and audit (Part 20)

Provides:
- Field-level encryption for sensitive data (API keys, PII)
- Data masking utilities
- Audit trail logging
- Privacy compliance helpers (data deletion requests)
"""

from __future__ import annotations

import base64
import hashlib
import json
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


# ── Encryption ────────────────────────────────────────────────────────

class EncryptionProvider:
    """Simple field-level encryption using Fernet-compatible approach."""

    def __init__(self, key: bytes | None = None) -> None:
        from cryptography.fernet import Fernet
        self._fernet = Fernet(key or Fernet.generate_key())

    def encrypt(self, plaintext: str) -> str:
        """Encrypt a string. Returns base64-encoded ciphertext."""
        return self._fernet.encrypt(plaintext.encode()).decode()

    def decrypt(self, ciphertext: str) -> str:
        """Decrypt a base64-encoded ciphertext."""
        return self._fernet.decrypt(ciphertext.encode()).decode()

    def encrypt_dict(self, data: dict[str, Any], fields: list[str]) -> dict[str, Any]:
        """Encrypt specified fields in a dict."""
        result = dict(data)
        for field in fields:
            if field in result and isinstance(result[field], str):
                result[field] = f"ENC:{self.encrypt(result[field])}"
        return result

    def decrypt_dict(self, data: dict[str, Any]) -> dict[str, Any]:
        """Decrypt fields prefixed with ENC:."""
        result = dict(data)
        for key, value in result.items():
            if isinstance(value, str) and value.startswith("ENC:"):
                result[key] = self.decrypt(value[4:])
        return result


# ── Data Masking ──────────────────────────────────────────────────────

def mask_api_key(key: str, visible: int = 4) -> str:
    """Mask an API key showing only the last N characters."""
    if len(key) <= visible:
        return "*" * len(key)
    return "*" * (len(key) - visible) + key[-visible:]


def mask_email(email: str) -> str:
    """Mask an email: j***@example.com."""
    if "@" not in email:
        return mask_string(email)
    local, domain = email.split("@", 1)
    return local[0] + "***" + "@" + domain


def mask_string(s: str, keep_start: int = 1, keep_end: int = 0) -> str:
    """Generic string masking."""
    if len(s) <= keep_start + keep_end:
        return "*" * len(s)
    return s[:keep_start] + "*" * (len(s) - keep_start - keep_end) + (s[-keep_end:] if keep_end > 0 else "")


# ── Audit Trail ───────────────────────────────────────────────────────

class AuditAction(str, Enum):
    CREATE = "create"
    READ = "read"
    UPDATE = "update"
    DELETE = "delete"
    EXPORT = "export"
    LOGIN = "login"
    LOGOUT = "logout"
    API_KEY_CREATED = "api_key_created"
    API_KEY_REVOKED = "api_key_revoked"


@dataclass
class AuditEntry:
    """Single audit log entry."""
    id: str = ""
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    user_id: str = ""
    action: str = ""
    resource_type: str = ""
    resource_id: str = ""
    project_id: str = ""
    details: dict[str, Any] = field(default_factory=dict)
    ip_address: str = ""
    success: bool = True


class AuditLogger:
    """Append-only audit log."""

    def __init__(self) -> None:
        self._entries: list[AuditEntry] = []
        self._counter = 0

    def log(
        self,
        action: str,
        resource_type: str = "",
        resource_id: str = "",
        user_id: str = "",
        project_id: str = "",
        details: dict[str, Any] | None = None,
        success: bool = True,
    ) -> AuditEntry:
        self._counter += 1
        entry = AuditEntry(
            id=str(self._counter),
            user_id=user_id,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            project_id=project_id,
            details=details or {},
            success=success,
        )
        self._entries.append(entry)
        return entry

    def query(
        self,
        user_id: str = "",
        action: str = "",
        resource_type: str = "",
        limit: int = 100,
    ) -> list[AuditEntry]:
        """Query audit entries with optional filters."""
        results = self._entries
        if user_id:
            results = [e for e in results if e.user_id == user_id]
        if action:
            results = [e for e in results if e.action == action]
        if resource_type:
            results = [e for e in results if e.resource_type == resource_type]
        return results[-limit:]

    def to_jsonl(self) -> str:
        """Export audit log as JSONL string."""
        import json
        lines = []
        for e in self._entries:
            lines.append(json.dumps({
                "id": e.id,
                "timestamp": e.timestamp,
                "user_id": e.user_id,
                "action": e.action,
                "resource_type": e.resource_type,
                "resource_id": e.resource_id,
                "project_id": e.project_id,
                "success": e.success,
            }, default=str))
        return "\n".join(lines)


# Global audit logger
audit_logger = AuditLogger()
