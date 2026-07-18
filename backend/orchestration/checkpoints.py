from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def input_hash(payload: dict[str, Any]) -> str:
    canonical = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class ArtifactDraft:
    kind: str
    path: str
    sha256: str
    size: int
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "metadata", copy.deepcopy(self.metadata))

    @classmethod
    def from_path(
        cls,
        kind: str,
        path: str | Path,
        metadata: dict[str, Any] | None = None,
    ) -> ArtifactDraft:
        resolved = Path(path).resolve()
        if not resolved.is_file():
            raise FileNotFoundError(resolved)
        return cls(
            kind=kind,
            path=str(resolved),
            sha256=sha256_file(resolved),
            size=resolved.stat().st_size,
            metadata={} if metadata is None else metadata,
        )


def validate_checkpoint(
    artifacts: Iterable[ArtifactDraft],
    expected_input_hash: str,
    actual_input_hash: str,
) -> bool:
    if expected_input_hash != actual_input_hash:
        return False
    materialized = list(artifacts)
    if not materialized:
        return False
    try:
        for artifact in materialized:
            path = Path(artifact.path)
            if not path.is_file():
                return False
            if path.stat().st_size != artifact.size:
                return False
            if sha256_file(path) != artifact.sha256:
                return False
    except OSError:
        return False
    return True
