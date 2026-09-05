from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone

from backend.timeline.models import (
    LinkClipsOperation,
    MoveClipOperation,
    RemoveClipOperation,
    SplitClipOperation,
    TimelineClipView,
    TimelineDraftView,
    TimelineMutationResult,
    TimelineOperationRequest,
    TimelinePreflight,
    TimelineSummary,
    TimelineTrackView,
    TrimClipOperation,
    UnlinkClipsOperation,
)
from backend.timeline.repository import TimelineRepository
from backend.timeline.timebase import snap_video_tick


class TimelineNotFound(ValueError):
    pass


class TimelineRevisionConflict(ValueError):
    pass


class TimelineValidationError(ValueError):
    pass


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class TimelineService:
    def __init__(self, repo: TimelineRepository):
        self.repo = repo

    def initialize_project(self, project_id: str) -> tuple[TimelineDraftView, bool]:
        timeline, created = self.repo.initialize_project(project_id)
        return self._build_draft(str(timeline["id"])), created

    def get_project_timeline(self, project_id: str) -> TimelineSummary | None:
        timeline = self.repo.get_project_timeline(project_id)
        if timeline is None:
            return None
        draft = self.repo.get_draft(str(timeline["active_draft_id"]))
        if draft is None:
            raise TimelineNotFound(f"Active draft missing for timeline {timeline['id']}")
        return TimelineSummary(
            timeline_id=str(timeline["id"]),
            project_id=str(timeline["project_id"]),
            name=str(timeline["name"]),
            active_draft_id=str(timeline["active_draft_id"]),
            revision=int(draft["revision"]),
            timebase_hz=int(timeline["timebase_hz"]),
            fps_num=int(timeline["fps_num"]),
            fps_den=int(timeline["fps_den"]),
            latest_snapshot_no=int(timeline["latest_snapshot_no"]),
        )

    def get_draft(self, timeline_id: str) -> TimelineDraftView:
        return self._build_draft(timeline_id)

    def apply_operation(
        self,
        timeline_id: str,
        request: TimelineOperationRequest,
    ) -> TimelineMutationResult:
        with self.repo.db.transaction(immediate=True) as conn:
            timeline = conn.execute("SELECT * FROM timelines WHERE id=?", (timeline_id,)).fetchone()
            if timeline is None:
                raise TimelineNotFound(f"Timeline not found: {timeline_id}")
            draft = conn.execute(
                "SELECT * FROM timeline_drafts WHERE id=? AND timeline_id=?",
                (timeline["active_draft_id"], timeline_id),
            ).fetchone()
            if draft is None:
                raise TimelineNotFound(f"Active draft missing for timeline {timeline_id}")
            if int(draft["revision"]) != request.expected_revision:
                raise TimelineRevisionConflict(
                    f"expected revision {request.expected_revision}, current revision {draft['revision']}"
                )

            before = self._capture_inverse_state(conn, str(draft["id"]))
            operation = request.operation
            if isinstance(operation, MoveClipOperation):
                self._move_clip(conn, timeline, draft, operation)
            elif isinstance(operation, TrimClipOperation):
                self._trim_clip(conn, timeline, draft, operation)
            elif isinstance(operation, SplitClipOperation):
                self._split_clip(conn, timeline, draft, operation)
            elif isinstance(operation, RemoveClipOperation):
                self._remove_clip(conn, timeline, draft, operation)
            elif isinstance(operation, LinkClipsOperation):
                self._link_clips(conn, draft, operation)
            elif isinstance(operation, UnlinkClipsOperation):
                self._unlink_clips(conn, draft, operation)
            else:  # pragma: no cover - Pydantic discriminator is exhaustive
                raise TimelineValidationError(f"unsupported operation: {operation.type}")

            operation_seq = int(draft["head_operation_seq"]) + 1
            revision = int(draft["revision"]) + 1
            conn.execute(
                """INSERT INTO timeline_operations
                   (id, draft_id, seq, operation_type, payload_json, inverse_json,
                    branch_state, actor, created_at)
                   VALUES (?,?,?,?,?,?,'active','user',?)""",
                (
                    f"op-{uuid.uuid4().hex[:12]}",
                    draft["id"],
                    operation_seq,
                    operation.type,
                    operation.model_dump_json(),
                    json.dumps(before, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
                    _now_iso(),
                ),
            )
            conn.execute(
                """UPDATE timeline_drafts
                   SET revision=?, head_operation_seq=?, redo_operation_seq=NULL,
                       dirty=1, updated_at=?
                   WHERE id=?""",
                (revision, operation_seq, _now_iso(), draft["id"]),
            )

        return TimelineMutationResult(
            revision=revision,
            operation_seq=operation_seq,
            draft=self._build_draft(timeline_id),
            preflight=TimelinePreflight(),
        )

    def _move_clip(self, conn, timeline, draft, operation: MoveClipOperation) -> None:
        clip, track = self._require_editable_clip(conn, draft["id"], operation.clip_id)
        if track["role"] != "video.main":
            raise TimelineValidationError("MOVE_CLIP free-track positioning is not enabled in v0.10 core UI")
        if bool(operation.insert_before_clip_id) == bool(operation.insert_after_clip_id):
            raise TimelineValidationError("MOVE_CLIP requires exactly one insertion anchor")

        rows = conn.execute(
            """SELECT * FROM timeline_clips
               WHERE draft_id=? AND track_id=?
               ORDER BY timeline_start_tick, id""",
            (draft["id"], track["id"]),
        ).fetchall()
        ordered = [str(row["id"]) for row in rows if row["id"] != clip["id"]]
        anchor_id = operation.insert_before_clip_id or operation.insert_after_clip_id
        if anchor_id not in ordered:
            raise TimelineValidationError("MOVE_CLIP insertion anchor is not on the same track")
        anchor_index = ordered.index(str(anchor_id))
        insert_index = anchor_index if operation.insert_before_clip_id else anchor_index + 1
        ordered.insert(insert_index, str(clip["id"]))
        self._normalize_main_track(conn, draft["id"], track["id"], ordered)

    def _trim_clip(self, conn, timeline, draft, operation: TrimClipOperation) -> None:
        clip, track = self._require_editable_clip(conn, draft["id"], operation.clip_id)
        target = self._snap_if_video(timeline, clip, operation.target_source_tick)
        source_in = int(clip["source_in_tick"])
        source_out = int(clip["source_out_tick"])
        source_duration = self._artifact_duration_tick(conn, clip)

        if operation.edge == "right":
            if target <= source_in or target > source_duration:
                raise TimelineValidationError("source range exceeds artifact duration")
            source_out = target
        else:
            if target < 0 or target >= source_out:
                raise TimelineValidationError("source range is empty or invalid")
            source_in = target

        duration = source_out - source_in
        conn.execute(
            """UPDATE timeline_clips
               SET source_in_tick=?, source_out_tick=?, duration_tick=?, updated_at=?
               WHERE id=? AND draft_id=?""",
            (source_in, source_out, duration, _now_iso(), clip["id"], draft["id"]),
        )
        if track["role"] == "video.main":
            self._normalize_main_track(conn, draft["id"], track["id"])

    def _split_clip(self, conn, timeline, draft, operation: SplitClipOperation) -> None:
        clip, track = self._require_editable_clip(conn, draft["id"], operation.clip_id)
        split_tick = self._snap_if_video(timeline, clip, operation.timeline_tick)
        start = int(clip["timeline_start_tick"])
        end = start + int(clip["duration_tick"])
        if split_tick <= start or split_tick >= end:
            raise TimelineValidationError("split point must be inside clip")
        if int(clip["playback_rate_num"]) != int(clip["playback_rate_den"]):
            raise TimelineValidationError("split for rate-adjusted clips is not available in v0.10")

        left_duration = split_tick - start
        split_source = int(clip["source_in_tick"]) + left_duration
        right_duration = int(clip["source_out_tick"]) - split_source
        now = _now_iso()
        right_id = f"clip-{uuid.uuid4().hex[:12]}"
        conn.execute(
            """UPDATE timeline_clips
               SET source_out_tick=?, duration_tick=?, updated_at=?
               WHERE id=? AND draft_id=?""",
            (split_source, left_duration, now, clip["id"], draft["id"]),
        )
        conn.execute(
            """INSERT INTO timeline_clips
               (id, draft_id, track_id, artifact_id, artifact_version, clip_type,
                timeline_start_tick, duration_tick, source_in_tick, source_out_tick,
                link_group_id, enabled, locked, gain_db, playback_rate_num,
                playback_rate_den, metadata_json, created_at, updated_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                right_id,
                draft["id"],
                track["id"],
                clip["artifact_id"],
                clip["artifact_version"],
                clip["clip_type"],
                split_tick,
                right_duration,
                split_source,
                clip["source_out_tick"],
                clip["link_group_id"],
                clip["enabled"],
                clip["locked"],
                clip["gain_db"],
                clip["playback_rate_num"],
                clip["playback_rate_den"],
                clip["metadata_json"],
                now,
                now,
            ),
        )
        if track["role"] == "video.main":
            self._normalize_main_track(conn, draft["id"], track["id"])

    def _remove_clip(self, conn, timeline, draft, operation: RemoveClipOperation) -> None:
        clip, track = self._require_editable_clip(conn, draft["id"], operation.clip_id)
        if track["role"] == "video.main" and operation.mode != "ripple":
            raise TimelineValidationError("v0.10 main video track exposes ripple delete only")
        conn.execute("DELETE FROM timeline_clips WHERE id=? AND draft_id=?", (clip["id"], draft["id"]))
        if track["role"] == "video.main":
            self._normalize_main_track(conn, draft["id"], track["id"])

    def _link_clips(self, conn, draft, operation: LinkClipsOperation) -> None:
        rows = self._require_clips(conn, draft["id"], operation.clip_ids)
        if any(row["link_group_id"] for row in rows):
            raise TimelineValidationError("one or more clips already belong to a link group")
        group_id = f"link-{uuid.uuid4().hex[:12]}"
        conn.execute(
            """INSERT INTO timeline_link_groups
               (id, draft_id, group_type, anchor_clip_id, created_at)
               VALUES (?,?,'av',?,?)""",
            (group_id, draft["id"], rows[0]["id"], _now_iso()),
        )
        placeholders = ",".join("?" for _ in rows)
        conn.execute(
            f"UPDATE timeline_clips SET link_group_id=?, updated_at=? WHERE draft_id=? AND id IN ({placeholders})",
            (group_id, _now_iso(), draft["id"], *[row["id"] for row in rows]),
        )

    def _unlink_clips(self, conn, draft, operation: UnlinkClipsOperation) -> None:
        rows = self._require_clips(conn, draft["id"], operation.clip_ids)
        groups = {str(row["link_group_id"]) for row in rows if row["link_group_id"]}
        placeholders = ",".join("?" for _ in rows)
        conn.execute(
            f"UPDATE timeline_clips SET link_group_id=NULL, updated_at=? WHERE draft_id=? AND id IN ({placeholders})",
            (_now_iso(), draft["id"], *[row["id"] for row in rows]),
        )
        for group_id in groups:
            remaining = conn.execute(
                "SELECT COUNT(*) AS n FROM timeline_clips WHERE draft_id=? AND link_group_id=?",
                (draft["id"], group_id),
            ).fetchone()
            if remaining is not None and int(remaining["n"]) < 2:
                conn.execute(
                    "UPDATE timeline_clips SET link_group_id=NULL WHERE draft_id=? AND link_group_id=?",
                    (draft["id"], group_id),
                )
                conn.execute("DELETE FROM timeline_link_groups WHERE id=? AND draft_id=?", (group_id, draft["id"]))

    def _require_editable_clip(self, conn, draft_id: str, clip_id: str):
        row = conn.execute(
            """SELECT c.*, t.role AS track_role, t.locked AS track_locked
               FROM timeline_clips c
               JOIN timeline_tracks t ON t.id=c.track_id
               WHERE c.id=? AND c.draft_id=? AND t.draft_id=?""",
            (clip_id, draft_id, draft_id),
        ).fetchone()
        if row is None:
            raise TimelineValidationError(f"clip not found: {clip_id}")
        if bool(row["locked"]) or bool(row["track_locked"]):
            raise TimelineValidationError("clip or track is locked")
        track = conn.execute("SELECT * FROM timeline_tracks WHERE id=?", (row["track_id"],)).fetchone()
        return row, track

    def _require_clips(self, conn, draft_id: str, clip_ids: list[str]):
        if len(set(clip_ids)) != len(clip_ids):
            raise TimelineValidationError("clip ids must be unique")
        placeholders = ",".join("?" for _ in clip_ids)
        rows = conn.execute(
            f"""SELECT c.*, t.locked AS track_locked
                FROM timeline_clips c
                JOIN timeline_tracks t ON t.id=c.track_id
                WHERE c.draft_id=? AND c.id IN ({placeholders})""",
            (draft_id, *clip_ids),
        ).fetchall()
        if len(rows) != len(clip_ids):
            raise TimelineValidationError("one or more clips were not found in the active draft")
        by_id = {str(row["id"]): row for row in rows}
        ordered = [by_id[clip_id] for clip_id in clip_ids]
        if any(bool(row["locked"]) or bool(row["track_locked"]) for row in ordered):
            raise TimelineValidationError("clip or track is locked")
        return ordered

    def _normalize_main_track(self, conn, draft_id: str, track_id: str, ordered_ids: list[str] | None = None) -> None:
        rows = conn.execute(
            """SELECT id, duration_tick FROM timeline_clips
               WHERE draft_id=? AND track_id=?
               ORDER BY timeline_start_tick, id""",
            (draft_id, track_id),
        ).fetchall()
        by_id = {str(row["id"]): row for row in rows}
        if ordered_ids is None:
            ordered_ids = [str(row["id"]) for row in rows]
        if set(ordered_ids) != set(by_id):
            raise TimelineValidationError("main track normalization lost clip identity")
        cursor = 0
        now = _now_iso()
        for clip_id in ordered_ids:
            row = by_id[clip_id]
            duration = int(row["duration_tick"])
            if duration <= 0:
                raise TimelineValidationError("clip duration must be positive")
            conn.execute(
                "UPDATE timeline_clips SET timeline_start_tick=?, updated_at=? WHERE id=? AND draft_id=?",
                (cursor, now, clip_id, draft_id),
            )
            cursor += duration

    def _artifact_duration_tick(self, conn, clip) -> int:
        if clip["artifact_id"] is None:
            return int(clip["source_out_tick"])
        artifact = conn.execute("SELECT metadata FROM artifacts WHERE id=?", (clip["artifact_id"],)).fetchone()
        if artifact is None:
            raise TimelineValidationError("source artifact is missing")
        metadata = json.loads(artifact["metadata"] or "{}")
        duration = int(metadata.get("duration_tick") or 0)
        return duration if duration > 0 else int(clip["source_out_tick"])

    def _snap_if_video(self, timeline, clip, tick: int) -> int:
        if str(clip["clip_type"]) != "video":
            return tick
        return snap_video_tick(
            tick,
            ticks_per_second=int(timeline["timebase_hz"]),
            fps_num=int(timeline["fps_num"]),
            fps_den=int(timeline["fps_den"]),
        )

    def _capture_inverse_state(self, conn, draft_id: str) -> dict[str, object]:
        clips = [dict(row) for row in conn.execute(
            "SELECT * FROM timeline_clips WHERE draft_id=? ORDER BY track_id, timeline_start_tick, id",
            (draft_id,),
        ).fetchall()]
        groups = [dict(row) for row in conn.execute(
            "SELECT * FROM timeline_link_groups WHERE draft_id=? ORDER BY id",
            (draft_id,),
        ).fetchall()]
        return {"type": "RESTORE_DRAFT_STATE", "clips": clips, "link_groups": groups}

    def _build_draft(self, timeline_id: str) -> TimelineDraftView:
        timeline = self.repo.get_timeline(timeline_id)
        if timeline is None:
            raise TimelineNotFound(f"Timeline not found: {timeline_id}")
        draft = self.repo.get_active_draft_for_timeline(timeline_id)
        if draft is None:
            raise TimelineNotFound(f"Active draft missing for timeline {timeline_id}")

        clips = self.repo.list_clips(str(draft["id"]))
        clips_by_track: dict[str, list[TimelineClipView]] = {}
        for clip in clips:
            artifact_id = clip["artifact_id"]
            project_id = str(clip.get("artifact_project_id") or timeline["project_id"])
            media_url = ""
            if artifact_id is not None:
                media_url = f"/api/workspace/{project_id}/assets/{artifact_id}/media"
            clips_by_track.setdefault(str(clip["track_id"]), []).append(
                TimelineClipView(
                    id=str(clip["id"]),
                    track_id=str(clip["track_id"]),
                    artifact_id=int(artifact_id) if artifact_id is not None else None,
                    artifact_version=int(clip["artifact_version"]) if clip["artifact_version"] is not None else None,
                    clip_type=str(clip["clip_type"]),
                    timeline_start_tick=int(clip["timeline_start_tick"]),
                    duration_tick=int(clip["duration_tick"]),
                    source_in_tick=int(clip["source_in_tick"]),
                    source_out_tick=int(clip["source_out_tick"]),
                    link_group_id=str(clip["link_group_id"]) if clip["link_group_id"] else None,
                    enabled=bool(clip["enabled"]),
                    locked=bool(clip["locked"]),
                    shot_id=str(clip.get("artifact_shot_id") or ""),
                    scene_id=str(clip.get("artifact_scene_id") or ""),
                    media_url=media_url,
                )
            )

        tracks = [
            TimelineTrackView(
                id=str(track["id"]),
                track_type=str(track["track_type"]),
                role=str(track["role"]),
                name=str(track["name"]),
                sort_index=int(track["sort_index"]),
                locked=bool(track["locked"]),
                muted=bool(track["muted"]),
                hidden=bool(track["hidden"]),
                clips=clips_by_track.get(str(track["id"]), []),
            )
            for track in self.repo.list_tracks(str(draft["id"]))
        ]
        return TimelineDraftView(
            timeline_id=str(timeline["id"]),
            draft_id=str(draft["id"]),
            project_id=str(timeline["project_id"]),
            revision=int(draft["revision"]),
            timebase_hz=int(timeline["timebase_hz"]),
            fps_num=int(timeline["fps_num"]),
            fps_den=int(timeline["fps_den"]),
            tracks=tracks,
        )
