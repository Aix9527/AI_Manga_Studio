from __future__ import annotations

import asyncio
import hashlib
import json
import threading
from concurrent.futures import ThreadPoolExecutor

import pytest

from backend.routes.jobs import event_stream

from conftest import events, insert_artifact, insert_step, set_job


def create(client, payload, **changes):
    body = {**payload, **changes}
    response = client.post("/api/jobs", json=body)
    assert response.status_code == 200, response.text
    return response.json()


def test_current_job_and_idempotency_survive_new_app_instance(
    app_factory, valid_job_payload
):
    first = app_factory()
    assert first.get("/api/jobs/current").json() is None
    created = create(first, valid_job_payload)

    second = app_factory()
    duplicate = create(second, valid_job_payload)
    restored = second.get("/api/jobs/current")

    assert duplicate["id"] == created["id"]
    assert restored.status_code == 200
    assert restored.json()["id"] == created["id"]
    assert restored.json()["settings"]["project_id"] == "测试项目"


@pytest.mark.parametrize(
    "changes",
    [
        {"project_id": "不同项目"},
        {"input_path": "input/other.txt"},
        {"input_type": "script"},
        {"mode": "manual_review"},
        {"shot_duration": 8},
        {"width": 1280},
        {"height": 1280},
        {"fps": 30},
        {"options": {"language": "en"}},
    ],
)
def test_create_idempotency_key_conflicts_on_any_semantic_payload_change(
    app_factory, valid_job_payload, changes
):
    first = app_factory()
    created = create(first, valid_job_payload)
    repository = first.app.state.job_service.repository
    before_job = repository.get_job(created["id"])
    before_events = repository.list_events(created["id"])

    second = app_factory()
    response = second.post(
        "/api/jobs", json={**valid_job_payload, **changes}
    )

    assert response.status_code == 409
    assert repository.get_job(created["id"]) == before_job
    assert repository.list_events(created["id"]) == before_events
    assert repository.list_jobs() == [
        {key: value for key, value in created.items() if key not in {"settings", "steps"}}
    ]


def test_concurrent_creates_with_same_key_and_different_payload_have_one_winner(
    app_factory, valid_job_payload
):
    first = app_factory()
    second = app_factory()
    barrier = threading.Barrier(2)

    def submit(client, project_id):
        barrier.wait(timeout=5)
        return client.post(
            "/api/jobs",
            json={**valid_job_payload, "project_id": project_id},
        )

    with ThreadPoolExecutor(max_workers=2) as executor:
        responses = [
            future.result(timeout=10)
            for future in (
                executor.submit(submit, first, "并发项目甲"),
                executor.submit(submit, second, "并发项目乙"),
            )
        ]

    assert sorted(response.status_code for response in responses) == [200, 409]
    repository = first.app.state.job_service.repository
    jobs = repository.list_jobs()
    assert len(jobs) == 1
    assert events(repository, jobs[0]["id"]) == ["job.created"]


def test_get_list_and_query_validation(client, valid_job_payload):
    created = create(client, valid_job_payload)

    assert client.get("/api/jobs/missing").status_code == 404
    listed = client.get("/api/jobs", params={"limit": 1, "offset": 0})
    assert listed.status_code == 200
    assert [item["id"] for item in listed.json()["items"]] == [created["id"]]
    for params in ({"limit": 0}, {"limit": 201}, {"offset": -1}):
        assert client.get("/api/jobs", params=params).status_code == 422


@pytest.mark.parametrize(
    "changes",
    [
        {"shot_duration": 4.99},
        {"shot_duration": 15.01},
        {"project_id": "../unsafe"},
        {"width": 1079},
    ],
)
def test_create_reuses_job_create_validation(client, valid_job_payload, changes):
    assert client.post(
        "/api/jobs", json={**valid_job_payload, **changes}
    ).status_code == 422


def test_retry_resets_only_failed_step_checkpoint_and_audits(
    client, valid_job_payload
):
    job = create(client, valid_job_payload)
    repository = client.app.state.job_service.repository
    completed = insert_step(
        repository,
        job["id"],
        0,
        "completed",
        progress=1,
        input_hash="kept",
        finished_at="2026-07-19T00:00:00+00:00",
    )
    failed = insert_step(
        repository,
        job["id"],
        1,
        "failed",
        progress=.7,
        input_hash="stale",
        error_code="BROKEN",
        error_message="失败",
        started_at="2026-07-19T00:00:00+00:00",
        finished_at="2026-07-19T00:01:00+00:00",
    )
    artifact = insert_artifact(repository, job["id"], failed)
    set_job(
        repository,
        job["id"],
        status="failed",
        desired_state="paused",
        worker_id="old",
        lease_until="2099-01-01T00:00:00+00:00",
        run_after="2099-01-01T00:00:00+00:00",
    )

    response = client.post(f"/api/jobs/{job['id']}/retry", json={"step_id": failed})

    assert response.status_code == 200
    restored = response.json()
    by_id = {step["id"]: step for step in restored["steps"]}
    assert by_id[completed]["status"] == "completed"
    assert by_id[completed]["input_hash"] == "kept"
    assert by_id[failed] | {
        "status": "queued",
        "progress": 0,
        "input_hash": "",
        "error_code": "",
        "error_message": "",
        "started_at": None,
        "finished_at": None,
    } == by_id[failed]
    assert restored["status"] == "queued"
    assert restored["desired_state"] == "running"
    assert restored["worker_id"] is restored["lease_until"] is None
    with repository.database.connection() as connection:
        assert connection.execute(
            "SELECT active FROM artifacts WHERE id=?", (artifact,)
        ).fetchone()["active"] == 0
    assert events(repository, job["id"])[-1] == "job.retry"

    assert client.post(
        f"/api/jobs/{job['id']}/retry", json={"step_id": completed}
    ).status_code == 409
    assert client.post(
        "/api/jobs/missing/retry", json={"step_id": failed}
    ).status_code == 404


