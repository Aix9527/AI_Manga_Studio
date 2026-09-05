from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timezone

from backend.timeline.models import (
    AddSubtitleOperation,
    AddTransitionOperation,
    LinkClipsOperation,
    MoveClipOperation,
    RemoveClipOperation,
    RemoveSubtitleOperation,
    RemoveTransitionOperation,
    ReplaceArtifactVersionOperation,
    SplitClipOperation,
    TimelineClipView,
    TimelineDraftView,
    TimelineMutationResult,
    TimelineOperationRequest,
    TimelinePreflight,
    TimelineSubtitleCueView,
    TimelineSummary,
    TimelineTrackView,
    TimelineTransitionView,
    TrimClipOperation,
    UnlinkClipsOperation,
    UpdateSubtitleOperation,
    UpdateTransitionOperation,
)
from backend.timeline.repository import TimelineRepository
from backend.timeline.timebase import snap_video_tick


class TimelineNotFound(ValueError):
    pass


class TimelineRevisionConflict(ValueError):
    pass


class TimelineValidationError(ValueError):
    pass


class TimelineRedoUnavailable(ValueError):
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

    def create_snapshot(self, timeline_id: str):
        from backend.timeline.snapshot import create_snapshot
        return create_snapshot(self, timeline_id)

    def list_snapshots(self, timeline_id: str):
        from backend.timeline.snapshot import list_snapshots
        if self.repo.get_timeline(timeline_id) is None:
            raise TimelineNotFound(f"Timeline not found: {timeline_id}")
        return list_snapshots(self.repo, timeline_id)

    def get_snapshot(self, timeline_id: str, snapshot_id: str):
        from backend.timeline.snapshot import get_snapshot
        if self.repo.get_timeline(timeline_id) is None:
            raise TimelineNotFound(f"Timeline not found: {timeline_id}")
        try:
            return get_snapshot(self.repo, timeline_id, snapshot_id)
        except ValueError as error:
            raise TimelineNotFound(str(error)) from error

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

            head_seq = int(draft["head_operation_seq"])
            conn.execute(
                """UPDATE timeline_operations SET branch_state='abandoned'
                   WHERE draft_id=? AND branch_state='active' AND seq>?""",
                (draft["id"], head_seq),
            )
            max_row = conn.execute(
                "SELECT COALESCE(MAX(seq), 0) AS seq FROM timeline_operations WHERE draft_id=?",
                (draft["id"],),
            ).fetchone()
            before = self._capture_inverse_state(conn, str(draft["id"]))
            operation = request.operation
            self._apply_operation_in_tx(conn, timeline, draft, operation)

            operation_seq = int(max_row["seq"]) + 1
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
            if operation_seq % 50 == 0:
                self._save_checkpoint(conn, str(draft["id"]), operation_seq, revision)

        return TimelineMutationResult(
            revision=revision,
            operation_seq=operation_seq,
            draft=self._build_draft(timeline_id),
            preflight=TimelinePreflight(),
        )

    def undo(self, timeline_id: str, *, expected_revision: int) -> TimelineMutationResult:
        with self.repo.db.transaction(immediate=True) as conn:
            timeline, draft = self._require_history_context(conn, timeline_id, expected_revision)
            head_seq = int(draft["head_operation_seq"])
            if head_seq <= 0:
                raise TimelineValidationError("undo is not available")
            target = conn.execute(
                """SELECT * FROM timeline_operations
                   WHERE draft_id=? AND seq=? AND branch_state='active'""",
                (draft["id"], head_seq),
            ).fetchone()
            if target is None:
                raise TimelineValidationError("undo history head is unavailable")
            self._restore_inverse_state(conn, str(draft["id"]), json.loads(target["inverse_json"]))
            previous = conn.execute(
                """SELECT COALESCE(MAX(seq), 0) AS seq FROM timeline_operations
                   WHERE draft_id=? AND branch_state='active' AND seq<?""",
                (draft["id"], target["seq"]),
            ).fetchone()
            revision = int(draft["revision"]) + 1
            new_head = int(previous["seq"])
            conn.execute(
                """UPDATE timeline_drafts
                   SET revision=?, head_operation_seq=?, redo_operation_seq=?, dirty=1, updated_at=?
                   WHERE id=?""",
                (revision, new_head, int(target["seq"]), _now_iso(), draft["id"]),
            )
        return TimelineMutationResult(
            revision=revision,
            operation_seq=new_head,
            draft=self._build_draft(timeline_id),
            preflight=TimelinePreflight(),
        )

    def redo(self, timeline_id: str, *, expected_revision: int) -> TimelineMutationResult:
        with self.repo.db.transaction(immediate=True) as conn:
            timeline, draft = self._require_history_context(conn, timeline_id, expected_revision)
            head_seq = int(draft["head_operation_seq"])
            target = conn.execute(
                """SELECT * FROM timeline_operations
                   WHERE draft_id=? AND branch_state='active' AND seq>?
                   ORDER BY seq LIMIT 1""",
                (draft["id"], head_seq),
            ).fetchone()
            if target is None:
                raise TimelineRedoUnavailable("redo is not available")
            operation = TimelineOperationRequest(
                expected_revision=expected_revision,
                operation=json.loads(target["payload_json"]),
            ).operation
            self._apply_operation_in_tx(conn, timeline, draft, operation)
            revision = int(draft["revision"]) + 1
            next_redo = conn.execute(
                """SELECT MIN(seq) AS seq FROM timeline_operations
                   WHERE draft_id=? AND branch_state='active' AND seq>?""",
                (draft["id"], target["seq"]),
            ).fetchone()
            conn.execute(
                """UPDATE timeline_drafts
                   SET revision=?, head_operation_seq=?, redo_operation_seq=?, dirty=1, updated_at=?
                   WHERE id=?""",
                (
                    revision,
                    int(target["seq"]),
                    int(next_redo["seq"]) if next_redo and next_redo["seq"] is not None else None,
                    _now_iso(),
                    draft["id"],
                ),
            )
        return TimelineMutationResult(
            revision=revision,
            operation_seq=int(target["seq"]),
            draft=self._build_draft(timeline_id),
            preflight=TimelinePreflight(),
        )

    def _require_history_context(self, conn, timeline_id: str, expected_revision: int):
        timeline = conn.execute("SELECT * FROM timelines WHERE id=?", (timeline_id,)).fetchone()
        if timeline is None:
            raise TimelineNotFound(f"Timeline not found: {timeline_id}")
        draft = conn.execute(
            "SELECT * FROM timeline_drafts WHERE id=? AND timeline_id=?",
            (timeline["active_draft_id"], timeline_id),
        ).fetchone()
        if draft is None:
            raise TimelineNotFound(f"Active draft missing for timeline {timeline_id}")
        if int(draft["revision"]) != expected_revision:
            raise TimelineRevisionConflict(
                f"expected revision {expected_revision}, current revision {draft['revision']}"
            )
        return timeline, draft

    def _apply_operation_in_tx(self, conn, timeline, draft, operation) -> None:
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
        elif isinstance(operation, AddTransitionOperation):
            self._add_transition(conn, timeline, draft, operation)
        elif isinstance(operation, UpdateTransitionOperation):
            self._update_transition(conn, timeline, draft, operation)
        elif isinstance(operation, RemoveTransitionOperation):
            self._remove_transition(conn, draft, operation)
        elif isinstance(operation, AddSubtitleOperation):
            self._add_subtitle(conn, draft, operation)
        elif isinstance(operation, UpdateSubtitleOperation):
            self._update_subtitle(conn, draft, operation)
        elif isinstance(operation, RemoveSubtitleOperation):
            self._remove_subtitle(conn, draft, operation)
        elif isinstance(operation, ReplaceArtifactVersionOperation):
            self._replace_artifact_version(conn, draft, operation)
        else:
            raise TimelineValidationError(f"unsupported operation: {operation.type}")

    def _restore_inverse_state(self, conn, draft_id: str, state: dict[str, object]) -> None:
        if state.get("type") != "RESTORE_DRAFT_STATE":
            raise TimelineValidationError("unsupported undo payload")
        conn.execute("DELETE FROM timeline_transitions WHERE draft_id=?", (draft_id,))
        conn.execute("DELETE FROM timeline_subtitle_cues WHERE draft_id=?", (draft_id,))
        conn.execute("DELETE FROM timeline_clips WHERE draft_id=?", (draft_id,))
        conn.execute("DELETE FROM timeline_link_groups WHERE draft_id=?", (draft_id,))
        for group in state.get("link_groups", []):
            conn.execute(
                """INSERT INTO timeline_link_groups
                   (id, draft_id, group_type, anchor_clip_id, created_at)
                   VALUES (?,?,?,?,?)""",
                (group["id"], group["draft_id"], group["group_type"], group["anchor_clip_id"], group["created_at"]),
            )
        for clip in state.get("clips", []):
            conn.execute(
                """INSERT INTO timeline_clips
                   (id, draft_id, track_id, artifact_id, artifact_version, clip_type,
                    timeline_start_tick, duration_tick, source_in_tick, source_out_tick,
                    link_group_id, enabled, locked, gain_db, playback_rate_num,
                    playback_rate_den, metadata_json, created_at, updated_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    clip["id"], clip["draft_id"], clip["track_id"], clip["artifact_id"],
                    clip["artifact_version"], clip["clip_type"], clip["timeline_start_tick"],
                    clip["duration_tick"], clip["source_in_tick"], clip["source_out_tick"],
                    clip["link_group_id"], clip["enabled"], clip["locked"], clip["gain_db"],
                    clip["playback_rate_num"], clip["playback_rate_den"], clip["metadata_json"],
                    clip["created_at"], clip["updated_at"],
                ),
            )
        for cue in state.get("subtitle_cues", []):
            conn.execute(
                """INSERT INTO timeline_subtitle_cues
                   (id, draft_id, track_id, clip_id, link_group_id, start_tick, end_tick,
                    text, speaker, style_json, created_at, updated_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    cue["id"], cue["draft_id"], cue["track_id"], cue["clip_id"], cue["link_group_id"],
                    cue["start_tick"], cue["end_tick"], cue["text"], cue["speaker"], cue["style_json"],
                    cue["created_at"], cue["updated_at"],
                ),
            )
        for transition in state.get("transitions", []):
            conn.execute(
                """INSERT INTO timeline_transitions
                   (id, draft_id, track_id, from_clip_id, to_clip_id, transition_type,
                    duration_tick, params_json, created_at, updated_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?)""",
                (
                    transition["id"], transition["draft_id"], transition["track_id"],
                    transition["from_clip_id"], transition["to_clip_id"], transition["transition_type"],
                    transition["duration_tick"], transition["params_json"], transition["created_at"],
                    transition["updated_at"],
                ),
            )

    def _save_checkpoint(self, conn, draft_id: str, operation_seq: int, revision: int) -> None:
        state = self._capture_inverse_state(conn, draft_id)
        encoded = json.dumps(state, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        digest = hashlib.sha256(encoded.encode("utf-8")).hexdigest()
        conn.execute(
            """INSERT INTO timeline_checkpoints
               (id, draft_id, operation_seq, revision, state_json, state_sha256, created_at)
               VALUES (?,?,?,?,?,?,?)""",
            (f"checkpoint-{uuid.uuid4().hex[:12]}", draft_id, operation_seq, revision, encoded, digest, _now_iso()),
        )

    def _add_transition(self, conn, timeline, draft, operation: AddTransitionOperation) -> None:
        from_clip, from_track = self._require_editable_clip(conn, draft["id"], operation.from_clip_id)
        to_clip, to_track = self._require_editable_clip(conn, draft["id"], operation.to_clip_id)
        if from_track["id"] != to_track["id"] or from_track["role"] != "video.main":
            raise TimelineValidationError("transition clips must be adjacent on video.main")
        ordered = conn.execute(
            """SELECT id FROM timeline_clips WHERE draft_id=? AND track_id=?
               ORDER BY timeline_start_tick, id""",
            (draft["id"], from_track["id"]),
        ).fetchall()
        ids = [str(row["id"]) for row in ordered]
        if operation.from_clip_id not in ids or operation.to_clip_id not in ids or ids.index(operation.to_clip_id) != ids.index(operation.from_clip_id) + 1:
            raise TimelineValidationError("transition clips must be adjacent on video.main")
        existing = conn.execute(
            "SELECT id FROM timeline_transitions WHERE draft_id=? AND from_clip_id=? AND to_clip_id=?",
            (draft["id"], from_clip["id"], to_clip["id"]),
        ).fetchone()
        if existing is not None:
            raise TimelineValidationError("transition already exists at this cut")
        duration = self._snap_if_video(timeline, from_clip, operation.duration_tick)
        if duration <= 0:
            raise TimelineValidationError("transition duration must be positive")
        from_right_handle = self._artifact_duration_tick(conn, from_clip) - int(from_clip["source_out_tick"])
        to_left_handle = int(to_clip["source_in_tick"])
        if from_right_handle < duration or to_left_handle < duration:
            raise TimelineValidationError("transition handles are insufficient")
        now = _now_iso()
        conn.execute(
            """UPDATE timeline_clips
               SET source_out_tick=source_out_tick+?, duration_tick=duration_tick+?, updated_at=?
               WHERE id=?""",
            (duration, duration, now, from_clip["id"]),
        )
        conn.execute(
            """UPDATE timeline_clips
               SET source_in_tick=source_in_tick-?, duration_tick=duration_tick+?, updated_at=?
               WHERE id=?""",
            (duration, duration, now, to_clip["id"]),
        )
        transition_id = f"transition-{uuid.uuid4().hex[:12]}"
        params = dict(operation.params)
        params["source_extension_tick"] = duration
        conn.execute(
            """INSERT INTO timeline_transitions
               (id, draft_id, track_id, from_clip_id, to_clip_id, transition_type,
                duration_tick, params_json, created_at, updated_at)
               VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (
                transition_id, draft["id"], from_track["id"], from_clip["id"], to_clip["id"],
                operation.transition_type, duration,
                json.dumps(params, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
                now, now,
            ),
        )
        self._normalize_main_track_with_transitions(conn, draft["id"], from_track["id"])

    def _update_transition(self, conn, timeline, draft, operation: UpdateTransitionOperation) -> None:
        row = conn.execute(
            "SELECT * FROM timeline_transitions WHERE id=? AND draft_id=?",
            (operation.transition_id, draft["id"]),
        ).fetchone()
        if row is None:
            raise TimelineValidationError("transition not found")
        if operation.duration_tick is not None and int(operation.duration_tick) != int(row["duration_tick"]):
            raise TimelineValidationError("changing transition duration requires remove and add in v0.10")
        if operation.params is not None:
            conn.execute(
                "UPDATE timeline_transitions SET params_json=?, updated_at=? WHERE id=?",
                (json.dumps(operation.params, ensure_ascii=False, sort_keys=True, separators=(",", ":")), _now_iso(), row["id"]),
            )

    def _remove_transition(self, conn, draft, operation: RemoveTransitionOperation) -> None:
        row = conn.execute(
            "SELECT * FROM timeline_transitions WHERE id=? AND draft_id=?",
            (operation.transition_id, draft["id"]),
        ).fetchone()
        if row is None:
            raise TimelineValidationError("transition not found")
        duration = int(row["duration_tick"])
        from_clip = conn.execute("SELECT * FROM timeline_clips WHERE id=?", (row["from_clip_id"],)).fetchone()
        to_clip = conn.execute("SELECT * FROM timeline_clips WHERE id=?", (row["to_clip_id"],)).fetchone()
        if from_clip is None or to_clip is None:
            raise TimelineValidationError("transition clip is missing")
        conn.execute(
            "UPDATE timeline_clips SET source_out_tick=source_out_tick-?, duration_tick=duration_tick-?, updated_at=? WHERE id=?",
            (duration, duration, _now_iso(), from_clip["id"]),
        )
        conn.execute(
            "UPDATE timeline_clips SET source_in_tick=source_in_tick+?, duration_tick=duration_tick-?, updated_at=? WHERE id=?",
            (duration, duration, _now_iso(), to_clip["id"]),
        )
        conn.execute("DELETE FROM timeline_transitions WHERE id=?", (row["id"],))
        self._normalize_main_track_with_transitions(conn, draft["id"], row["track_id"])

    def _add_subtitle(self, conn, draft, operation: AddSubtitleOperation) -> None:
        track = conn.execute(
            "SELECT * FROM timeline_tracks WHERE id=? AND draft_id=?",
            (operation.track_id, draft["id"]),
        ).fetchone()
        if track is None or track["track_type"] != "subtitle":
            raise TimelineValidationError("subtitle track not found")
        if bool(track["locked"]):
            raise TimelineValidationError("clip or track is locked")
        if operation.end_tick <= operation.start_tick:
            raise TimelineValidationError("subtitle range must have positive duration")
        conn.execute(
            """INSERT INTO timeline_subtitle_cues
               (id, draft_id, track_id, clip_id, link_group_id, start_tick, end_tick,
                text, speaker, style_json, created_at, updated_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                f"subtitle-{uuid.uuid4().hex[:12]}", draft["id"], operation.track_id,
                operation.clip_id, operation.link_group_id, operation.start_tick, operation.end_tick,
                operation.text, operation.speaker,
                json.dumps(operation.style, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
                _now_iso(), _now_iso(),
            ),
        )

    def _update_subtitle(self, conn, draft, operation: UpdateSubtitleOperation) -> None:
        cue = conn.execute(
            "SELECT * FROM timeline_subtitle_cues WHERE id=? AND draft_id=?",
            (operation.cue_id, draft["id"]),
        ).fetchone()
        if cue is None:
            raise TimelineValidationError("subtitle cue not found")
        start_tick = operation.start_tick if operation.start_tick is not None else int(cue["start_tick"])
        end_tick = operation.end_tick if operation.end_tick is not None else int(cue["end_tick"])
        if end_tick <= start_tick:
            raise TimelineValidationError("subtitle range must have positive duration")
        text_value = operation.text if operation.text is not None else str(cue["text"])
        speaker = operation.speaker if operation.speaker is not None else str(cue["speaker"])
        style = operation.style if operation.style is not None else json.loads(cue["style_json"] or "{}")
        conn.execute(
            """UPDATE timeline_subtitle_cues
               SET start_tick=?, end_tick=?, text=?, speaker=?, style_json=?, updated_at=?
               WHERE id=?""",
            (start_tick, end_tick, text_value, speaker, json.dumps(style, ensure_ascii=False, sort_keys=True, separators=(",", ":")), _now_iso(), cue["id"]),
        )

    def _remove_subtitle(self, conn, draft, operation: RemoveSubtitleOperation) -> None:
        cursor = conn.execute(
            "DELETE FROM timeline_subtitle_cues WHERE id=? AND draft_id=?",
            (operation.cue_id, draft["id"]),
        )
        if cursor.rowcount != 1:
            raise TimelineValidationError("subtitle cue not found")

    def _replace_artifact_version(self, conn, draft, operation: ReplaceArtifactVersionOperation) -> None:
        clips = self._require_clips(conn, draft["id"], operation.clip_ids)
        artifact = conn.execute("SELECT * FROM artifacts WHERE id=?", (operation.artifact_id,)).fetchone()
        if artifact is None:
            raise TimelineValidationError("replacement artifact not found")
        metadata = json.loads(artifact["metadata"] or "{}")
        duration = int(metadata.get("duration_tick") or 0)
        if duration <= 0:
            raise TimelineValidationError("replacement artifact duration is unknown")
        for clip in clips:
            if duration < int(clip["source_out_tick"]):
                raise TimelineValidationError("replacement_media_too_short")
        for clip in clips:
            conn.execute(
                """UPDATE timeline_clips SET artifact_id=?, artifact_version=?, updated_at=?
                   WHERE id=? AND draft_id=?""",
                (artifact["id"], artifact["version"], _now_iso(), clip["id"], draft["id"]),
            )

    def _normalize_main_track_with_transitions(self, conn, draft_id: str, track_id: str) -> None:
        rows = conn.execute(
            """SELECT id, duration_tick FROM timeline_clips
               WHERE draft_id=? AND track_id=? ORDER BY timeline_start_tick, id""",
            (draft_id, track_id),
        ).fetchall()
        cursor = 0
        previous_id = None
        for row in rows:
            overlap = 0
            if previous_id is not None:
                transition = conn.execute(
                    """SELECT duration_tick FROM timeline_transitions
                       WHERE draft_id=? AND track_id=? AND from_clip_id=? AND to_clip_id=?""",
                    (draft_id, track_id, previous_id, row["id"]),
                ).fetchone()
                if transition is not None:
                    overlap = int(transition["duration_tick"])
            start = max(0, cursor - overlap)
            conn.execute(
                "UPDATE timeline_clips SET timeline_start_tick=?, updated_at=? WHERE id=?",
                (start, _now_iso(), row["id"]),
            )
            cursor = start + int(row["duration_tick"])
            previous_id = str(row["id"])

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
        subtitle_cues = [dict(row) for row in conn.execute(
            "SELECT * FROM timeline_subtitle_cues WHERE draft_id=? ORDER BY track_id, start_tick, id",
            (draft_id,),
        ).fetchall()]
        transitions = [dict(row) for row in conn.execute(
            "SELECT * FROM timeline_transitions WHERE draft_id=? ORDER BY track_id, from_clip_id, to_clip_id, id",
            (draft_id,),
        ).fetchall()]
        return {
            "type": "RESTORE_DRAFT_STATE",
            "clips": clips,
            "link_groups": groups,
            "subtitle_cues": subtitle_cues,
            "transitions": transitions,
        }

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
        with self.repo.db.connect() as conn:
            cue_rows = conn.execute(
                "SELECT * FROM timeline_subtitle_cues WHERE draft_id=? ORDER BY start_tick, id",
                (draft["id"],),
            ).fetchall()
            transition_rows = conn.execute(
                "SELECT * FROM timeline_transitions WHERE draft_id=? ORDER BY track_id, from_clip_id, id",
                (draft["id"],),
            ).fetchall()
        subtitle_cues = [
            TimelineSubtitleCueView(
                id=str(row["id"]), track_id=str(row["track_id"]),
                clip_id=str(row["clip_id"]) if row["clip_id"] else None,
                link_group_id=str(row["link_group_id"]) if row["link_group_id"] else None,
                start_tick=int(row["start_tick"]), end_tick=int(row["end_tick"]),
                text=str(row["text"]), speaker=str(row["speaker"]),
                style=json.loads(row["style_json"] or "{}"),
            )
            for row in cue_rows
        ]
        transitions = [
            TimelineTransitionView(
                id=str(row["id"]), track_id=str(row["track_id"]),
                from_clip_id=str(row["from_clip_id"]), to_clip_id=str(row["to_clip_id"]),
                transition_type=str(row["transition_type"]), duration_tick=int(row["duration_tick"]),
                params=json.loads(row["params_json"] or "{}"),
            )
            for row in transition_rows
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
            subtitle_cues=subtitle_cues,
            transitions=transitions,
        )
