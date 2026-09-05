from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

from backend.orchestration.database import OrchestrationDatabase


class TimelineMediaNotFound(ValueError):
    pass


class TimelineMediaIntegrityError(ValueError):
    pass


@dataclass(frozen=True)
class MediaIdentity:
    artifact_id: int
    project_id: str
    version: int
    path: str
    sha256: str
    duration_tick: int
    kind: str
    shot_id: str
    scene_id: str


class MediaIdentityResolver:
    def __init__(self, db: OrchestrationDatabase, projects_root: str | Path = "projects"):
        self.db = db
        self.projects_root = Path(projects_root)

    def resolve_artifact(self, artifact_id: int, *, verify_sha: bool = False) -> MediaIdentity:
        with self.db.connect() as conn:
            row = conn.execute("SELECT * FROM artifacts WHERE id=?", (artifact_id,)).fetchone()
        if row is None:
            raise TimelineMediaNotFound(f"Artifact not found: {artifact_id}")

        metadata = json.loads(row["metadata"] or "{}")
        duration_tick = int(metadata.get("duration_tick") or 0)
        path = str(row["path"])
        candidate = Path(path)
        if not candidate.is_absolute():
            candidate = self.projects_root / str(row["project_id"] or "") / candidate

        if verify_sha:
            if not candidate.is_file():
                raise TimelineMediaNotFound(f"Artifact media missing: {candidate}")
            digest = hashlib.sha256(candidate.read_bytes()).hexdigest()
            if digest != str(row["sha256"]):
                raise TimelineMediaIntegrityError(f"Artifact SHA mismatch: {artifact_id}")

        return MediaIdentity(
            artifact_id=int(row["id"]),
            project_id=str(row["project_id"] or ""),
            version=int(row["version"] or 1),
            path=path,
            sha256=str(row["sha256"]),
            duration_tick=duration_tick,
            kind=str(row["kind"]),
            shot_id=str(row["shot_id"] or ""),
            scene_id=str(row["scene_id"] or ""),
        )