def test_retry_rejects_failed_step_while_job_is_worker_owned(
    client, valid_job_payload
):
    job = create(client, valid_job_payload)
    repository = client.app.state.job_service.repository
    failed = insert_step(repository, job["id"], 0, "failed", error_code="E")
    set_job(
        repository,
        job["id"],
        status="running",
        worker_id="live-owner",
        lease_until="2099-01-01T00:00:00+00:00",
    )
    before_events = events(repository, job["id"])

    response = client.post(
        f"/api/jobs/{job['id']}/retry", json={"step_id": failed}
    )

    assert response.status_code == 409
    restored = repository.get_job(job["id"])
    assert restored["status"] == "running"
    assert restored["worker_id"] == "live-owner"
    assert restored["steps"][0]["status"] == "failed"
    assert events(repository, job["id"]) == before_events


@pytest.mark.parametrize("job_status", ["paused", "retry_wait"])
def test_retry_rejects_failed_step_unless_job_itself_failed_without_writes(
    client, valid_job_payload, job_status
):
    job = create(client, valid_job_payload)
    repository = client.app.state.job_service.repository
    failed = insert_step(
        repository,
        job["id"],
        0,
        "failed",
        progress=.5,
        input_hash="keep",
        error_code="E",
        error_message="keep",
        started_at="start",
        finished_at="finish",
    )
    insert_artifact(repository, job["id"], failed)
    set_job(repository, job["id"], status=job_status, desired_state="paused")
    before_job = repository.get_job(job["id"])
    with repository.database.connection() as connection:
        before_artifacts = [
            dict(row)
            for row in connection.execute(
                "SELECT * FROM artifacts WHERE job_id=? ORDER BY id", (job["id"],)
            )
        ]
        before_event_count = connection.execute(
            "SELECT count(*) AS n FROM job_events WHERE job_id=?", (job["id"],)
        ).fetchone()["n"]

    response = client.post(
        f"/api/jobs/{job['id']}/retry", json={"step_id": failed}
    )

    assert response.status_code == 409
    assert repository.get_job(job["id"]) == before_job
    with repository.database.connection() as connection:
        assert [
            dict(row)
            for row in connection.execute(
                "SELECT * FROM artifacts WHERE job_id=? ORDER BY id", (job["id"],)
            )
        ] == before_artifacts
        assert connection.execute(
            "SELECT count(*) AS n FROM job_events WHERE job_id=?", (job["id"],)
        ).fetchone()["n"] == before_event_count


def test_pause_and_resume_follow_desired_state_semantics(client, valid_job_payload):
    job = create(client, valid_job_payload)
    repository = client.app.state.job_service.repository
    set_job(
        repository,
        job["id"],
        status="running",
        desired_state="running",
        worker_id="owner",
        lease_until="2099-01-01T00:00:00+00:00",
    )

    paused_running = client.post(f"/api/jobs/{job['id']}/pause")
    assert paused_running.status_code == 200
    assert paused_running.json()["status"] == "running"
    assert paused_running.json()["desired_state"] == "paused"
    resumed_running = client.post(f"/api/jobs/{job['id']}/resume")
    assert resumed_running.json()["status"] == "running"
    assert resumed_running.json()["desired_state"] == "running"

    set_job(
        repository,
        job["id"],
        status="retry_wait",
        run_after="2099-01-01T00:00:00+00:00",
        worker_id="stale",
        lease_until="2099-01-01T00:00:00+00:00",
    )
    paused = client.post(f"/api/jobs/{job['id']}/pause").json()
    assert paused["status"] == paused["desired_state"] == "paused"
    assert paused["run_after"] is paused["worker_id"] is paused["lease_until"] is None
    resumed = client.post(f"/api/jobs/{job['id']}/resume").json()
    assert resumed["status"] == "queued"
    assert resumed["desired_state"] == "running"
    assert events(repository, job["id"])[-4:] == [
        "job.pause", "job.resume", "job.pause", "job.resume"
    ]

    set_job(repository, job["id"], status="completed", desired_state="running")
    assert client.post(f"/api/jobs/{job['id']}/resume").status_code == 409


