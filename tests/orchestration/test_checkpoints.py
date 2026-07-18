import hashlib
import json
import sqlite3
from contextlib import contextmanager

import pytest

from backend.orchestration import checkpoints as checkpoints_module
from backend.orchestration import repository as repository_module
from backend.orchestration.checkpoints import (
    ArtifactDraft,
    input_hash,
    validate_checkpoint,
)
from backend.orchestration.database import OrchestrationDatabase
from backend.orchestration.repository import JobRepository
from backend.orchestration.schemas import JobCreate


def _request(key="checkpoint-job-0001"):
    return JobCreate(
        project_id="checkpoint-project",
        input_path="input/story.txt",
        input_type="novel",
        mode="automatic",
        idempotency_key=key,
    )


@pytest.fixture
def repository_and_job(tmp_path):
    database = OrchestrationDatabase(tmp_path / "orchestration.db")
    repository = JobRepository(database)
    job = repository.create_job(_request())
    return database, repository, job


def _insert_step(
    database,
    job_id,
    step_id,
    sequence,
    shot_id="",
    *,
    status="running",
):
    with database.transaction() as connection:
        connection.execute(
            """
            INSERT INTO job_steps(
                id, job_id, sequence, stage_key, shot_id, status,
                progress, input_hash, error_code, error_message,
                started_at, finished_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                step_id,
                job_id,
                sequence,
                "first_frame" if sequence < 10 else "compose",
                shot_id,
                status,
                0.4,
                "old-input",
                "old-error",
                "旧错误",
                "2026-01-01T00:00:00+00:00",
                None,
            ),
        )


def _row(database, sql, parameters=()):
    with database.connection() as connection:
        return connection.execute(sql, parameters).fetchone()


def test_checkpoint_detects_modified_deleted_and_input_changed_files(tmp_path):
    output = tmp_path / "shot.json"
    output.write_text("first", encoding="utf-8")
    draft = ArtifactDraft.from_path("shot", output)

    assert validate_checkpoint([draft], "abc", "abc") is True
    assert validate_checkpoint([draft], "abc", "different") is False

    output.write_text("second", encoding="utf-8")
    assert validate_checkpoint([draft], "abc", "abc") is False

    output.unlink()
    assert validate_checkpoint([draft], "abc", "abc") is False


def test_checkpoint_rejects_empty_artifacts_and_missing_draft_path(tmp_path):
    assert validate_checkpoint([], "abc", "abc") is False

    with pytest.raises(FileNotFoundError):
        ArtifactDraft.from_path("shot", tmp_path / "missing.json")


def test_checkpoint_rejects_file_that_changes_while_hashing(tmp_path, monkeypatch):
    output = tmp_path / "shot.json"
    output.write_text("content", encoding="utf-8")
    draft = ArtifactDraft.from_path("shot", output)
    original_fstat = checkpoints_module.os.fstat
    calls = 0

    def changing_fstat(file_descriptor):
        nonlocal calls
        calls += 1
        file_stat = original_fstat(file_descriptor)
        if calls == 2:
            values = list(file_stat)
            values[6] += 1
            return checkpoints_module.os.stat_result(values)
        return file_stat

    monkeypatch.setattr(checkpoints_module.os, "fstat", changing_fstat)

    assert validate_checkpoint([draft], "abc", "abc") is False


def test_input_hash_is_stable_for_key_order_and_unicode():
    first = input_hash({"镜头": "雨夜", "options": {"b": 2, "a": 1}})
    second = input_hash({"options": {"a": 1, "b": 2}, "镜头": "雨夜"})

    assert first == second
    assert first == hashlib.sha256(
        json.dumps(
            {"镜头": "雨夜", "options": {"b": 2, "a": 1}},
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()
    assert input_hash({"镜头": "晴天"}) != first


def test_artifact_draft_copies_metadata_and_preserves_unicode(tmp_path):
    output = tmp_path / "shot.json"
    output.write_text("content", encoding="utf-8")
    metadata = {"说明": "第一镜", "nested": {"take": 1}}

    draft = ArtifactDraft.from_path("shot", output, metadata)
    other = ArtifactDraft.from_path("shot", output)
    metadata["说明"] = "已修改"
    metadata["nested"]["take"] = 2

    assert draft.metadata == {"说明": "第一镜", "nested": {"take": 1}}
    fresh = ArtifactDraft.from_path("shot", output)
    assert other.metadata == fresh.metadata == {}
    assert other.metadata is not fresh.metadata


def test_artifact_draft_metadata_is_recursively_immutable_and_json_safe(tmp_path):
    output = tmp_path / "shot.json"
    output.write_text("content", encoding="utf-8")
    draft = ArtifactDraft.from_path(
        "shot", output, {"说明": "第一镜", "nested": {"takes": [1, 2]}}
    )

    with pytest.raises(TypeError):
        draft.metadata["说明"] = "changed"
    with pytest.raises(TypeError):
        draft.metadata["nested"]["takes"] = []
    with pytest.raises(TypeError):
        draft.metadata["nested"]["takes"][0] = 9

    encoded = json.dumps(draft.metadata, ensure_ascii=False)
    assert json.loads(encoded) == {
        "说明": "第一镜",
        "nested": {"takes": [1, 2]},
    }


def test_complete_step_atomically_persists_artifact_and_completion(
    repository_and_job, tmp_path
):
    database, repository, job = repository_and_job
    _insert_step(database, job["id"], "step-1", 4, "shot-1")
    output = tmp_path / "第一镜.json"
    output.write_text("render", encoding="utf-8")
    draft = ArtifactDraft.from_path("image", output, {"说明": "雨夜"})

    repository.complete_step(job["id"], "step-1", "input-abc", [draft])

    step = _row(database, "SELECT * FROM job_steps WHERE id = 'step-1'")
    artifact = _row(database, "SELECT * FROM artifacts WHERE step_id = 'step-1'")
    assert step["status"] == "completed"
    assert step["progress"] == 1
    assert step["input_hash"] == "input-abc"
    assert step["error_code"] == step["error_message"] == ""
    assert step["finished_at"]
    assert artifact["active"] == 1
    assert artifact["path"] == str(output.resolve())
    assert json.loads(artifact["metadata_json"]) == {"说明": "雨夜"}
    assert "雨夜" in artifact["metadata_json"]


@pytest.mark.parametrize("damage", ["modify", "delete"])
def test_complete_step_rejects_stale_artifact_without_partial_write(
    repository_and_job, tmp_path, damage
):
    database, repository, job = repository_and_job
    _insert_step(database, job["id"], "step-1", 4, "shot-1")
    output = tmp_path / "shot.json"
    output.write_text("original", encoding="utf-8")
    draft = ArtifactDraft.from_path("image", output)
    if damage == "modify":
        output.write_text("changed", encoding="utf-8")
    else:
        output.unlink()

    with pytest.raises(ValueError, match="artifact checkpoint"):
        repository.complete_step(job["id"], "step-1", "input-abc", [draft])

    step = _row(database, "SELECT * FROM job_steps WHERE id = 'step-1'")
    count = _row(database, "SELECT COUNT(*) AS count FROM artifacts")["count"]
    assert step["status"] == "running"
    assert count == 0


def test_complete_step_rolls_back_when_file_changes_after_validation(
    repository_and_job, tmp_path, monkeypatch
):
    database, repository, job = repository_and_job
    _insert_step(database, job["id"], "step-1", 4, "shot-1")
    output = tmp_path / "shot.json"
    output.write_bytes(b"original")
    draft = ArtifactDraft.from_path("image", output)
    original_transaction = database.transaction

    @contextmanager
    def transaction_with_late_file_change():
        with original_transaction() as connection:
            output.write_bytes(b"modified")
            yield connection

    monkeypatch.setattr(database, "transaction", transaction_with_late_file_change)

    with pytest.raises(ValueError, match="artifact checkpoint"):
        repository.complete_step(job["id"], "step-1", "input-abc", [draft])

    step = _row(database, "SELECT * FROM job_steps WHERE id = 'step-1'")
    assert step["status"] == "running"
    assert _row(database, "SELECT COUNT(*) AS count FROM artifacts")["count"] == 0


def test_complete_step_rejects_empty_inputs_unknown_steps_and_duplicates(
    repository_and_job, tmp_path
):
    database, repository, job = repository_and_job
    _insert_step(database, job["id"], "step-1", 4, "shot-1")
    output = tmp_path / "shot.json"
    output.write_text("render", encoding="utf-8")
    draft = ArtifactDraft.from_path("image", output)

    with pytest.raises(ValueError, match="artifact"):
        repository.complete_step(job["id"], "step-1", "input-abc", [])
    with pytest.raises(ValueError, match="input hash"):
        repository.complete_step(job["id"], "step-1", "", [draft])
    with pytest.raises(KeyError):
        repository.complete_step(job["id"], "missing", "input-abc", [draft])
    other_job = repository.create_job(_request("checkpoint-job-0002"))
    with pytest.raises(KeyError):
        repository.complete_step(other_job["id"], "step-1", "input-abc", [draft])
    with pytest.raises(ValueError, match="duplicate"):
        repository.complete_step(job["id"], "step-1", "input-abc", [draft, draft])

    assert _row(database, "SELECT COUNT(*) AS count FROM artifacts")["count"] == 0
    assert _row(database, "SELECT status FROM job_steps WHERE id = 'step-1'")[
        "status"
    ] == "running"


def test_complete_step_rejects_non_json_metadata_before_transaction(
    repository_and_job, tmp_path, monkeypatch
):
    database, repository, job = repository_and_job
    _insert_step(database, job["id"], "step-1", 4, "shot-1")
    output = tmp_path / "shot.json"
    output.write_text("render", encoding="utf-8")
    draft = ArtifactDraft.from_path("image", output, {"bad": object()})
    original_transaction = database.transaction
    entered = 0

    @contextmanager
    def counted_transaction():
        nonlocal entered
        entered += 1
        with original_transaction() as connection:
            yield connection

    monkeypatch.setattr(database, "transaction", counted_transaction)

    with pytest.raises(TypeError):
        repository.complete_step(job["id"], "step-1", "input-abc", [draft])

    assert entered == 0


def test_recompletion_deactivates_old_artifact_set(repository_and_job, tmp_path):
    database, repository, job = repository_and_job
    _insert_step(database, job["id"], "step-1", 4, "shot-1")
    old_path = tmp_path / "old.png"
    new_path = tmp_path / "new.png"
    old_path.write_bytes(b"old")
    new_path.write_bytes(b"new")

    repository.complete_step(
        job["id"], "step-1", "input-1", [ArtifactDraft.from_path("image", old_path)]
    )
    repository.complete_step(
        job["id"], "step-1", "input-2", [ArtifactDraft.from_path("image", new_path)]
    )

    with database.connection() as connection:
        artifacts = connection.execute(
            "SELECT path, active FROM artifacts ORDER BY path"
        ).fetchall()
    assert {row["path"]: row["active"] for row in artifacts} == {
        str(new_path.resolve()): 1,
        str(old_path.resolve()): 0,
    }


def test_recompletion_rolls_back_all_changes_when_step_update_aborts(
    repository_and_job, tmp_path
):
    database, repository, job = repository_and_job
    _insert_step(database, job["id"], "step-1", 4, "shot-1")
    old_path = tmp_path / "old.png"
    new_path = tmp_path / "new.png"
    old_path.write_bytes(b"old")
    new_path.write_bytes(b"new")
    repository.complete_step(
        job["id"],
        "step-1",
        "old-input",
        [ArtifactDraft.from_path("image", old_path)],
    )
    with database.transaction() as connection:
        connection.execute(
            """
            CREATE TRIGGER abort_step_completion
            BEFORE UPDATE OF status ON job_steps
            WHEN NEW.id = 'step-1' AND NEW.status = 'completed'
            BEGIN
                SELECT RAISE(ABORT, 'blocked completion');
            END
            """
        )

    with pytest.raises(sqlite3.IntegrityError, match="blocked completion"):
        repository.complete_step(
            job["id"],
            "step-1",
            "new-input",
            [ArtifactDraft.from_path("image", new_path)],
        )

    step = _row(database, "SELECT * FROM job_steps WHERE id='step-1'")
    with database.connection() as connection:
        artifacts = connection.execute(
            "SELECT path, active FROM artifacts ORDER BY path"
        ).fetchall()
    assert step["status"] == "completed"
    assert step["input_hash"] == "old-input"
    assert [(row["path"], row["active"]) for row in artifacts] == [
        (str(old_path.resolve()), 1)
    ]

    with database.transaction() as connection:
        connection.execute("DROP TRIGGER abort_step_completion")


def test_reconcile_bad_shot_preserves_other_shot_and_resets_job(
    repository_and_job, tmp_path
):
    database, repository, job = repository_and_job
    _insert_step(database, job["id"], "shot-1-frame", 4, "shot-1")
    _insert_step(database, job["id"], "shot-2-frame", 4, "shot-2")
    _insert_step(database, job["id"], "compose", 10, "")
    paths = {}
    for step_id in ("shot-1-frame", "shot-2-frame", "compose"):
        path = tmp_path / f"{step_id}.dat"
        path.write_text(step_id, encoding="utf-8")
        paths[step_id] = path
        repository.complete_step(
            job["id"], step_id, f"hash-{step_id}", [ArtifactDraft.from_path("file", path)]
        )
    with database.transaction() as connection:
        connection.execute(
            """
            UPDATE jobs SET status='completed', desired_state='paused',
                final_video='final.mp4', worker_id='worker', lease_until='later',
                run_after='later', finished_at='later', message='旧消息'
            WHERE id=?
            """,
            (job["id"],),
        )
    paths["shot-1-frame"].unlink()

    assert repository.reconcile_checkpoints() == 1

    with database.connection() as connection:
        steps = {
            row["id"]: dict(row)
            for row in connection.execute("SELECT * FROM job_steps WHERE job_id=?", (job["id"],))
        }
        artifacts = {
            row["step_id"]: row["active"]
            for row in connection.execute("SELECT step_id, active FROM artifacts")
        }
        restored_job = connection.execute("SELECT * FROM jobs WHERE id=?", (job["id"],)).fetchone()

    assert steps["shot-2-frame"]["status"] == "completed"
    assert artifacts["shot-2-frame"] == 1
    for step_id in ("shot-1-frame", "compose"):
        step = steps[step_id]
        assert step["status"] == "queued"
        assert step["progress"] == 0
        assert step["input_hash"] == ""
        assert step["error_code"] == step["error_message"] == ""
        assert step["started_at"] is step["finished_at"] is None
        assert artifacts[step_id] == 0
    assert restored_job["status"] == "queued"
    assert restored_job["desired_state"] == "running"
    assert restored_job["final_video"] == ""
    assert restored_job["worker_id"] is None
    assert restored_job["lease_until"] is None
    assert restored_job["run_after"] is None
    assert restored_job["finished_at"] is None
    assert restored_job["message"] == "检测到检查点损坏，已从受影响步骤恢复"


def test_reconcile_reads_artifacts_through_managed_connection(
    repository_and_job, monkeypatch
):
    database, repository, _job = repository_and_job
    original_connection = database.connection
    managed = {"entered": 0, "exited": 0}

    @contextmanager
    def counted_connection():
        managed["entered"] += 1
        try:
            with original_connection() as connection:
                yield connection
        finally:
            managed["exited"] += 1

    monkeypatch.setattr(database, "connection", counted_connection)

    assert repository.reconcile_checkpoints() == 0
    assert managed == {"entered": 1, "exited": 1}


def test_reconcile_skips_bad_artifact_repaired_after_scan(
    repository_and_job, tmp_path, monkeypatch
):
    database, repository, job = repository_and_job
    _insert_step(database, job["id"], "shot-root", 2, "shot-1")
    output = tmp_path / "shot.dat"
    output.write_bytes(b"broken00")
    repository.complete_step(
        job["id"],
        "shot-root",
        "input-hash",
        [ArtifactDraft.from_path("image", output)],
    )
    output.unlink()
    original_validate = repository_module.validate_checkpoint
    repaired = {}

    def validate_then_repair(artifacts, expected_hash, actual_hash):
        result = original_validate(artifacts, expected_hash, actual_hash)
        if not repaired:
            output.write_bytes(b"repaired")
            draft = ArtifactDraft.from_path("image", output)
            with database.transaction() as connection:
                connection.execute(
                    """
                    UPDATE artifacts
                    SET sha256=?, size=?, validated_at=?
                    WHERE job_id=? AND step_id=? AND active=1
                    """,
                    (
                        draft.sha256,
                        draft.size,
                        "2026-07-19T12:00:00+00:00",
                        job["id"],
                        "shot-root",
                    ),
                )
            repaired["sha256"] = draft.sha256
        return result

    monkeypatch.setattr(repository_module, "validate_checkpoint", validate_then_repair)

    assert repository.reconcile_checkpoints() == 0

    step = _row(database, "SELECT * FROM job_steps WHERE id='shot-root'")
    artifact = _row(database, "SELECT * FROM artifacts WHERE step_id='shot-root'")
    assert step["status"] == "completed"
    assert artifact["active"] == 1
    assert artifact["sha256"] == repaired["sha256"]


def test_reconcile_completed_step_without_active_artifact(
    repository_and_job, tmp_path
):
    database, repository, job = repository_and_job
    _insert_step(database, job["id"], "shot-root", 2, "shot-1")
    _insert_step(database, job["id"], "compose", 10, "")
    output = tmp_path / "shot.dat"
    output.write_bytes(b"rendered")
    repository.complete_step(
        job["id"],
        "shot-root",
        "input-hash",
        [ArtifactDraft.from_path("image", output)],
    )
    with database.transaction() as connection:
        connection.execute(
            "UPDATE artifacts SET active=0 WHERE step_id='shot-root'"
        )

    assert repository.reconcile_checkpoints() == 1

    root = _row(database, "SELECT * FROM job_steps WHERE id='shot-root'")
    downstream = _row(database, "SELECT * FROM job_steps WHERE id='compose'")
    assert root["status"] == downstream["status"] == "queued"


def test_reconcile_counts_invalid_steps_once_and_merges_roots_per_job(
    repository_and_job, tmp_path
):
    database, repository, job = repository_and_job
    _insert_step(database, job["id"], "shot-root", 2, "shot-1")
    _insert_step(database, job["id"], "global-root", 5, "")
    _insert_step(database, job["id"], "downstream", 8, "shot-2")
    first = tmp_path / "first.dat"
    second = tmp_path / "second.dat"
    global_path = tmp_path / "global.dat"
    downstream = tmp_path / "downstream.dat"
    for path in (first, second, global_path, downstream):
        path.write_text(path.name, encoding="utf-8")
    repository.complete_step(
        job["id"],
        "shot-root",
        "shot-hash",
        [
            ArtifactDraft.from_path("image", first),
            ArtifactDraft.from_path("metadata", second),
        ],
    )
    repository.complete_step(
        job["id"], "global-root", "global-hash", [ArtifactDraft.from_path("file", global_path)]
    )
    repository.complete_step(
        job["id"], "downstream", "down-hash", [ArtifactDraft.from_path("file", downstream)]
    )
    first.unlink()
    second.unlink()
    global_path.unlink()

    assert repository.reconcile_checkpoints() == 2

    with database.connection() as connection:
        rows = connection.execute(
            "SELECT id, status FROM job_steps WHERE job_id=?", (job["id"],)
        ).fetchall()
    assert {row["id"]: row["status"] for row in rows} == {
        "shot-root": "queued",
        "global-root": "queued",
        "downstream": "queued",
    }


def test_global_and_shot_roots_have_different_downstream_scope(
    repository_and_job, tmp_path
):
    database, repository, job = repository_and_job
    step_specs = [
        ("global", 1, ""),
        ("shot-1", 2, "shot-1"),
        ("shot-2", 2, "shot-2"),
        ("shot-1-later", 3, "shot-1"),
        ("shot-2-later", 3, "shot-2"),
        ("compose", 4, ""),
    ]
    paths = {}
    for step_id, sequence, shot_id in step_specs:
        _insert_step(database, job["id"], step_id, sequence, shot_id)
        path = tmp_path / step_id
        path.write_text(step_id, encoding="utf-8")
        paths[step_id] = path
        repository.complete_step(
            job["id"], step_id, step_id, [ArtifactDraft.from_path("file", path)]
        )

    paths["shot-1"].unlink()
    assert repository.reconcile_checkpoints() == 1
    with database.connection() as connection:
        statuses = {
            row["id"]: row["status"]
            for row in connection.execute("SELECT id, status FROM job_steps")
        }
    assert statuses == {
        "global": "completed",
        "shot-1": "queued",
        "shot-2": "completed",
        "shot-1-later": "queued",
        "shot-2-later": "completed",
        "compose": "queued",
    }

    paths["global"].unlink()
    assert repository.reconcile_checkpoints() == 1
    with database.connection() as connection:
        statuses = {
            row["id"]: row["status"]
            for row in connection.execute("SELECT id, status FROM job_steps")
        }
    assert set(statuses.values()) == {"queued"}
