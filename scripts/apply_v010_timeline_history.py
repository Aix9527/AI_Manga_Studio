from pathlib import Path

service_path = Path("backend/timeline/service.py")
text = service_path.read_text(encoding="utf-8")

if "import hashlib\n" not in text:
    text = text.replace("import json\nimport uuid\n", "import hashlib\nimport json\nimport uuid\n", 1)

if "class TimelineRedoUnavailable" not in text:
    text = text.replace(
        "class TimelineValidationError(ValueError):\n    pass\n\n\ndef _now_iso()",
        "class TimelineValidationError(ValueError):\n    pass\n\n\nclass TimelineRedoUnavailable(ValueError):\n    pass\n\n\ndef _now_iso()",
        1,
    )

old_apply = '''            before = self._capture_inverse_state(conn, str(draft["id"]))
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
'''
new_apply = '''            head_seq = int(draft["head_operation_seq"])
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
'''
if old_apply not in text:
    raise SystemExit("apply_operation anchor not found")
text = text.replace(old_apply, new_apply, 1)

history_methods = '''    def undo(self, timeline_id: str, *, expected_revision: int) -> TimelineMutationResult:
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

'''
anchor = "    def _move_clip(self, conn, timeline, draft, operation: MoveClipOperation) -> None:\n"
if anchor not in text:
    raise SystemExit("service history insertion anchor not found")
text = text.replace(anchor, history_methods + anchor, 1)

old_capture = '''        groups = [dict(row) for row in conn.execute(
            "SELECT * FROM timeline_link_groups WHERE draft_id=? ORDER BY id",
            (draft_id,),
        ).fetchall()]
        return {"type": "RESTORE_DRAFT_STATE", "clips": clips, "link_groups": groups}
'''
new_capture = '''        groups = [dict(row) for row in conn.execute(
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
'''
if old_capture not in text:
    raise SystemExit("capture state anchor not found")
text = text.replace(old_capture, new_capture, 1)
service_path.write_text(text, encoding="utf-8")

routes_path = Path("backend/timeline/routes.py")
routes = routes_path.read_text(encoding="utf-8")
if "TimelineRevisionRequest" not in routes:
    routes = routes.replace(
        "    TimelineOperationRequest,\n    TimelineSummary,\n",
        "    TimelineOperationRequest,\n    TimelineRevisionRequest,\n    TimelineSummary,\n",
        1,
    )
if "TimelineRedoUnavailable" not in routes:
    routes = routes.replace(
        "    TimelineRevisionConflict,\n    TimelineService,\n",
        "    TimelineRevisionConflict,\n    TimelineRedoUnavailable,\n    TimelineService,\n",
        1,
    )
routes += '''\n\n@router.post("/api/timelines/{timeline_id}/undo", response_model=TimelineMutationResult)
async def undo_timeline_operation(timeline_id: str, value: TimelineRevisionRequest, request: Request) -> TimelineMutationResult:
    try:
        return _service(request).undo(timeline_id, expected_revision=value.expected_revision)
    except TimelineRevisionConflict as error:
        raise HTTPException(status_code=409, detail={"code": "TIMELINE_REVISION_CONFLICT", "message": str(error)}) from error
    except TimelineNotFound as error:
        raise HTTPException(status_code=404, detail={"code": "TIMELINE_NOT_FOUND", "message": str(error)}) from error
    except TimelineValidationError as error:
        raise HTTPException(status_code=422, detail={"code": "TIMELINE_HISTORY_UNAVAILABLE", "message": str(error)}) from error


@router.post("/api/timelines/{timeline_id}/redo", response_model=TimelineMutationResult)
async def redo_timeline_operation(timeline_id: str, value: TimelineRevisionRequest, request: Request) -> TimelineMutationResult:
    try:
        return _service(request).redo(timeline_id, expected_revision=value.expected_revision)
    except TimelineRevisionConflict as error:
        raise HTTPException(status_code=409, detail={"code": "TIMELINE_REVISION_CONFLICT", "message": str(error)}) from error
    except TimelineNotFound as error:
        raise HTTPException(status_code=404, detail={"code": "TIMELINE_NOT_FOUND", "message": str(error)}) from error
    except (TimelineRedoUnavailable, TimelineValidationError) as error:
        raise HTTPException(status_code=422, detail={"code": "TIMELINE_HISTORY_UNAVAILABLE", "message": str(error)}) from error
'''
routes_path.write_text(routes, encoding="utf-8")