def test_cancel_is_durable_idempotent_and_runner_failure_is_best_effort(
    app_factory, valid_job_payload
):
    class ExplodingRunner:
        calls = 0

        def cancel(self, _job_id):
            self.calls += 1
            raise RuntimeError("backend unavailable")

    runner = ExplodingRunner()
    client = app_factory(runner)
    job = create(client, valid_job_payload)
    repository = client.app.state.job_service.repository
    completed = insert_step(repository, job["id"], 0, "completed", progress=1)
    unfinished = insert_step(repository, job["id"], 1, "running")
    set_job(
        repository,
        job["id"],
        status="running",
        worker_id="owner",
        lease_until="2099-01-01T00:00:00+00:00",
        run_after="2099-01-01T00:00:00+00:00",
    )

    first = client.post(f"/api/jobs/{job['id']}/cancel")
    second = client.post(f"/api/jobs/{job['id']}/cancel")

    assert first.status_code == second.status_code == 200
    restored = second.json()
    steps = {step["id"]: step for step in restored["steps"]}
    assert restored["status"] == restored["desired_state"] == "cancelled"
    assert restored["finished_at"] is not None
    assert restored["run_after"] is restored["worker_id"] is restored["lease_until"] is None
    assert steps[completed]["status"] == "completed"
    assert steps[unfinished]["status"] == "cancelled"
    assert steps[unfinished]["finished_at"] is not None
    assert runner.calls == 1
    assert events(repository, job["id"]).count("job.cancel") == 1


def test_rollback_scope_exact_confirmation_and_atomic_reset(client, valid_job_payload):
    job = create(client, valid_job_payload)
    repository = client.app.state.job_service.repository
    root = insert_step(repository, job["id"], 1, "completed", shot_id="shot-a")
    other = insert_step(repository, job["id"], 2, "completed", shot_id="shot-b")
    same = insert_step(
        repository, job["id"], 2, "failed", shot_id="shot-a",
        progress=.4, input_hash="stale", error_code="E", started_at="x", finished_at="y"
    )
    global_step = insert_step(repository, job["id"], 3, "completed", shot_id="")
    artifacts = [insert_artifact(repository, job["id"], step) for step in (root, same, global_step)]
    set_job(repository, job["id"], status="failed", final_video="old.mp4")

    preview = client.get(
        f"/api/jobs/{job['id']}/rollback-preview", params={"step_id": root}
    )
    expected = [root, same, global_step]
    assert preview.status_code == 200
    assert preview.json()["invalidated_step_ids"] == expected

    before_events = events(repository, job["id"])
    duplicate = client.post(
        f"/api/jobs/{job['id']}/rollback",
        json={"step_id": root, "confirm_invalidated_step_ids": [root, same, same]},
    )
    assert duplicate.status_code == 409
    assert repository.get_job(job["id"])["steps"][0]["status"] == "completed"
    assert events(repository, job["id"]) == before_events

    concurrent = insert_step(repository, job["id"], 4, "completed", shot_id="shot-a")
    stale = client.post(
        f"/api/jobs/{job['id']}/rollback",
        json={"step_id": root, "confirm_invalidated_step_ids": expected},
    )
    assert stale.status_code == 409
    assert next(step for step in repository.get_job(job["id"])["steps"] if step["id"] == concurrent)["status"] == "completed"

    exact = [root, same, global_step, concurrent]
    restored = client.post(
        f"/api/jobs/{job['id']}/rollback",
        json={"step_id": root, "confirm_invalidated_step_ids": exact},
    )
    assert restored.status_code == 200
    by_id = {step["id"]: step for step in restored.json()["steps"]}
    assert by_id[other]["status"] == "completed"
    for step_id in exact:
        assert by_id[step_id]["status"] == "queued"
        assert by_id[step_id]["progress"] == 0
        assert by_id[step_id]["input_hash"] == ""
        assert by_id[step_id]["started_at"] is by_id[step_id]["finished_at"] is None
    assert restored.json()["status"] == "queued"
    assert restored.json()["desired_state"] == "running"
    assert restored.json()["final_video"] == ""
    with repository.database.connection() as connection:
        assert all(
            connection.execute("SELECT active FROM artifacts WHERE id=?", (item,)).fetchone()["active"] == 0
            for item in artifacts
        )
    assert events(repository, job["id"])[-1] == "job.rollback"

    after_success = repository.get_job(job["id"])
    after_events = events(repository, job["id"])
    repeated = client.post(
        f"/api/jobs/{job['id']}/rollback",
        json={"step_id": root, "confirm_invalidated_step_ids": exact},
    )
    assert repeated.status_code == 409
    assert repository.get_job(job["id"]) == after_success
    assert events(repository, job["id"]) == after_events


