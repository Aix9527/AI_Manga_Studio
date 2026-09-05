from __future__ import annotations

import hashlib
import json

import pytest

from backend.orchestration.config import OrchestrationConfig
from backend.orchestration.database import OrchestrationDatabase
from backend.orchestration.worker import SSEBroadcaster, StageExecutor
from backend.timeline.runtime import TimelineCompositionIntegrityError, load_verified_composition_spec


class _Repo:
    def __init__(self, db: OrchestrationDatabase):
        self.db = db


def _insert_spec(db: OrchestrationDatabase, *, spec_id: str = "spec-1") -> tuple[str, str]:
    spec_json = json.dumps(
        {
            "schema_version": 1,
            "compiler_version": "timeline-compose/v1",
            "timeline_snapshot_id": "snapshot-1",
            "project_id": "project-a",
            "tracks": [],
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    digest = hashlib.sha256(spec_json.encode("utf-8")).hexdigest()
    with db.transaction() as conn:
        conn.execute(
            """INSERT INTO timelines
               (id,project_id,name,timebase_hz,fps_num,fps_den,active_draft_id,latest_snapshot_no,created_at,updated_at)
               VALUES ('timeline-a','project-a','Timeline',1000000,24,1,NULL,1,'now','now')"""
        )
        conn.execute(
            """INSERT INTO timeline_snapshots
               (id,timeline_id,snapshot_no,source_draft_revision,state_json,state_sha256,duration_tick,created_at)
               VALUES ('snapshot-1','timeline-a',1,0,'{}','snapshot-sha',1000000,'now')"""
        )
        conn.execute(
            """INSERT INTO timeline_composition_specs
               (id,snapshot_id,output_profile_json,compiler_version,spec_json,spec_sha256,created_at)
               VALUES (?,?,?,?,?,?,?)""",
            (spec_id, "snapshot-1", '{}', "timeline-compose/v1", spec_json, digest, "now"),
        )
    return spec_json, digest


def test_runtime_loader_verifies_exact_spec_id_and_sha(tmp_path):
    db = OrchestrationDatabase(str(tmp_path / "runtime.db"))
    _spec_json, digest = _insert_spec(db)
    settings = {
        "timeline": {
            "source": "timeline_snapshot",
            "composition_spec_id": "spec-1",
            "composition_spec_sha256": digest,
        }
    }

    loaded = load_verified_composition_spec(_Repo(db), settings)

    assert loaded is not None
    assert loaded["timeline_snapshot_id"] == "snapshot-1"
    assert loaded["project_id"] == "project-a"


def test_runtime_loader_fails_closed_when_expected_sha_changes(tmp_path):
    db = OrchestrationDatabase(str(tmp_path / "runtime.db"))
    _insert_spec(db)
    settings = {
        "timeline": {
            "source": "timeline_snapshot",
            "composition_spec_id": "spec-1",
            "composition_spec_sha256": "0" * 64,
        }
    }

    with pytest.raises(TimelineCompositionIntegrityError, match="SHA"):
        load_verified_composition_spec(_Repo(db), settings)


def test_runtime_loader_returns_none_for_legacy_job(tmp_path):
    db = OrchestrationDatabase(str(tmp_path / "runtime.db"))
    assert load_verified_composition_spec(_Repo(db), {"width": 1080}) is None


@pytest.mark.asyncio
async def test_stage_executor_routes_timeline_job_away_from_legacy_composition(tmp_path, monkeypatch):
    class FakeJobRepo:
        def get_job(self, job_id: str):
            return {
                "id": job_id,
                "project_id": "project-a",
                "input_path": "",
                "settings": json.dumps(
                    {
                        "fps": 24,
                        "timeline": {
                            "source": "timeline_snapshot",
                            "composition_spec_id": "spec-1",
                            "composition_spec_sha256": "a" * 64,
                        },
                    }
                ),
            }

    executor = StageExecutor(
        FakeJobRepo(),
        SSEBroadcaster(),
        OrchestrationConfig(
            database_path=str(tmp_path / "unused.db"),
            checkpoint_dir=str(tmp_path / "checkpoints"),
            project_root=str(tmp_path / "projects"),
        ),
    )
    calls: list[str] = []

    async def timeline_compose(*args, **kwargs):
        calls.append("timeline")

    async def legacy_compose(*args, **kwargs):
        calls.append("legacy")
        raise AssertionError("timeline job must not enter legacy production-plan composition")

    monkeypatch.setattr(executor, "_run_timeline_composition", timeline_compose, raising=False)
    monkeypatch.setattr(executor, "_run_composition", legacy_compose)

    await executor._run_stage(
        "job-timeline",
        {"id": "step-compose", "stage_key": "composition_compose", "shot_id": ""},
    )

    assert calls == ["timeline"]
