"""
Utility Functions — Shared helpers (Part 8)

Common utilities used across all backend modules.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def ensure_dir(dir_path: str) -> str:
    """Create directory if it doesn't exist, return path."""
    Path(dir_path).mkdir(parents=True, exist_ok=True)
    return dir_path


def safe_json_loads(text: str, default: Any = None) -> Any:
    """Safely parse JSON, returning default on failure."""
    try:
        return json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return default if default is not None else {}


def safe_json_dumps(obj: Any, indent: int = 2) -> str:
    """Safely serialize to JSON."""
    try:
        return json.dumps(obj, ensure_ascii=False, indent=indent)
    except (TypeError, ValueError) as e:
        logger.error(f"JSON serialization failed: {e}")
        return "{}"


def file_sha256(file_path: str) -> str:
    """Compute SHA-256 hash of a file."""
    if not os.path.isfile(file_path):
        return ""
    sha = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            sha.update(chunk)
    return sha.hexdigest()


def format_file_size(size_bytes: int) -> str:
    """Format file size to human-readable string."""
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if size_bytes < 1024:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.1f} PB"


def timestamp_iso() -> str:
    """Get current UTC timestamp as ISO 8601 string."""
    return datetime.utcnow().isoformat() + "Z"


def slugify(text: str) -> str:
    """Create a URL-safe slug from text."""
    import re
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_]+", "-", text)
    return text[:100]


def chunk_list(lst: list[Any], chunk_size: int) -> list[list[Any]]:
    """Split a list into chunks of specified size."""
    return [lst[i : i + chunk_size] for i in range(0, len(lst), chunk_size)]


def resolve_path(*parts: str) -> str:
    """Resolve a path from parts, handling both / and \\."""
    return str(Path(os.path.join(*parts)).resolve())