def test_global_rollback_root_includes_every_downstream_step(client, valid_job_payload):
    job = create(client, valid_job_payload)
    repository = client.app.state.job_service.repository
    ids = [
        insert_step(repository, job["id"], 0, "completed", shot_id=""),
        insert_step(repository, job["id"], 1, "completed", shot_id="shot-a"),
        insert_step(repository, job["id"], 1, "completed", shot_id="shot-b"),
        insert_step(repository, job["id"], 2, "failed", shot_id=""),
    ]
    preview = client.get(
        f"/api/jobs/{job['id']}/rollback-preview", params={"step_id": ids[0]}
    )
    assert preview.json()["invalidated_step_ids"] == ids


def test_manual_review_approve_edit_retry_and_failures_are_transactional(
    client, valid_job_payload
):
    job = create(client, valid_job_payload, mode="manual_review")
    repository = client.app.state.job_service.repository
    reviewed = insert_step(repository, job["id"], 1, "completed", shot_id="shot-a")
    downstream = insert_step(
        repository, job["id"], 2, "queued", shot_id="shot-a", input_hash="old"
    )
    set_job(repository, job["id"], status="waiting_review")

    approved = client.post(
        f"/api/jobs/{job['id']}/steps/{reviewed}/review",
        json={"action": "approve", "comment": "通过", "patch": {}},
    )
    assert approved.status_code == 200
    assert approved.json()["status"] == "queued"

    set_job(repository, job["id"], status="waiting_review")
    edited = client.post(
        f"/api/jobs/{job['id']}/steps/{reviewed}/review",
        json={
            "action": "edit",
            "comment": "调整",
            "patch": {"shot_duration": 8, "options": {"style": "水墨"}},
        },
    )
    assert edited.status_code == 200
    assert edited.json()["settings"]["shot_duration"] == 8
    assert edited.json()["settings"]["options"] == {"language": "zh-CN", "style": "水墨"}

    set_job(repository, job["id"], status="waiting_review")
    with repository.database.transaction() as connection:
        connection.execute(
            "UPDATE job_steps SET status='completed' WHERE id=?", (reviewed,)
        )
    before = repository.get_job(job["id"])["settings"]
    with repository.database.connection() as connection:
        action_count = connection.execute("SELECT count(*) AS n FROM review_actions").fetchone()["n"]
    invalid = client.post(
        f"/api/jobs/{job['id']}/steps/{reviewed}/review",
        json={"action": "edit", "patch": {"project_id": "hijack", "width": 1079}},
    )
    assert invalid.status_code == 409
    assert repository.get_job(job["id"])["settings"] == before
    with repository.database.connection() as connection:
        assert connection.execute("SELECT count(*) AS n FROM review_actions").fetchone()["n"] == action_count

    set_job(repository, job["id"], status="waiting_review")
    with repository.database.transaction() as connection:
        connection.execute(
            "UPDATE job_steps SET status='completed' WHERE id IN (?, ?)",
            (reviewed, downstream),
        )
    retried = client.post(
        f"/api/jobs/{job['id']}/steps/{reviewed}/review",
        json={"action": "retry", "comment": "重做"},
    )
    assert retried.status_code == 200
    statuses = {step["id"]: step["status"] for step in retried.json()["steps"]}
    assert statuses[reviewed] == statuses[downstream] == "queued"

    other = create(client, valid_job_payload, idempotency_key="other-job-0001")
    other_step = insert_step(repository, other["id"], 0, "waiting_review")
    set_job(repository, job["id"], status="waiting_review")
    assert client.post(
        f"/api/jobs/{job['id']}/steps/{other_step}/review",
        json={"action": "approve"},
    ).status_code == 409
    assert client.post(
        f"/api/jobs/{job['id']}/steps/{reviewed}/review",
        json={"action": "rollback"},
    ).status_code == 409
    assert events(repository, job["id"])[-3:] == [
        "job.review.approve", "job.review.edit", "job.review.retry"
    ]


@pytest.mark.parametrize("step_status", ["queued", "failed"])
def test_review_rejects_non_reviewable_step_without_writes(
    client, valid_job_payload, step_status
):
    job = create(client, valid_job_payload, mode="manual_review")
    repository = client.app.state.job_service.repository
    step = insert_step(
        repository,
        job["id"],
        0,
        step_status,
        input_hash="keep",
        error_code="keep",
    )
    insert_artifact(repository, job["id"], step)
    set_job(repository, job["id"], status="waiting_review")
    before_job = repository.get_job(job["id"])
    with repository.database.connection() as connection:
        before_artifacts = [
            dict(row)
            for row in connection.execute(
                "SELECT * FROM artifacts WHERE job_id=? ORDER BY id", (job["id"],)
            )
        ]
        before_reviews = [
            dict(row)
            for row in connection.execute(
                "SELECT * FROM review_actions WHERE job_id=? ORDER BY id", (job["id"],)
            )
        ]
        before_events = [
            dict(row)
            for row in connection.execute(
                "SELECT * FROM job_events WHERE job_id=? ORDER BY id", (job["id"],)
            )
        ]

    response = client.post(
        f"/api/jobs/{job['id']}/steps/{step}/review",
        json={"action": "edit", "patch": {"shot_duration": 8}},
    )

    assert response.status_code == 409
    assert repository.get_job(job["id"]) == before_job
    with repository.database.connection() as connection:
        assert [
            dict(row)
            for row in connection.execute(
                "SELECT * FROM artifacts WHERE job_id=? ORDER BY id", (job["id"],)
            )
        ] == before_artifacts
        assert [
            dict(row)
            for row in connection.execute(
                "SELECT * FROM review_actions WHERE job_id=? ORDER BY id", (job["id"],)
            )
        ] == before_reviews
        assert [
            dict(row)
            for row in connection.execute(
                "SELECT * FROM job_events WHERE job_id=? ORDER BY id", (job["id"],)
            )
        ] == before_events


