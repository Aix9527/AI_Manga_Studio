"""Artifact Signer (Phase 12.9-A, GPT spec).

Computes a deterministic content hash for every released artifact and signs
it with the release id so a production package can be verified later
(artifact hash PASS gate in 12.9-C).
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


def content_hash(data: Any) -> str:
    """Deterministic sha256 over the JSON-canonicalized payload."""
    blob = json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def file_hash(path: str | Path, chunk: int = 1 << 16) -> str:
    """sha256 of a file (streamed, for large video artifacts)."""
    hasher = hashlib.sha256()
    with open(path, "rb") as handle:
        while block := handle.read(chunk):
            hasher.update(block)
    return hasher.hexdigest()


class ArtifactSigner:
    """Signs a manifest of artifacts with their content hashes."""

    def __init__(self, root: str | Path = "production_release"):
        self.root = Path(root)

    def sign_manifest(self, manifest: dict, release_id: str) -> dict:
        payload = dict(manifest)
        payload["release_id"] = release_id
        payload["_hash"] = content_hash(payload)
        return payload

    def verify(self, manifest: dict, release_id: str) -> bool:
        expected = manifest.get("_hash")
        if not expected:
            return False
        probe = dict(manifest)
        probe.pop("_hash", None)
        return content_hash(probe) == expected and manifest.get("release_id") == release_id
