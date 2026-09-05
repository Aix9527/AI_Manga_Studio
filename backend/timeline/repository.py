from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

from backend.orchestration.database import OrchestrationDatabase


DEFAULT_TIMEBASE_HZ = 1_000_000
DEFAULT_FPS_NUM = 24
DEFAULT_FPS_DEN = 1


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class TimelineRepository:
    def __init__(self, db: OrchestrationDatabase, projects_root: str | Path = "projects"):
        self.db = db
        self.projects_root = Path(projects_root)

    def get_project_timeline(self, project_id: str) -> dict | None:
        with self.db.connect() as conn:
            row = conn.execute(
                "SELECT * FROM timelines WHERE project_id=?",
                (project_id,),
            ).fetchone()
            return dict(row) if row else None

    def get_timeline(self, timeline_id: str) -> dict | None:
        with self.db.connect() as conn:
            row = conn.execute("SELECT * FROM timelines WHERE id=?", (timeline_id,)).fetchone()
            return dict(row) if row else None

    def get_draft(self, draft_id: str) -> dict | None:
        with self.db.connect() as conn:
            row = conn.execute("SELECT * FROM timeline_drafts WHERE id=?", (draft_id,)).fetchone()
            return dict(row) if row else None

    def get_active_draft_for_timeline(self, timeline_id: str) -> dict | None:
        with self.db.connect() as conn:
            row = conn.execute(
                """SELECT d.*
                   FROM timelines t
                   JOIN timeline_drafts d ON d.id=t.active_draft_id
                   WHERE t.id=?""",
                (timeline_id,),
            ).fetchone()
            return dict(row) if row else None

    def list_tracks(self, draft_id: str) -> list[dict]:
        with self.db.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM timeline_tracks WHERE draft_id=? ORDER BY sort_index, id",
                (draft_id,),
            ).fetchall()
            return [dict(row) for row in rows]

    def list_clips(self, draft_id: str) -> list[dict]:
        with self.db.connect() as conn:
            rows = conn.execute(
                """SELECT c.*, a.shot_id AS artifact_shot_id,
                          a.scene_id AS artifact_scene_id, a.project_id AS artifact_project_id
                   FROM timeline_clips c
                   LEFT JOIN artifacts a ON a.id=c.artifact_id
                   WHERE c.draft_id=?
                   ORDER BY c.timeline_start_tick, c.id""",
                (draft_id,),
            ).fetchall()
            return [dict(row) for row in rows]

    def initialize_project(self, project_id: str) -> tuple[dict, bool]:
        with self.db.transaction(immediate=True) as conn:
            existing = conn.execute(
                "SELECT * FROM timelines WHERE project_id=?",
                (project_id,),
            ).fetchone()
            if existing is not None:
                return dict(existing), False

            now = _now_iso()
            timeline_id = f"timeline-{uuid.uuid4().hex[:12]}"
            draft_id = f"draft-{uuid.uuid4().hex[:12]}"
            conn.execute(
                """INSERT INTO timelines
                   (id, project_id, name, timebase_hz, fps_num, fps_den,
                    active_draft_id, latest_snapshot_no, created_at, updated_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?)""",
                (
                    timeline_id,
                    project_id,
                    "Main Timeline",
                    DEFAULT_TIMEBASE_HZ,
                    DEFAULT_FPS_NUM,
                    DEFAULT_FPS_DEN,
                    draft_id,
                    0,
                    now,
                    now,
                ),
            )
            conn.execute(
                """INSERT INTO timeline_drafts
                   (id, timeline_id, revision, base_snapshot_id, head_operation_seq,
                    redo_operation_seq, dirty, created_at, updated_at)
                   VALUES (?,?,0,NULL,0,NULL,0,?,?)""",
                (draft_id, timeline_id, now, now),
            )

            track_specs = [
                ("video", "video.main", "V1 主轨", 0),
                ("audio", "audio.dialogue", "A1 对白", 1),
                ("audio", "audio.bgm", "A2 BGM / 音效", 2),
                ("subtitle", "subtitle.primary", "S1 字幕", 3),
            ]
            track_ids: dict[str, str] = {}
            for track_type, role, name, sort_index in track_specs:
                track_id = f"track-{uuid.uuid4().hex[:12]}"
                track_ids[role] = track_id
                conn.execute(
                    """INSERT INTO timeline_tracks
                       (id, draft_id, track_type, role, name, sort_index,
                        locked, muted, hidden, metadata_json)
                       VALUES (?,?,?,?,?,?,0,0,0,'{}')""",
                    (track_id, draft_id, track_type, role, name, sort_index),
                )

            artifacts = self._bootstrap_video_artifacts(conn, project_id)
            start_tick = 0
            v1_id = track_ids["video.main"]
            for artifact in artifacts:
                metadata = json.loads(artifact["metadata"] or "{}")
                duration_tick = int(metadata.get("duration_tick") or 0)
                if duration_tick <= 0:
                    duration_tick = DEFAULT_TIMEBASE_HZ
                clip_id = f"clip-{uuid.uuid4().hex[:12]}"
                conn.execute(
                    """INSERT INTO timeline_clips
                       (id, draft_id, track_id, artifact_id, artifact_version, clip_type,
                        timeline_start_tick, duration_tick, source_in_tick, source_out_tick,
                        link_group_id, enabled, locked, gain_db, playback_rate_num,
                        playback_rate_den, metadata_json, created_at, updated_at)
                       VALUES (?,?,?,?,?,'video',?,?,?,?,NULL,1,0,NULL,1,1,'{}',?,?)""",
                    (
                        clip_id,
                        draft_id,
                        v1_id,
                        artifact["id"],
                        artifact["version"],
                        start_tick,
                        duration_tick,
                        0,
                        duration_tick,
                        now,
                        now,
                    ),
                )
                start_tick += duration_tick

            row = conn.execute("SELECT * FROM timelines WHERE id=?", (timeline_id,)).fetchone()
            return dict(row), True

    def _bootstrap_video_artifacts(self, conn, project_id: str) -> list:
        rows = conn.execute(
            """SELECT * FROM artifacts
               WHERE project_id=? AND active=1
                 AND (kind LIKE '%video%' OR kind LIKE '%composition%')
               ORDER BY version DESC, id DESC""",
            (project_id,),
        ).fetchall()

        best_by_shot: dict[str, object] = {}
        unmatched: list = []
        for row in rows:
            shot_id = str(row["shot_id"] or "")
            if shot_id:
                current = best_by_shot.get(shot_id)
                if current is None or (int(row["version"]), int(row["id"])) > (
                    int(current["version"]), int(current["id"])
                ):
                    best_by_shot[shot_id] = row
            else:
                unmatched.append(row)

        ordered: list = []
        plan_path = self.projects_root / project_id / "production_plan.json"
        plan_shots: list[str] = []
        if plan_path.is_file():
            try:
                payload = json.loads(plan_path.read_text(encoding="utf-8"))
                plan_shots = [
                    str(item.get("id") or "")
                    for item in payload.get("shots", [])
                    if isinstance(item, dict) and str(item.get("id") or "")
                ]
            except (OSError, json.JSONDecodeError):
                plan_shots = []

        used: set[str] = set()
        for shot_id in plan_shots:
            row = best_by_shot.get(shot_id)
            if row is not None:
                ordered.append(row)
                used.add(shot_id)

        remaining_shots = [
            row for shot_id, row in best_by_shot.items() if shot_id not in used
        ]
        remaining_shots.sort(key=lambda row: int(row["id"]))
        unmatched.sort(key=lambda row: int(row["id"]))
        ordered.extend(remaining_shots)
        ordered.extend(unmatched)
        return ordered