def _parse_sse(frame):
    result = {}
    for line in frame.strip().splitlines():
        if ": " in line:
            key, value = line.split(": ", 1)
            result[key] = value
    return result


def test_sse_snapshot_uses_stable_hash_and_last_event_id(client, valid_job_payload):
    job = create(client, valid_job_payload)
    service = client.app.state.job_service

    async def scenario():
        never_disconnect = lambda: asyncio.sleep(0, result=False)
        stream = event_stream(service, job["id"], never_disconnect, poll_seconds=.001)
        first = _parse_sse(await anext(stream))
        await stream.aclose()
        canonical = json.dumps(
            service.get(job["id"]), ensure_ascii=False, sort_keys=True,
            separators=(",", ":"),
        )
        assert first["event"] == "job"
        assert json.loads(first["data"])["project_id"] == "测试项目"
        assert first["id"] == hashlib.sha256(canonical.encode("utf-8")).hexdigest()

        reconnected = event_stream(
            service, job["id"], never_disconnect,
            last_event_id=first["id"], poll_seconds=.001,
        )
        assert (await anext(reconnected)).startswith(": keepalive")
        service.pause(job["id"])
        changed = _parse_sse(await anext(reconnected))
        assert changed["event"] == "job"
        assert changed["id"] != first["id"]
        await reconnected.aclose()

    asyncio.run(scenario())


def test_sse_gone_ends_and_route_sets_streaming_headers(client):
    async def scenario():
        stream = event_stream(
            client.app.state.job_service,
            "missing",
            lambda: asyncio.sleep(0, result=False),
            poll_seconds=.001,
        )
        frame = await anext(stream)
        assert _parse_sse(frame)["event"] == "gone"
        with pytest.raises(StopAsyncIteration):
            await anext(stream)

    asyncio.run(scenario())
    response = client.get("/api/jobs/missing/events")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert response.headers["cache-control"] == "no-cache"
    assert response.headers["x-accel-buffering"] == "no"


def test_job_detail_and_current_include_active_artifacts_in_one_query(
    client, valid_job_payload, monkeypatch
):
    job = create(client, valid_job_payload)
    repository = client.app.state.job_service.repository
    with_artifacts = insert_step(repository, job["id"], 0, "completed")
    without_artifacts = insert_step(repository, job["id"], 1, "queued")
    active_ids = [
        insert_artifact(repository, job["id"], with_artifacts),
        insert_artifact(repository, job["id"], with_artifacts),
    ]
    inactive_id = insert_artifact(repository, job["id"], with_artifacts)
    with repository.database.transaction() as connection:
        connection.execute(
            "UPDATE artifacts SET metadata_json=? WHERE id=?",
            ('{"角色":"小雨","frame":1}', active_ids[0]),
        )
        connection.execute(
            "UPDATE artifacts SET active=0, metadata_json=? WHERE id=?",
            ('{"historical":true}', inactive_id),
        )

    queries = []
    original_connect = repository.database.connect

    def traced_connect():
        connection = original_connect()
        connection.set_trace_callback(queries.append)
        return connection

    monkeypatch.setattr(repository.database, "connect", traced_connect)
    detail = client.get(f"/api/jobs/{job['id']}")

    assert detail.status_code == 200
    by_id = {step["id"]: step for step in detail.json()["steps"]}
    artifacts = by_id[with_artifacts]["artifacts"]
    assert len(artifacts) == 2
    assert [item["path"] for item in artifacts] == sorted(
        item["path"] for item in artifacts
    )
    assert any(item["metadata"] == {"角色": "小雨", "frame": 1} for item in artifacts)
    assert by_id[without_artifacts]["artifacts"] == []
    assert all(item["metadata"] != {"historical": True} for item in artifacts)
    artifact_queries = [
        query for query in queries if "FROM artifacts" in query
    ]
    assert len(artifact_queries) == 1

    queries.clear()
    current = client.get("/api/jobs/current")
    assert current.status_code == 200
    current_by_id = {step["id"]: step for step in current.json()["steps"]}
    assert current_by_id[with_artifacts]["artifacts"] == artifacts
    assert len([query for query in queries if "FROM artifacts" in query]) == 1


