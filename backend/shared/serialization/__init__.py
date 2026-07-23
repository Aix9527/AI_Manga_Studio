"""Canonical JSON serialization for stable hashing."""

import json
from hashlib import sha256
from typing import Any


def canonical_json_dumps(value: Any) -> str:
    """Serialize to canonical JSON (sorted keys, no whitespace, no NaN)."""
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def json_loads(value: str) -> Any:
    """Deserialize canonical JSON."""
    return json.loads(value)


def hash_json(value: Any) -> str:
    """Compute SHA-256 hash of canonical JSON representation."""
    encoded = canonical_json_dumps(value).encode("utf-8")
    return sha256(encoded).hexdigest()
