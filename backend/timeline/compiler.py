from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

from pydantic import BaseModel, Field

from backend.timeline.media import MediaIdentityResolver, TimelineMediaIntegrityError, TimelineMediaNotFound


COMPILER_VERSION = "timeline-compose/v1"


class TimelineOutputProfile(BaseModel):
    width: int = Field(gt=0)
    height: int = Field(gt=0)
    fps_num: int = Field(gt=0)
    fps_den: int = Field(default=1, gt=0)


class TimelineCompositionSpecView(BaseModel):
    id: str
    snapshot_id: str
    compiler_version: str
    output_profile: TimelineOutputProfile
    spec_json: str
    spec_sha256: str
    created_at: str


class TimelineCompileError(ValueError):
    pass


def _canonical(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class TimelineCompiler:
    def __init__(self, repo):
        self.repo = repo
        self.resolver = MediaIdentityResolver(repo.db, projects_root=repo.projects_root)

    def compile(self, snapshot_id: str, output_profile: TimelineOutputProfile) -> TimelineCompositionSpecView:
        with self.repo.db.connect() as conn:
            snapshot = conn.execute("SELECT * FROM timeline_snapshots WHERE id=?", (snapshot_id,)).fetchone()
        if snapshot is None:
            raise TimelineCompileError(f"Timeline snapshot not found: {snapshot_id}")
        state = json.loads(str(snapshot["state_json"]))
        project_id = str(state.get("project_id", ""))
        if not project_id:
            raise TimelineCompileError("Snapshot project identity is missing")

        resolved_by_id: dict[int, dict[str, object]] = {}
        for frozen in state.get("source_artifacts", []):
            artifact_id = int(frozen["artifact_id"])
            try:
                identity = self.resolver.resolve_artifact(artifact_id, verify_sha=True)
            except (TimelineMediaIntegrityError, TimelineMediaNotFound) as error:
                raise TimelineCompileError(f"Source integrity failed for artifact {artifact_id}: {error}") from error
            if identity.version != int(frozen["artifact_version"]):
                raise TimelineCompileError(f"Source integrity failed: artifact {artifact_id} version changed")
            if identity.sha256 != str(frozen["sha256"]):
                raise TimelineCompileError(f"Source integrity failed: artifact {artifact_id} SHA changed")
            if identity.path != str(frozen["path"]):
                raise TimelineCompileError(f"Source integrity failed: artifact {artifact_id} path changed")
            resolved_path = (Path(self.repo.projects_root) / project_id / identity.path).resolve()
            resolved_by_id[artifact_id] = {
                **dict(frozen),
                "resolved_path": str(resolved_path),
            }

        tracks: list[dict[str, object]] = []
        for track in state.get("tracks", []):
            compiled_track = {
                "id": track["id"],
                "track_type": track["track_type"],
                "role": track["role"],
                "name": track["name"],
                "sort_index": track["sort_index"],
                "muted": bool(track.get("muted", False)),
                "clips": [],
            }
            for clip in track.get("clips", []):
                artifact_id = clip.get("artifact_id")
                source = resolved_by_id.get(int(artifact_id)) if artifact_id is not None else None
                compiled_clip = {
                    "id": clip["id"],
                    "artifact_id": artifact_id,
                    "artifact_version": clip.get("artifact_version"),
                    "artifact_sha256": source.get("sha256") if source else None,
                    "source_path": source.get("resolved_path") if source else None,
                    "timeline_start_tick": int(clip["timeline_start_tick"]),
                    "duration_tick": int(clip["duration_tick"]),
                    "source_in_tick": int(clip["source_in_tick"]),
                    "source_out_tick": int(clip["source_out_tick"]),
                    "gain_db": clip.get("gain_db"),
                    "playback_rate_num": int(clip.get("playback_rate_num", 1)),
                    "playback_rate_den": int(clip.get("playback_rate_den", 1)),
                    "enabled": bool(clip.get("enabled", True)),
                    "shot_id": clip.get("shot_id", ""),
                    "scene_id": clip.get("scene_id", ""),
                }
                compiled_track["clips"].append(compiled_clip)
            tracks.append(compiled_track)

        spec = {
            "schema_version": 1,
            "compiler_version": COMPILER_VERSION,
            "timeline_snapshot_id": snapshot_id,
            "timeline_state_sha256": str(snapshot["state_sha256"]),
            "project_id": project_id,
            "timebase": dict(state["timebase"]),
            "output": output_profile.model_dump(mode="json"),
            "duration_tick": int(snapshot["duration_tick"]),
            "tracks": tracks,
            "transitions": list(state.get("transitions", [])),
            "subtitle_cues": list(state.get("subtitle_cues", [])),
            "source_artifacts": [resolved_by_id[key] for key in sorted(resolved_by_id)],
        }
        spec_json = _canonical(spec)
        spec_sha256 = hashlib.sha256(spec_json.encode("utf-8")).hexdigest()
        profile_json = _canonical(output_profile.model_dump(mode="json"))

        with self.repo.db.transaction(immediate=True) as conn:
            existing = conn.execute(
                "SELECT * FROM timeline_composition_specs WHERE snapshot_id=? AND spec_sha256=?",
                (snapshot_id, spec_sha256),
            ).fetchone()
            if existing is None:
                spec_id = f"timeline-spec-{uuid.uuid4().hex[:12]}"
                now = _now_iso()
                conn.execute(
                    """INSERT INTO timeline_composition_specs
                       (id,snapshot_id,output_profile_json,compiler_version,spec_json,spec_sha256,created_at)
                       VALUES (?,?,?,?,?,?,?)""",
                    (spec_id, snapshot_id, profile_json, COMPILER_VERSION, spec_json, spec_sha256, now),
                )
                existing = conn.execute(
                    "SELECT * FROM timeline_composition_specs WHERE id=?", (spec_id,)
                ).fetchone()
        return TimelineCompositionSpecView(
            id=str(existing["id"]),
            snapshot_id=str(existing["snapshot_id"]),
            compiler_version=str(existing["compiler_version"]),
            output_profile=TimelineOutputProfile(**json.loads(existing["output_profile_json"])),
            spec_json=str(existing["spec_json"]),
            spec_sha256=str(existing["spec_sha256"]),
            created_at=str(existing["created_at"]),
        )