def test_artifact_activation_changes_sse_snapshot_and_stable_event_id(
    client, valid_job_payload
):
    job = create(client, valid_job_payload)
    service = client.app.state.job_service
    repository = service.repository
    step = insert_step(repository, job["id"], 0, "queued")

    async def scenario():
        stream = event_stream(
            service,
            job["id"],
            lambda: asyncio.sleep(0, result=False),
            poll_seconds=.001,
        )
        initial = _parse_sse(await anext(stream))
        assert json.loads(initial["data"])["steps"][0]["artifacts"] == []

        artifact_id = insert_artifact(repository, job["id"], step)
        active = _parse_sse(await anext(stream))
        assert active["id"] != initial["id"]
        assert len(json.loads(active["data"])["steps"][0]["artifacts"]) == 1

        with repository.database.transaction() as connection:
            connection.execute(
                "UPDATE artifacts SET active=0 WHERE id=?", (artifact_id,)
            )
        inactive = _parse_sse(await anext(stream))
        assert inactive["id"] != active["id"]
        assert json.loads(inactive["data"])["steps"][0]["artifacts"] == []
        await stream.aclose()

    asyncio.run(scenario())


def _command_fixture(client, valid_job_payload, action):
    job = create(client, valid_job_payload)
    repository = client.app.state.job_service.repository
    if action == "pause":
        return job, f"/api/jobs/{job['id']}/pause", None, "job.pause"
    if action == "resume":
        set_job(repository, job["id"], status="paused", desired_state="paused")
        return job, f"/api/jobs/{job['id']}/resume", None, "job.resume"
    if action == "retry":
        step = insert_step(repository, job["id"], 0, "failed")
        set_job(repository, job["id"], status="failed")
        return (
            job,
            f"/api/jobs/{job['id']}/retry",
            {"step_id": step},
            "job.retry",
        )
    if action == "rollback":
        root = insert_step(repository, job["id"], 0, "completed")
        downstream = insert_step(repository, job["id"], 1, "failed")
        set_job(repository, job["id"], status="failed")
        return (
            job,
            f"/api/jobs/{job['id']}/rollback",
            {
                "step_id": root,
                "confirm_invalidated_step_ids": [root, downstream],
            },
            "job.rollback",
        )
    if action == "review":
        step = insert_step(repository, job["id"], 0, "completed")
        insert_step(repository, job["id"], 1, "queued")
        set_job(repository, job["id"], status="waiting_review")
        return (
            job,
            f"/api/jobs/{job['id']}/steps/{step}/review",
            {"action": "approve", "comment": "持久去重"},
            "job.review.approve",
        )
    if action == "cancel":
        insert_step(repository, job["id"], 0, "running")
        set_job(repository, job["id"], status="running")
        return job, f"/api/jobs/{job['id']}/cancel", None, "job.cancel"
    raise AssertionError(action)


@pytest.mark.parametrize(
    "action", ["pause", "resume", "retry", "rollback", "review", "cancel"]
)
def test_command_idempotency_survives_new_client_and_runs_side_effect_once(
    app_factory, valid_job_payload, action
):
    class CountingRunner:
        calls = 0

        def cancel(self, _job_id):
            self.calls += 1
            return True

    runner = CountingRunner()
    first_client = app_factory(runner)
    job, url, body, event_type = _command_fixture(
        first_client, valid_job_payload, action
    )
    headers = {"Idempotency-Key": f"durable-{action}-command-0001"}

    first = first_client.post(url, json=body, headers=headers)
    assert first.status_code == 200, first.text
    first_snapshot = first.json()

    second_client = app_factory(runner)
    second = second_client.post(url, json=body, headers=headers)

    assert second.status_code == 200, second.text
    assert second.json() == first_snapshot
    repository = second_client.app.state.job_service.repository
    assert events(repository, job["id"]).count(event_type) == 1
    with repository.database.connection() as connection:
        assert connection.execute(
            "SELECT count(*) AS n FROM job_commands WHERE idempotency_key=?",
            (headers["Idempotency-Key"],),
        ).fetchone()["n"] == 1
        review_count = connection.execute(
            "SELECT count(*) AS n FROM review_actions WHERE job_id=?",
            (job["id"],),
        ).fetchone()["n"]
    assert review_count == (1 if action == "review" else 0)
    assert runner.calls == (1 if action == "cancel" else 0)


