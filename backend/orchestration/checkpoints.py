from __future__ import annotations

import hashlib
import json
import os
import stat
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable


class FrozenDict(dict[str, Any]):
    @staticmethod
    def _immutable(*_args: Any, **_kwargs: Any) -> None:
        raise TypeError("metadata is immutable")

    __setitem__ = _immutable
    __delitem__ = _immutable
    clear = _immutable
    pop = _immutable
    popitem = _immutable
    setdefault = _immutable
    update = _immutable
    __ior__ = _immutable


def _freeze_metadata(value: Any) -> Any:
    if isinstance(value, dict):
        frozen = FrozenDict()
        dict.update(
            frozen,
            ((key, _freeze_metadata(item)) for key, item in value.items()),
        )
        return frozen
    if isinstance(value, (list, tuple)):
        return tuple(_freeze_metadata(item) for item in value)
    return value


@dataclass(frozen=True)
class FileIdentity:
    device: int
    inode: int
    size: int
    modified_ns: int
    changed_ns: int


@dataclass(frozen=True)
class FileSnapshot:
    sha256: str
    size: int
    identity: FileIdentity


def _file_identity(file_stat: os.stat_result) -> FileIdentity:
    return FileIdentity(
        device=file_stat.st_dev,
        inode=file_stat.st_ino,
        size=file_stat.st_size,
        modified_ns=file_stat.st_mtime_ns,
        changed_ns=file_stat.st_ctime_ns,
    )


def stable_file_snapshot(path: str | Path) -> FileSnapshot:
    resolved = Path(path)
    digest = hashlib.sha256()
    with resolved.open("rb") as stream:
        before = os.fstat(stream.fileno())
        if not stat.S_ISREG(before.st_mode):
            raise FileNotFoundError(resolved)
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
        after = os.fstat(stream.fileno())
    current = resolved.stat()
    before_identity = _file_identity(before)
    if before_identity != _file_identity(after):
        raise OSError(f"file changed while hashing: {resolved}")
    current_identity = _file_identity(current)
    same_path_target = (
        before_identity.device == current_identity.device
        and before_identity.inode == current_identity.inode
        and before_identity.size == current_identity.size
        and before_identity.modified_ns == current_identity.modified_ns
    )
    if os.name != "nt":
        same_path_target = (
            same_path_target
            and before_identity.changed_ns == current_identity.changed_ns
        )
    if not same_path_target:
        raise OSError(f"file path changed while hashing: {resolved}")
    return FileSnapshot(
        sha256=digest.hexdigest(),
        size=before.st_size,
        identity=current_identity,
    )


def sha256_file(path: str | Path) -> str:
    return stable_file_snapshot(path).sha256


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
        object.__setattr__(self, "metadata", _freeze_metadata(self.metadata))

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
        snapshot = stable_file_snapshot(resolved)
        return cls(
            kind=kind,
            path=str(resolved),
            sha256=snapshot.sha256,
            size=snapshot.size,
            metadata={} if metadata is None else metadata,
        )


def validated_file_identities(
    artifacts: Iterable[ArtifactDraft],
) -> tuple[FileIdentity, ...] | None:
    materialized = list(artifacts)
    if not materialized:
        return None
    identities = []
    try:
        for artifact in materialized:
            snapshot = stable_file_snapshot(artifact.path)
            if snapshot.size != artifact.size or snapshot.sha256 != artifact.sha256:
                return None
            identities.append(snapshot.identity)
    except OSError:
        return None
    return tuple(identities)


def matches_file_identity(path: str | Path, expected: FileIdentity) -> bool:
    try:
        current = Path(path).stat()
    except OSError:
        return False
    return stat.S_ISREG(current.st_mode) and _file_identity(current) == expected


def validate_checkpoint(
    artifacts: Iterable[ArtifactDraft],
    expected_input_hash: str,
    actual_input_hash: str,
) -> bool:
    if expected_input_hash != actual_input_hash:
        return False
    return validated_file_identities(artifacts) is not None
