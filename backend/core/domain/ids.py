from __future__ import annotations

import hashlib
import uuid
from datetime import datetime, timezone


def create_id(prefix: str) -> str:
    """
    Generate domain identifier.

    Example:

    project_018f8b7a...
    """

    uid = uuid.uuid4().hex

    return f"{prefix}_{uid}"


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: str) -> str:
    h = hashlib.sha256()

    with open(path, "rb") as f:
        while True:
            chunk = f.read(1024 * 1024)

            if not chunk:
                break

            h.update(chunk)

    return h.hexdigest()
