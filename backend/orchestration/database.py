from __future__ import annotations

import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path


class OrchestrationDatabase:
    def __init__(self, db_path: str):
        self.db_path = db_path
        self._local = threading.local()
        self._initialize()

    def _initialize(self) -> None:
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as conn:
            conn.executescript(self._schema())
            self._migrate_job_steps(conn)
            self._migrate_artifacts(conn)
            conn.commit()

    def close(self) -> None:
        connection = getattr(self._local, "conn", None)
        if connection is not None:
            connection.close()
            self._local.conn = None

    @staticmethod
    def _migrate_job_steps(conn: sqlite3.Connection) -> None:
        columns = {row["name"] for row in conn.execute("PRAGMA table_info(job_steps)")}
        migrations = {
            "quality_attempt": "INTEGER NOT NULL DEFAULT 0",
            "ui_stage_key": "TEXT NOT NULL DEFAULT ''",
            "quality_report": "TEXT NOT NULL DEFAULT '{}'",
        }
        for name, definition in migrations.items():
            if name not in columns:
                conn.execute(f"ALTER TABLE job_steps ADD COLUMN {name} {definition}")

    @staticmethod
    def _migrate_artifacts(conn: sqlite3.Connection) -> None:
        columns = {row["name"] for row in conn.execute("PRAGMA table_info(artifacts)")}
        migrations = {
            "project_id": "TEXT NOT NULL DEFAULT ''",
            "parent_artifact_id": "INTEGER",
            "version": "INTEGER NOT NULL DEFAULT 1",
            "stage_key": "TEXT NOT NULL DEFAULT ''",
            "scene_id": "TEXT NOT NULL DEFAULT ''",
            "shot_id": "TEXT NOT NULL DEFAULT ''",
            "quality_status": "TEXT NOT NULL DEFAULT 'unreviewed'",
            "quality_attempt": "INTEGER NOT NULL DEFAULT 0",
            "quality_report": "TEXT NOT NULL DEFAULT '{}'",
        }
        for name, definition in migrations.items():
            if name not in columns:
                conn.execute(f"ALTER TABLE artifacts ADD COLUMN {name} {definition}")
        conn.execute(
            """UPDATE artifacts
               SET project_id=(SELECT jobs.project_id FROM jobs WHERE jobs.id=artifacts.job_id)
               WHERE project_id='' AND EXISTS (
                   SELECT 1 FROM jobs WHERE jobs.id=artifacts.job_id
               )"""
        )
        conn.execute(
            """CREATE INDEX IF NOT EXISTS idx_artifacts_project_listing
               ON artifacts(project_id, active DESC, version DESC, id DESC)"""
        )
        conn.execute(
            """CREATE INDEX IF NOT EXISTS idx_artifacts_lineage
               ON artifacts(project_id, kind, stage_key, scene_id, shot_id, version)"""
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_artifacts_parent ON artifacts(parent_artifact_id)"
        )

    def _schema(self) -> str:
        return """
        PRAGMA journal_mode=WAL;
        PRAGMA foreign_keys=ON;

        CREATE TABLE IF NOT EXISTS jobs (
            id TEXT PRIMARY KEY,
            project_id TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'draft',
            mode TEXT NOT NULL DEFAULT 'automatic',
            desired_state TEXT NOT NULL DEFAULT 'running',
            current_stage TEXT NOT NULL DEFAULT '',
            current_shot TEXT NOT NULL DEFAULT '',
            progress REAL NOT NULL DEFAULT 0.0,
            message TEXT NOT NULL DEFAULT '',
            final_video TEXT NOT NULL DEFAULT '',
            input_path TEXT NOT NULL DEFAULT '',
            input_type TEXT NOT NULL DEFAULT 'novel',
            settings TEXT NOT NULL DEFAULT '{}',
            idempotency_key TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at TEXT NOT NULL DEFAULT (datetime('now')),
            finished_at TEXT,
            retry_count INTEGER NOT NULL DEFAULT 0,
            lease_id TEXT,
            lease_expires_at TEXT
        );

        CREATE TABLE IF NOT EXISTS job_steps (
            id TEXT PRIMARY KEY,
            job_id TEXT NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
            sequence INTEGER NOT NULL,
            stage_key TEXT NOT NULL,
            shot_id TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'pending',
            attempt INTEGER NOT NULL DEFAULT 0,
            progress REAL NOT NULL DEFAULT 0.0,
            error_code TEXT NOT NULL DEFAULT '',
            error_message TEXT NOT NULL DEFAULT '',
            quality_attempt INTEGER NOT NULL DEFAULT 0,
            ui_stage_key TEXT NOT NULL DEFAULT '',
            quality_report TEXT NOT NULL DEFAULT '{}',
            started_at TEXT,
            finished_at TEXT,
            UNIQUE(job_id, stage_key, shot_id)
        );

        CREATE INDEX IF NOT EXISTS idx_job_steps_job_id ON job_steps(job_id);
        CREATE INDEX IF NOT EXISTS idx_job_steps_status ON job_steps(status);

        CREATE TRIGGER IF NOT EXISTS trg_pause_after_canvas_rerun
        AFTER UPDATE OF status ON job_steps
        WHEN NEW.status='completed'
          AND OLD.status <> 'completed'
          AND EXISTS (
              SELECT 1 FROM jobs
              WHERE id=NEW.job_id
                AND status='running'
                AND desired_state=('pause_after_step:' || NEW.id)
          )
        BEGIN
            UPDATE jobs
               SET status='paused',
                   desired_state=('rerun_node_complete:' || NEW.id),
                   current_stage=NEW.stage_key,
                   current_shot=NEW.shot_id,
                   message=('Single-node rerun completed at ' || NEW.stage_key || '; choose a stage execution command to continue.'),
                   lease_id=NULL,
                   lease_expires_at=NULL,
                   updated_at=datetime('now')
             WHERE id=NEW.job_id
               AND status='running'
               AND desired_state=('pause_after_step:' || NEW.id);
        END;

        CREATE TABLE IF NOT EXISTS artifacts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            job_id TEXT NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
            step_id TEXT NOT NULL REFERENCES job_steps(id) ON DELETE CASCADE,
            kind TEXT NOT NULL,
            path TEXT NOT NULL,
            sha256 TEXT NOT NULL,
            metadata TEXT NOT NULL DEFAULT '{}',
            active INTEGER NOT NULL DEFAULT 1,
            quality_attempt INTEGER NOT NULL DEFAULT 0,
            quality_report TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE INDEX IF NOT EXISTS idx_artifacts_job_id ON artifacts(job_id);
        CREATE INDEX IF NOT EXISTS idx_artifacts_active ON artifacts(active);

        CREATE TABLE IF NOT EXISTS checkpoints (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            job_id TEXT NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
            step_id TEXT NOT NULL,
            stage_key TEXT NOT NULL,
            shot_id TEXT NOT NULL DEFAULT '',
            input_hash TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'completed',
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE INDEX IF NOT EXISTS idx_checkpoints_job_id ON checkpoints(job_id);
        CREATE UNIQUE INDEX IF NOT EXISTS idx_checkpoints_unique
            ON checkpoints(job_id, stage_key, shot_id);

        CREATE TABLE IF NOT EXISTS project_workspaces (
            project_id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            source_path TEXT NOT NULL DEFAULT '',
            version INTEGER NOT NULL DEFAULT 1,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS stage_automation (
            project_id TEXT NOT NULL,
            stage_key TEXT NOT NULL,
            settings TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            PRIMARY KEY (project_id, stage_key)
        );

        CREATE TABLE IF NOT EXISTS project_production_templates (
            project_id TEXT PRIMARY KEY,
            published_version_id TEXT,
            latest_version INTEGER NOT NULL DEFAULT 0,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS project_production_template_versions (
            id TEXT PRIMARY KEY,
            project_id TEXT NOT NULL,
            version INTEGER NOT NULL,
            name TEXT NOT NULL DEFAULT '',
            schema_version INTEGER NOT NULL,
            content_json TEXT NOT NULL,
            content_sha256 TEXT NOT NULL,
            compiled_json TEXT NOT NULL,
            compiled_sha256 TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'active',
            created_at TEXT NOT NULL,
            published_at TEXT,
            UNIQUE(project_id, version)
        );

        CREATE INDEX IF NOT EXISTS idx_project_template_versions
            ON project_production_template_versions(project_id, version DESC);
        CREATE INDEX IF NOT EXISTS idx_project_template_status
            ON project_production_template_versions(project_id, status, version DESC);

        CREATE TABLE IF NOT EXISTS timelines (
            id TEXT PRIMARY KEY,
            project_id TEXT NOT NULL UNIQUE,
            name TEXT NOT NULL,
            timebase_hz INTEGER NOT NULL,
            fps_num INTEGER NOT NULL,
            fps_den INTEGER NOT NULL,
            active_draft_id TEXT,
            latest_snapshot_no INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_timelines_project ON timelines(project_id);

        CREATE TABLE IF NOT EXISTS timeline_drafts (
            id TEXT PRIMARY KEY,
            timeline_id TEXT NOT NULL REFERENCES timelines(id) ON DELETE CASCADE,
            revision INTEGER NOT NULL,
            base_snapshot_id TEXT,
            head_operation_seq INTEGER NOT NULL DEFAULT 0,
            redo_operation_seq INTEGER,
            dirty INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_timeline_drafts_timeline
            ON timeline_drafts(timeline_id, revision DESC);

        CREATE TABLE IF NOT EXISTS timeline_tracks (
            id TEXT PRIMARY KEY,
            draft_id TEXT NOT NULL REFERENCES timeline_drafts(id) ON DELETE CASCADE,
            track_type TEXT NOT NULL,
            role TEXT NOT NULL,
            name TEXT NOT NULL,
            sort_index INTEGER NOT NULL,
            locked INTEGER NOT NULL DEFAULT 0,
            muted INTEGER NOT NULL DEFAULT 0,
            hidden INTEGER NOT NULL DEFAULT 0,
            metadata_json TEXT NOT NULL DEFAULT '{}'
        );

        CREATE INDEX IF NOT EXISTS idx_timeline_tracks_draft
            ON timeline_tracks(draft_id, sort_index, id);

        CREATE TABLE IF NOT EXISTS timeline_link_groups (
            id TEXT PRIMARY KEY,
            draft_id TEXT NOT NULL REFERENCES timeline_drafts(id) ON DELETE CASCADE,
            group_type TEXT NOT NULL,
            anchor_clip_id TEXT,
            created_at TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_timeline_link_groups_draft
            ON timeline_link_groups(draft_id, id);

        CREATE TABLE IF NOT EXISTS timeline_clips (
            id TEXT PRIMARY KEY,
            draft_id TEXT NOT NULL REFERENCES timeline_drafts(id) ON DELETE CASCADE,
            track_id TEXT NOT NULL REFERENCES timeline_tracks(id) ON DELETE CASCADE,
            artifact_id INTEGER,
            artifact_version INTEGER,
            clip_type TEXT NOT NULL,
            timeline_start_tick INTEGER NOT NULL,
            duration_tick INTEGER NOT NULL,
            source_in_tick INTEGER NOT NULL DEFAULT 0,
            source_out_tick INTEGER NOT NULL,
            link_group_id TEXT REFERENCES timeline_link_groups(id) ON DELETE SET NULL,
            enabled INTEGER NOT NULL DEFAULT 1,
            locked INTEGER NOT NULL DEFAULT 0,
            gain_db REAL,
            playback_rate_num INTEGER NOT NULL DEFAULT 1,
            playback_rate_den INTEGER NOT NULL DEFAULT 1,
            metadata_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_timeline_clips_track
            ON timeline_clips(draft_id, track_id, timeline_start_tick, id);
        CREATE INDEX IF NOT EXISTS idx_timeline_clips_artifact
            ON timeline_clips(artifact_id, artifact_version);
        CREATE INDEX IF NOT EXISTS idx_timeline_clips_link_group
            ON timeline_clips(link_group_id);

        CREATE TABLE IF NOT EXISTS timeline_transitions (
            id TEXT PRIMARY KEY,
            draft_id TEXT NOT NULL REFERENCES timeline_drafts(id) ON DELETE CASCADE,
            track_id TEXT NOT NULL REFERENCES timeline_tracks(id) ON DELETE CASCADE,
            from_clip_id TEXT NOT NULL REFERENCES timeline_clips(id) ON DELETE CASCADE,
            to_clip_id TEXT NOT NULL REFERENCES timeline_clips(id) ON DELETE CASCADE,
            transition_type TEXT NOT NULL,
            duration_tick INTEGER NOT NULL,
            params_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_timeline_transitions_track
            ON timeline_transitions(draft_id, track_id, from_clip_id, to_clip_id);

        CREATE TABLE IF NOT EXISTS timeline_subtitle_cues (
            id TEXT PRIMARY KEY,
            draft_id TEXT NOT NULL REFERENCES timeline_drafts(id) ON DELETE CASCADE,
            track_id TEXT NOT NULL REFERENCES timeline_tracks(id) ON DELETE CASCADE,
            clip_id TEXT REFERENCES timeline_clips(id) ON DELETE SET NULL,
            link_group_id TEXT REFERENCES timeline_link_groups(id) ON DELETE SET NULL,
            start_tick INTEGER NOT NULL,
            end_tick INTEGER NOT NULL,
            text TEXT NOT NULL,
            speaker TEXT NOT NULL DEFAULT '',
            style_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_timeline_subtitle_cues_track
            ON timeline_subtitle_cues(draft_id, track_id, start_tick, id);

        CREATE TABLE IF NOT EXISTS timeline_operations (
            id TEXT PRIMARY KEY,
            draft_id TEXT NOT NULL REFERENCES timeline_drafts(id) ON DELETE CASCADE,
            seq INTEGER NOT NULL,
            operation_type TEXT NOT NULL,
            payload_json TEXT NOT NULL,
            inverse_json TEXT NOT NULL,
            branch_state TEXT NOT NULL DEFAULT 'active',
            actor TEXT NOT NULL DEFAULT 'user',
            created_at TEXT NOT NULL,
            UNIQUE(draft_id, seq)
        );

        CREATE INDEX IF NOT EXISTS idx_timeline_operations_history
            ON timeline_operations(draft_id, branch_state, seq);

        CREATE TABLE IF NOT EXISTS timeline_checkpoints (
            id TEXT PRIMARY KEY,
            draft_id TEXT NOT NULL REFERENCES timeline_drafts(id) ON DELETE CASCADE,
            operation_seq INTEGER NOT NULL,
            revision INTEGER NOT NULL,
            state_json TEXT NOT NULL,
            state_sha256 TEXT NOT NULL,
            created_at TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_timeline_checkpoints_draft
            ON timeline_checkpoints(draft_id, operation_seq DESC);

        CREATE TABLE IF NOT EXISTS timeline_snapshots (
            id TEXT PRIMARY KEY,
            timeline_id TEXT NOT NULL REFERENCES timelines(id) ON DELETE CASCADE,
            snapshot_no INTEGER NOT NULL,
            source_draft_revision INTEGER NOT NULL,
            state_json TEXT NOT NULL,
            state_sha256 TEXT NOT NULL,
            duration_tick INTEGER NOT NULL,
            created_at TEXT NOT NULL,
            UNIQUE(timeline_id, snapshot_no)
        );

        CREATE INDEX IF NOT EXISTS idx_timeline_snapshots_timeline
            ON timeline_snapshots(timeline_id, snapshot_no DESC);

        CREATE TABLE IF NOT EXISTS timeline_snapshot_qc_runs (
            id TEXT PRIMARY KEY,
            snapshot_id TEXT NOT NULL REFERENCES timeline_snapshots(id) ON DELETE CASCADE,
            attempt INTEGER NOT NULL,
            status TEXT NOT NULL,
            report_json TEXT NOT NULL DEFAULT '{}',
            started_at TEXT NOT NULL,
            completed_at TEXT,
            created_at TEXT NOT NULL,
            UNIQUE(snapshot_id, attempt)
        );

        CREATE INDEX IF NOT EXISTS idx_timeline_snapshot_qc_runs_latest
            ON timeline_snapshot_qc_runs(snapshot_id, attempt DESC);

        CREATE TABLE IF NOT EXISTS timeline_composition_specs (
            id TEXT PRIMARY KEY,
            snapshot_id TEXT NOT NULL REFERENCES timeline_snapshots(id) ON DELETE CASCADE,
            output_profile_json TEXT NOT NULL,
            compiler_version TEXT NOT NULL,
            spec_json TEXT NOT NULL,
            spec_sha256 TEXT NOT NULL,
            created_at TEXT NOT NULL,
            UNIQUE(snapshot_id, spec_sha256)
        );

        CREATE INDEX IF NOT EXISTS idx_timeline_composition_specs_snapshot
            ON timeline_composition_specs(snapshot_id, created_at DESC);

        CREATE TABLE IF NOT EXISTS timeline_export_bindings (
            id TEXT PRIMARY KEY,
            composition_spec_id TEXT NOT NULL REFERENCES timeline_composition_specs(id) ON DELETE CASCADE,
            job_id TEXT NOT NULL,
            artifact_id INTEGER,
            status TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_timeline_export_bindings_spec
            ON timeline_export_bindings(composition_spec_id, status, updated_at DESC);
        CREATE INDEX IF NOT EXISTS idx_timeline_export_bindings_job
            ON timeline_export_bindings(job_id);

        CREATE TRIGGER IF NOT EXISTS trg_timeline_snapshot_immutable
        BEFORE UPDATE ON timeline_snapshots
        BEGIN
            SELECT RAISE(ABORT, 'immutable timeline snapshot');
        END;

        CREATE TRIGGER IF NOT EXISTS trg_timeline_composition_spec_immutable
        BEFORE UPDATE ON timeline_composition_specs
        BEGIN
            SELECT RAISE(ABORT, 'immutable timeline composition spec');
        END;
        """

    @contextmanager
    def connect(self):
        if not hasattr(self._local, "conn") or self._local.conn is None:
            self._local.conn = sqlite3.connect(self.db_path, check_same_thread=False)
            self._local.conn.row_factory = sqlite3.Row
            self._local.conn.execute("PRAGMA journal_mode=WAL")
            self._local.conn.execute("PRAGMA foreign_keys=ON")
            self._local.conn.execute("PRAGMA busy_timeout=10000")
        try:
            yield self._local.conn
        except Exception:
            self._local.conn.rollback()
            raise

    @contextmanager
    def transaction(self, *, immediate: bool = False):
        with self.connect() as conn:
            try:
                if immediate:
                    conn.execute("BEGIN IMMEDIATE")
                yield conn
                conn.commit()
            except Exception:
                conn.rollback()
                raise
