import sqlite3

import pytest

from backend.orchestration.database import OrchestrationDatabase


@pytest.fixture
def db(tmp_path):
    instance = OrchestrationDatabase(str(tmp_path / "timeline.db"))
    try:
        yield instance
    finally:
        instance.close()


def test_timeline_schema_contains_all_approved_tables(db):
    expected = {
        "timelines",
        "timeline_drafts",
        "timeline_tracks",
        "timeline_clips",
        "timeline_link_groups",
        "timeline_transitions",
        "timeline_subtitle_cues",
        "timeline_operations",
        "timeline_checkpoints",
        "timeline_snapshots",
        "timeline_snapshot_qc_runs",
        "timeline_composition_specs",
        "timeline_export_bindings",
    }
    with db.connect() as conn:
        actual = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert expected <= actual


def test_snapshot_payload_cannot_be_updated(db):
    with db.transaction() as conn:
        conn.execute(
            """INSERT INTO timelines
               (id, project_id, name, timebase_hz, fps_num, fps_den, active_draft_id,
                latest_snapshot_no, created_at, updated_at)
               VALUES ('timeline-1','project-1','Main',1000000,24,1,NULL,1,'now','now')"""
        )
        conn.execute(
            """INSERT INTO timeline_snapshots
               (id, timeline_id, snapshot_no, source_draft_revision, state_json,
                state_sha256, duration_tick, created_at)
               VALUES ('snapshot-1','timeline-1',1,0,'{}','sha',1000000,'now')"""
        )

    with pytest.raises(sqlite3.IntegrityError, match="immutable timeline snapshot"):
        with db.transaction() as conn:
            conn.execute(
                "UPDATE timeline_snapshots SET state_json='{\"changed\":true}' WHERE id='snapshot-1'"
            )


def test_composition_spec_payload_cannot_be_updated(db):
    with db.transaction() as conn:
        conn.execute(
            """INSERT INTO timelines
               (id, project_id, name, timebase_hz, fps_num, fps_den, active_draft_id,
                latest_snapshot_no, created_at, updated_at)
               VALUES ('timeline-1','project-1','Main',1000000,24,1,NULL,1,'now','now')"""
        )
        conn.execute(
            """INSERT INTO timeline_snapshots
               (id, timeline_id, snapshot_no, source_draft_revision, state_json,
                state_sha256, duration_tick, created_at)
               VALUES ('snapshot-1','timeline-1',1,0,'{}','sha',1000000,'now')"""
        )
        conn.execute(
            """INSERT INTO timeline_composition_specs
               (id, snapshot_id, output_profile_json, compiler_version, spec_json,
                spec_sha256, created_at)
               VALUES ('spec-1','snapshot-1','{}','timeline-compose/v1','{}','specsha','now')"""
        )

    with pytest.raises(sqlite3.IntegrityError, match="immutable timeline composition spec"):
        with db.transaction() as conn:
            conn.execute(
                "UPDATE timeline_composition_specs SET spec_json='{\"changed\":true}' WHERE id='spec-1'"
            )