def test_idempotency_key_reuse_with_different_action_or_payload_conflicts(
    client, valid_job_payload
):
    job = create(client, valid_job_payload)
    repository = client.app.state.job_service.repository
    key = "conflicting-command-key-0001"
    assert client.post(
        f"/api/jobs/{job['id']}/pause", headers={"Idempotency-Key": key}
    ).status_code == 200
    before_resume = repository.get_job(job["id"])
    assert client.post(
        f"/api/jobs/{job['id']}/resume", headers={"Idempotency-Key": key}
    ).status_code == 409
    assert repository.get_job(job["id"]) == before_resume

    other_key = "conflicting-payload-key-0001"
    first_step = insert_step(repository, job["id"], 0, "failed")
    second_step = insert_step(repository, job["id"], 1, "failed")
    set_job(repository, job["id"], status="failed")
    assert client.post(
        f"/api/jobs/{job['id']}/retry",
        json={"step_id": first_step},
        headers={"Idempotency-Key": other_key},
    ).status_code == 200
    set_job(repository, job["id"], status="failed")
    before_retry = repository.get_job(job["id"])
    before_events = events(repository, job["id"])
    assert client.post(
        f"/api/jobs/{job['id']}/retry",
        json={"step_id": second_step},
        headers={"Idempotency-Key": other_key},
    ).status_code == 409
    assert repository.get_job(job["id"]) == before_retry
    assert events(repository, job["id"]) == before_events


def test_concurrent_cancel_with_same_key_runs_durable_and_runner_side_effect_once(
    app_factory, valid_job_payload
):
    class CountingRunner:
        def __init__(self):
            self.calls = 0
            self.lock = threading.Lock()

        def cancel(self, _job_id):
            with self.lock:
                self.calls += 1
            return True

    runner = CountingRunner()
    first = app_factory(runner)
    job = create(first, valid_job_payload)
    repository = first.app.state.job_service.repository
    insert_step(repository, job["id"], 0, "running")
    set_job(repository, job["id"], status="running")
    second = app_factory(runner)
    barrier = threading.Barrier(2)
    key = "concurrent-cancel-command-0001"

    def cancel(client):
        barrier.wait(timeout=5)
        return client.post(
            f"/api/jobs/{job['id']}/cancel",
            headers={"Idempotency-Key": key},
        )

    with ThreadPoolExecutor(max_workers=2) as executor:
        responses = [
            future.result(timeout=10)
            for future in (
                executor.submit(cancel, first),
                executor.submit(cancel, second),
            )
        ]

    assert [response.status_code for response in responses] == [200, 200]
    assert runner.calls == 1
    assert events(repository, job["id"]).count("job.cancel") == 1


def test_repeated_pause_without_key_is_noop_after_target_is_reached(
    client, valid_job_payload
):
    job = create(client, valid_job_payload)
    repository = client.app.state.job_service.repository
    first = client.post(f"/api/jobs/{job['id']}/pause")
    second = client.post(f"/api/jobs/{job['id']}/pause")

    assert first.status_code == second.status_code == 200
    assert second.json() == first.json()
    assert events(repository, job["id"]).count("job.pause") == 1


def test_pause_waiting_review_is_conflict_without_any_write(
    client, valid_job_payload
):
    job = create(client, valid_job_payload, mode="manual_review")
    repository = client.app.state.job_service.repository
    step = insert_step(repository, job["id"], 0, "completed")
    insert_artifact(repository, job["id"], step)
    set_job(repository, job["id"], status="waiting_review")
    before_job = repository.get_job(job["id"])
    with repository.database.connection() as connection:
        before_tables = {
            table: [dict(row) for row in connection.execute(
                f"SELECT * FROM {table} WHERE job_id=? ORDER BY id", (job["id"],)
            )]
            for table in ("artifacts", "review_actions", "job_events")
        }

    response = client.post(f"/api/jobs/{job['id']}/pause")

    assert response.status_code == 409
    assert repository.get_job(job["id"]) == before_job
    with repository.database.connection() as connection:
        assert {
            table: [dict(row) for row in connection.execute(
                f"SELECT * FROM {table} WHERE job_id=? ORDER BY id", (job["id"],)
            )]
            for table in before_tables
        } == before_tables


def test_approve_waiting_review_step_completes_it_and_exposes_next_step(
    client, valid_job_payload
):
    job = create(client, valid_job_payload, mode="manual_review")
    repository = client.app.state.job_service.repository
    reviewed = insert_step(repository, job["id"], 0, "waiting_review", progress=.8)
    next_step = insert_step(
        repository, job["id"], 1, "pending", stage_key="next-stage", shot_id="shot-2"
    )
    set_job(repository, job["id"], status="waiting_review")

    response = client.post(
        f"/api/jobs/{job['id']}/steps/{reviewed}/review",
        json={"action": "approve"},
    )

    assert response.status_code == 200
    restored = response.json()
    by_id = {step["id"]: step for step in restored["steps"]}
    assert by_id[reviewed]["status"] == "completed"
    assert by_id[reviewed]["progress"] == 1
    assert restored["status"] == "queued"
    assert restored["current_stage"] == "next-stage"
    assert restored["current_shot"] == "shot-2"
    assert repository.current_step_id(job["id"]) == next_step


