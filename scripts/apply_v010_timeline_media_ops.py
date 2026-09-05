from pathlib import Path

service_path = Path("backend/timeline/service.py")
text = service_path.read_text(encoding="utf-8")

old_imports = '''from backend.timeline.models import (
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
)'''
new_imports = '''from backend.timeline.models import (
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
)'''
if old_imports not in text:
    raise SystemExit("models import anchor not found")
text = text.replace(old_imports, new_imports, 1)

old_dispatch = '''        elif isinstance(operation, UnlinkClipsOperation):
            self._unlink_clips(conn, draft, operation)
        else:
            raise TimelineValidationError(f"unsupported operation: {operation.type}")
'''
new_dispatch = '''        elif isinstance(operation, UnlinkClipsOperation):
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
'''
if old_dispatch not in text:
    raise SystemExit("dispatch anchor not found")
text = text.replace(old_dispatch, new_dispatch, 1)

methods = '''    def _add_transition(self, conn, timeline, draft, operation: AddTransitionOperation) -> None:
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

'''
anchor = "    def _move_clip(self, conn, timeline, draft, operation: MoveClipOperation) -> None:\n"
if anchor not in text:
    raise SystemExit("media operations insertion anchor not found")
text = text.replace(anchor, methods + anchor, 1)

old_build = '''        tracks = [
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
        )'''
new_build = '''        tracks = [
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
        )'''
if old_build not in text:
    raise SystemExit("draft build anchor not found")
text = text.replace(old_build, new_build, 1)
service_path.write_text(text, encoding="utf-8")
