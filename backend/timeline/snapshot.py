from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timezone

from backend.timeline.media import MediaIdentityResolver
from backend.timeline.models import TimelineSnapshotView


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _snapshot_view(row) -> TimelineSnapshotView:
    return TimelineSnapshotView(
        id=str(row["id"]),
        timeline_id=str(row["timeline_id"]),
        snapshot_no=int(row["snapshot_no"]),
        source_draft_revision=int(row["source_draft_revision"]),
        state_sha256=str(row["state_sha256"]),
        duration_tick=int(row["duration_tick"]),
        created_at=str(row["created_at"]),
    )


def create_snapshot(service, timeline_id: str) -> TimelineSnapshotView:
    repo = service.repo
    resolver = MediaIdentityResolver(repo.db, projects_root=repo.projects_root)
    with repo.db.transaction(immediate=True) as conn:
        timeline = conn.execute("SELECT * FROM timelines WHERE id=?", (timeline_id,)).fetchone()
        if timeline is None:
            raise ValueError(f"Timeline not found: {timeline_id}")
        draft = conn.execute(
            "SELECT * FROM timeline_drafts WHERE id=? AND timeline_id=?",
            (timeline["active_draft_id"], timeline_id),
        ).fetchone()
        if draft is None:
            raise ValueError(f"Active draft missing for timeline {timeline_id}")

        service._save_checkpoint(
            conn,
            str(draft["id"]),
            int(draft["head_operation_seq"]),
            int(draft["revision"]),
        )
        draft_view = service._build_draft(timeline_id)
        clip_views = [clip for track in draft_view.tracks for clip in track.clips]
        duration_tick = max(
            [clip.timeline_start_tick + clip.duration_tick for clip in clip_views]
            + [cue.end_tick for cue in draft_view.subtitle_cues]
            + [0]
        )
        if duration_tick <= 0:
            raise ValueError("timeline snapshot requires positive duration")

        sources: list[dict[str, object]] = []
        seen: set[int] = set()
        for clip in clip_views:
            if clip.artifact_id is None or clip.artifact_id in seen:
                continue
            identity = resolver.resolve_artifact(clip.artifact_id, verify_sha=True)
            if clip.artifact_version is not None and identity.version != clip.artifact_version:
                raise ValueError(f"Artifact version mismatch: {clip.artifact_id}")
            seen.add(clip.artifact_id)
            sources.append(
                {
                    "artifact_id": identity.artifact_id,
                    "artifact_version": identity.version,
                    "path": identity.path,
                    "sha256": identity.sha256,
                    "duration_tick": identity.duration_tick,
                    "kind": identity.kind,
                    "shot_id": identity.shot_id,
                    "scene_id": identity.scene_id,
                }
            )
        sources.sort(key=lambda item: int(item["artifact_id"]))

        tracks: list[dict[str, object]] = []
        for track in draft_view.tracks:
            track_payload = track.model_dump(mode="json")
            for clip_payload in track_payload.get("clips", []):
                clip_payload.pop("media_url", None)
            tracks.append(track_payload)

        payload = {
            "schema_version": 1,
            "timeline_id": timeline_id,
            "project_id": str(timeline["project_id"]),
            "source_draft_revision": int(draft["revision"]),
            "timebase": {
                "ticks_per_second": int(timeline["timebase_hz"]),
                "fps_num": int(timeline["fps_num"]),
                "fps_den": int(timeline["fps_den"]),
            },
            "tracks": tracks,
            "subtitle_cues": [item.model_dump(mode="json") for item in draft_view.subtitle_cues],
            "transitions": [item.model_dump(mode="json") for item in draft_view.transitions],
            "source_artifacts": sources,
        }
        encoded = _canonical_json(payload)
        digest = hashlib.sha256(encoded.encode("utf-8")).hexdigest()
        snapshot_no = int(timeline["latest_snapshot_no"]) + 1
        snapshot_id = f"snapshot-{uuid.uuid4().hex[:12]}"
        now = _now_iso()
        conn.execute(
            """INSERT INTO timeline_snapshots
               (id, timeline_id, snapshot_no, source_draft_revision, state_json,
                state_sha256, duration_tick, created_at)
               VALUES (?,?,?,?,?,?,?,?)""",
            (
                snapshot_id,
                timeline_id,
                snapshot_no,
                int(draft["revision"]),
                encoded,
                digest,
                duration_tick,
                now,
            ),
        )
        conn.execute(
            "UPDATE timelines SET latest_snapshot_no=?, updated_at=? WHERE id=?",
            (snapshot_no, now, timeline_id),
        )
        row = conn.execute("SELECT * FROM timeline_snapshots WHERE id=?", (snapshot_id,)).fetchone()
    return _snapshot_view(row)


def list_snapshots(repo, timeline_id: str) -> list[TimelineSnapshotView]:
    with repo.db.connect() as conn:
        rows = conn.execute(
            "SELECT * FROM timeline_snapshots WHERE timeline_id=? ORDER BY snapshot_no",
            (timeline_id,),
        ).fetchall()
    return [_snapshot_view(row) for row in rows]


def get_snapshot(repo, timeline_id: str, snapshot_id: str) -> TimelineSnapshotView:
    with repo.db.connect() as conn:
        row = conn.execute(
            "SELECT * FROM timeline_snapshots WHERE timeline_id=? AND id=?",
            (timeline_id, snapshot_id),
        ).fetchone()
    if row is None:
        raise ValueError(f"Timeline snapshot not found: {snapshot_id}")
    return _snapshot_view(row)