def test_approve_last_waiting_review_step_finishes_job_consistently(
    client, valid_job_payload
):
    job = create(client, valid_job_payload, mode="manual_review")
    repository = client.app.state.job_service.repository
    reviewed = insert_step(repository, job["id"], 0, "waiting_review", progress=.6)
    set_job(
        repository,
        job["id"],
        status="waiting_review",
        final_video="output/final.mp4",
    )

    response = client.post(
        f"/api/jobs/{job['id']}/steps/{reviewed}/review",
        json={"action": "approve"},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "completed"
    assert response.json()["progress"] == 1
    assert response.json()["final_video"] == "output/final.mp4"
    assert response.json()["finished_at"] is not None
    with pytest.raises(LookupError, match="no active step"):
        repository.current_step_id(job["id"])


@pytest.mark.parametrize("command", ["retry", "rollback", "review-edit", "review-retry"])
def test_reset_commands_recompute_stale_job_execution_summary(
    client, valid_job_payload, command
):
    job = create(
        client,
        valid_job_payload,
        mode="manual_review" if command.startswith("review") else "automatic",
    )
    repository = client.app.state.job_service.repository
    insert_step(repository, job["id"], 0, "completed", progress=1, stage_key="done")
    target_status = "failed" if command == "retry" else "completed"
    target = insert_step(
        repository,
        job["id"],
        1,
        target_status,
        progress=.8,
        stage_key="restart-here",
        shot_id="shot-a",
    )
    if command == "retry":
        set_job(repository, job["id"], status="failed")
        url = f"/api/jobs/{job['id']}/retry"
        body = {"step_id": target}
        expected_progress = .5
    else:
        downstream = insert_step(
            repository,
            job["id"],
            2,
            "completed",
            progress=1,
            stage_key="later",
            shot_id="shot-a",
        )
        if command == "rollback":
            set_job(repository, job["id"], status="failed")
            url = f"/api/jobs/{job['id']}/rollback"
            body = {
                "step_id": target,
                "confirm_invalidated_step_ids": [target, downstream],
            }
        else:
            set_job(repository, job["id"], status="waiting_review")
            action = command.removeprefix("review-")
            url = f"/api/jobs/{job['id']}/steps/{target}/review"
            body = {
                "action": action,
                "patch": {"shot_duration": 8} if action == "edit" else {},
            }
        expected_progress = pytest.approx(1 / 3)
    set_job(
        repository,
        job["id"],
        progress=.95,
        current_stage="final_compose",
        current_shot="shot-99",
    )

    response = client.post(url, json=body)

    assert response.status_code == 200, response.text
    assert response.json()["progress"] == expected_progress
    assert response.json()["current_stage"] == "restart-here"
    assert response.json()["current_shot"] == "shot-a"


@pytest.mark.parametrize("number", ["NaN", "Infinity", "-Infinity"])
def test_review_patch_rejects_non_finite_json_with_422_and_no_write(
    app_factory, valid_job_payload, number
):
    client = app_factory(raise_server_exceptions=False)
    job = create(client, valid_job_payload, mode="manual_review")
    repository = client.app.state.job_service.repository
    step = insert_step(repository, job["id"], 0, "completed")
    set_job(repository, job["id"], status="waiting_review")
    before = repository.get_job(job["id"])
    before_events = events(repository, job["id"])

    response = client.post(
        f"/api/jobs/{job['id']}/steps/{step}/review",
        content=(
            '{"action":"edit","patch":{"options":{"nested":['
            + number
            + "]}}}"
        ),
        headers={"Content-Type": "application/json"},
    )

    assert response.status_code == 422
    assert repository.get_job(job["id"]) == before
    assert events(repository, job["id"]) == before_events
    with repository.database.connection() as connection:
        assert connection.execute(
            "SELECT count(*) AS n FROM review_actions WHERE job_id=?", (job["id"],)
        ).fetchone()["n"] == 0


@pytest.mark.parametrize("number", ["NaN", "Infinity", "-Infinity"])
def test_job_options_reject_non_finite_json_with_422(client, valid_job_payload, number):
    body = json.dumps(valid_job_payload, ensure_ascii=False)
    body = body.replace('{"language": "zh-CN"}', '{"score": ' + number + "}")

    response = client.post(
        "/api/jobs", content=body, headers={"Content-Type": "application/json"}
    )

    assert response.status_code == 422
    assert client.get("/api/jobs").json()["items"] == []


@pytest.mark.parametrize("number", ["NaN", "Infinity", "-Infinity"])
def test_job_numeric_fields_reject_non_finite_json_with_422(
    app_factory, valid_job_payload, number
):
    client = app_factory(raise_server_exceptions=False)
    body = json.dumps(valid_job_payload, ensure_ascii=False)
    body = body.replace('"shot_duration": 5', '"shot_duration": ' + number)

    response = client.post(
        "/api/jobs", content=body, headers={"Content-Type": "application/json"}
    )

    assert response.status_code == 422
    assert client.get("/api/jobs").json()["items"] == []


@pytest.mark.parametrize("poll_seconds", [0, -0.1, float("nan")])
def test_event_stream_rejects_non_positive_or_non_finite_poll_interval(
    client, poll_seconds
):
    with pytest.raises(ValueError, match="poll_seconds"):
        event_stream(
            client.app.state.job_service,
            "missing",
            lambda: asyncio.sleep(0, result=False),
            poll_seconds=poll_seconds,
        )
