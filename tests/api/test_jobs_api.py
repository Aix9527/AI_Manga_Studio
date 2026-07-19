from __future__ import annotations

import asyncio
import hashlib
import json

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
    duplicate = create(first, valid_job_payload, project_id="ignored-by-idempotency")

    second = app_factory()
    restored = second.get("/api/jobs/current")

    assert duplicate["id"] == created["id"]
    assert restored.status_code == 200
    assert restored.json()["id"] == created["id"]
    assert restored.json()["settings"]["project_id"] == "测试项目"


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
    assert runner.calls == 2
    assert events(repository, job["id"])[-2:] == ["job.cancel", "job.cancel"]


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
    reviewed = insert_step(repository, job["id"], 1, "waiting_review", shot_id="shot-a")
    downstream = insert_step(repository, job["id"], 2, "completed", shot_id="shot-a", input_hash="old")
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
        stream = event_stream(service, job["id"], never_disconnect, poll_seconds=0)
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
            last_event_id=first["id"], poll_seconds=0,
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
            poll_seconds=0,
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
