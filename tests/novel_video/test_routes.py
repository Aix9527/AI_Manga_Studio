from __future__ import annotations

import asyncio
import os
import hmac
import secrets
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.novel_video.repository import NovelVideoRepository
from backend.novel_video.routes import NovelVideoIngressLimitMiddleware, router
from backend.novel_video.schemas import ProjectCreateRequest
from backend.novel_video.service import NovelVideoService
from backend.novel_video.storage import AtomicAssetStore
from backend.orchestration.database import OrchestrationDatabase


def _project_payload(**overrides):
    payload = {
        "id": "novel-route-project",
        "name": "Route novel",
        "width": 864,
        "height": 480,
        "target_duration_seconds": 15,
        "max_shots": 3,
    }
    payload.update(overrides)
    return payload


@pytest.fixture
def client(tmp_path: Path):
    app = FastAPI()
    app.add_middleware(NovelVideoIngressLimitMiddleware)
    app.include_router(router, prefix="/api/core/novel-video")
    app.state.novel_video_capabilities = {"test-capability": "alice", "other-capability": "bob"}
    app.state.novel_video_sessions = {}
    app.state.novel_video_proxy_assertion_bypass = True
    app.state.novel_video_allowed_origins = {"http://localhost:5173"}
    app.state.novel_video_service = NovelVideoService(
        repo=NovelVideoRepository(OrchestrationDatabase(str(tmp_path / "novel.db"))),
        asset_store=AtomicAssetStore(),
        projects_root=tmp_path / "projects",
    )
    with TestClient(app, headers={
        "X-Novel-Video-Capability": "test-capability", "Origin": "http://localhost:5173",
    }) as test_client:
        handshake = test_client.post("/api/core/novel-video/session")
        assert handshake.status_code == 204
        test_client.headers.pop("X-Novel-Video-Capability", None)
        yield test_client


def _upload(client: TestClient, project_id: str, content: bytes) -> dict:
    response = client.post(
        f"/api/core/novel-video/projects/{project_id}/source",
        files={"file": ("greed-wolf.txt", content, "text/plain")},
    )
    assert response.status_code == 201, response.text
    assert "copied_path" not in response.json()
    return response.json()


def _create_run(client: TestClient, project_id: str, plan_id: str, *, key: str = "route-run-key"):
    return client.post(
        f"/api/core/novel-video/projects/{project_id}/runs",
        json={"plan_id": plan_id}, headers={"Idempotency-Key": key},
    )


def _proxy_headers(
    secret: str,
    method: str,
    target: str,
    *,
    session: str = "-",
    timestamp: str | None = None,
    nonce: str | None = None,
) -> dict[str, str]:
    timestamp = timestamp or str(int(datetime.now(timezone.utc).timestamp()))
    nonce = nonce or secrets.token_urlsafe(24)
    message = "\n".join((timestamp, nonce, method, target, session))
    return {
        "X-Novel-Proxy-Timestamp": timestamp,
        "X-Novel-Proxy-Nonce": nonce,
        "X-Novel-Proxy-Assertion": hmac.new(secret.encode(), message.encode(), "sha256").hexdigest(),
    }


def _assertion_app(tmp_path: Path):
    from backend.novel_video.routes import ProxyNonceCache

    app = FastAPI()
    app.include_router(router, prefix="/api/core/novel-video")
    app.state.novel_video_capabilities = {"cap": "desktop"}
    app.state.novel_video_sessions = {}
    app.state.novel_video_proxy_secret = "test-proxy-secret"
    app.state.novel_video_proxy_nonces = ProxyNonceCache(max_entries=64)
    app.state.novel_video_allowed_origins = {"http://localhost:5173"}
    app.state.novel_video_service = NovelVideoService(
        repo=NovelVideoRepository(OrchestrationDatabase(str(tmp_path / "assertion.db"))),
        projects_root=tmp_path / "assertion-projects",
    )
    return app


def test_create_upload_analyze_and_create_run_with_immutable_plan_id(client):
    project = client.post("/api/core/novel-video/projects", json=_project_payload())
    assert project.status_code == 201, project.text
    assert project.json()["id"] == "novel-route-project"
    assert client.get("/api/core/novel-video/projects/novel-route-project").status_code == 200

    uploaded = _upload(
        client,
        "novel-route-project",
        "第一章 沙漠\n银色人形机器人在夕阳中发现一株绿色植物。".encode("gb18030"),
    )
    assert uploaded["encoding"] == "gb18030"
    analysis = client.post(
        "/api/core/novel-video/projects/novel-route-project/analyze",
        json={"chapter_indexes": [1], "target_seconds": 15, "max_shots": 3},
    )
    assert analysis.status_code == 200, analysis.text
    plan_id = analysis.json()["plan_id"]
    assert plan_id.startswith("plan-")

    missing_plan = client.post(
        "/api/core/novel-video/projects/novel-route-project/runs",
        json={"chapter_indexes": [1]}, headers={"Idempotency-Key": "invalid-plan-key"},
    )
    assert missing_plan.status_code == 422
    run = _create_run(client, "novel-route-project", plan_id)
    assert run.status_code == 201, run.text
    assert run.json()["status"] == "draft"
    assert client.get(f"/api/core/novel-video/runs/{run.json()['id']}").status_code == 200


@pytest.mark.parametrize(
    ("filename", "content", "expected"),
    [
        ("../source.txt", b"valid novel", 400),
        ("source.exe", b"valid novel", 400),
        ("source.txt", b"\x00\x00\x00binary", 422),
    ],
)
def test_source_upload_rejects_unsafe_filename_and_content(client, filename, content, expected):
    assert client.post("/api/core/novel-video/projects", json=_project_payload()).status_code == 201
    response = client.post(
        "/api/core/novel-video/projects/novel-route-project/source",
        files={"file": (filename, content, "text/plain")},
    )
    assert response.status_code == expected


def test_source_upload_rejects_oversize(client, monkeypatch):
    from backend.novel_video import routes

    monkeypatch.setattr(routes, "MAX_SOURCE_BYTES", 8)
    assert client.post("/api/core/novel-video/projects", json=_project_payload()).status_code == 201
    response = client.post(
        "/api/core/novel-video/projects/novel-route-project/source",
        files={"file": ("source.txt", b"this is over the limit", "text/plain")},
    )
    assert response.status_code == 413


def test_cloud_request_without_project_authorization_is_403(client):
    assert client.post("/api/core/novel-video/projects", json=_project_payload()).status_code == 201
    response = client.post(
        "/api/core/novel-video/projects/novel-route-project/analyze",
        json={"chapter_indexes": [1], "provider": "cloud"},
    )
    assert response.status_code == 403


def test_project_preflight_reports_local_blockers_without_startup_probe(client, monkeypatch):
    from backend.novel_video import routes

    async def fake_preflight(**kwargs):
        assert kwargs["provider"] == "minimax_h3_ref2va"
        return SimpleNamespace(ok=False, missing=["video_vae"], checks=[], resolved={})

    monkeypatch.setattr(routes, "run_preflight", fake_preflight)
    assert client.post("/api/core/novel-video/projects", json=_project_payload()).status_code == 201
    response = client.post("/api/core/novel-video/projects/novel-route-project/preflight")
    assert response.status_code == 200
    assert response.json()["ready"] is False
    assert response.json()["blockers"] == ["video_vae"]


def test_routes_reject_extra_command_fields(client):
    assert client.post("/api/core/novel-video/projects", json=_project_payload(extra="nope")).status_code == 422


def test_local_capability_origin_and_project_owner_are_enforced(client):
    bare = TestClient(client.app, headers={"Origin": "http://localhost:5173"})
    missing = bare.post("/api/core/novel-video/projects", json=_project_payload(), headers={"X-Novel-Video-Capability": ""})
    assert missing.status_code == 403
    wrong = bare.post("/api/core/novel-video/projects", json=_project_payload(), headers={"X-Novel-Video-Capability": "wrong"})
    assert wrong.status_code == 403
    hostile = bare.post("/api/core/novel-video/projects", json=_project_payload(), headers={"Origin": "https://evil.invalid", "X-Novel-Video-Capability": "test-capability"})
    assert hostile.status_code == 403
    assert client.post("/api/core/novel-video/projects", json=_project_payload()).status_code == 201
    other_client = TestClient(client.app, headers={"Origin": "http://localhost:5173"})
    assert other_client.post(
        "/api/core/novel-video/session", headers={"X-Novel-Video-Capability": "other-capability"}
    ).status_code == 204
    other = other_client.get(
        "/api/core/novel-video/projects/novel-route-project",
    )
    assert other.status_code == 403


def test_browser_session_is_created_only_through_capability_proxy_and_then_authorizes(client):
    # A renderer-like client without the Vite proxy capability has neither a
    # token nor an HttpOnly session and cannot call formal endpoints.
    bare = TestClient(client.app, headers={"Origin": "http://localhost:5173"})
    assert bare.post("/api/core/novel-video/projects", json=_project_payload()).status_code == 403
    handshake = bare.post(
        "/api/core/novel-video/session",
        headers={"X-Novel-Video-Capability": "test-capability"},
    )
    assert handshake.status_code == 204
    assert "test-capability" not in handshake.text
    assert "test-capability" not in str(handshake.headers).lower()
    created = bare.post("/api/core/novel-video/projects", json=_project_payload())
    assert created.status_code == 201


def test_capability_cannot_authorize_non_session_routes_and_session_rotates_expires(client):
    app = FastAPI()
    app.include_router(router, prefix="/api/core/novel-video")
    app.state.novel_video_capabilities = {"cap": "desktop"}
    app.state.novel_video_sessions = {}
    app.state.novel_video_proxy_secret = "test-proxy-secret"
    from backend.novel_video.routes import ProxyNonceCache
    app.state.novel_video_proxy_nonces = ProxyNonceCache()
    app.state.novel_video_allowed_origins = {"http://localhost:5173"}
    app.state.novel_video_service = NovelVideoService(
        repo=NovelVideoRepository(OrchestrationDatabase(":memory:")), projects_root=Path.cwd() / "unused-projects"
    )
    with TestClient(app, headers={"Origin": "http://localhost:5173"}) as browser:
        assert browser.post(
            "/api/core/novel-video/projects", json=_project_payload(),
            headers={"X-Novel-Video-Capability": "cap", **_proxy_headers("test-proxy-secret", "POST", "/api/core/novel-video/projects")},
        ).status_code == 403
        first = browser.post("/api/core/novel-video/session", headers={"X-Novel-Video-Capability": "cap", **_proxy_headers("test-proxy-secret", "POST", "/api/core/novel-video/session")})
        assert first.status_code == 204
        first_cookie = browser.cookies.get("novel_video_session")
        second = browser.post("/api/core/novel-video/session", headers={"X-Novel-Video-Capability": "cap", **_proxy_headers("test-proxy-secret", "POST", "/api/core/novel-video/session", session=first_cookie)})
        assert second.status_code == 204
        second_cookie = browser.cookies.get("novel_video_session")
        assert first_cookie != second_cookie
        assert first_cookie not in app.state.novel_video_sessions
        app.state.novel_video_sessions[second_cookie]["expires_at"] = datetime.now(timezone.utc)
        assert browser.post("/api/core/novel-video/projects", json=_project_payload()).status_code == 403


def test_proxy_assertion_binds_cookie_method_path_and_nonce(tmp_path):
    app = FastAPI()
    app.include_router(router, prefix="/api/core/novel-video")
    secret = "test-proxy-secret"
    app.state.novel_video_capabilities = {"cap": "desktop"}
    app.state.novel_video_sessions = {}
    app.state.novel_video_proxy_secret = secret
    from backend.novel_video.routes import ProxyNonceCache
    app.state.novel_video_proxy_nonces = ProxyNonceCache()
    app.state.novel_video_allowed_origins = {"http://localhost:5173"}
    app.state.novel_video_service = NovelVideoService(
        repo=NovelVideoRepository(OrchestrationDatabase(str(tmp_path / "assertion.db"))), projects_root=tmp_path / "assertion-projects"
    )
    origin = {"Origin": "http://localhost:5173"}
    with TestClient(app, headers=origin) as proxy:
        handshake_headers = {"X-Novel-Video-Capability": "cap", **_proxy_headers(secret, "POST", "/api/core/novel-video/session")}
        assert proxy.post("/api/core/novel-video/session", headers=handshake_headers).status_code == 204
        cookie = proxy.cookies.get("novel_video_session")
        signed = _proxy_headers(secret, "POST", "/api/core/novel-video/projects", session=cookie)
        assert proxy.post("/api/core/novel-video/projects", json=_project_payload(), headers=signed).status_code == 201
        # The same cookie, directly pointed at the backend without an HMAC,
        # cannot pass the server-only proxy boundary.
        direct = TestClient(app, headers=origin)
        direct.cookies.set("novel_video_session", cookie, path="/api/core/novel-video")
        assert direct.get("/api/core/novel-video/projects/novel-route-project").status_code == 403
        assert proxy.post("/api/core/novel-video/projects", json=_project_payload(id="second"), headers=signed).status_code == 403
        mismatched = _proxy_headers(secret, "GET", "/api/core/novel-video/projects/novel-route-project", session=cookie)
        assert proxy.post("/api/core/novel-video/projects", json=_project_payload(id="third"), headers=mismatched).status_code == 403


def test_signed_safe_request_without_origin_is_authorized_but_unsafe_is_not(tmp_path):
    app = _assertion_app(tmp_path)
    service = app.state.novel_video_service
    service.create_project(ProjectCreateRequest(**_project_payload()), principal="desktop")
    session = "safe-no-origin-session"
    app.state.novel_video_sessions[session] = {
        "principal": "desktop",
        "expires_at": datetime.now(timezone.utc) + timedelta(minutes=5),
    }
    with TestClient(app) as caller:
        caller.cookies.set("novel_video_session", session, path="/api/core/novel-video")
        target = "/api/core/novel-video/projects/novel-route-project"
        safe = caller.get(
            target,
            headers=_proxy_headers(app.state.novel_video_proxy_secret, "GET", target, session=session),
        )
        unsafe_target = "/api/core/novel-video/projects"
        unsafe = caller.post(
            unsafe_target,
            json=_project_payload(id="unsafe-no-origin"),
            headers=_proxy_headers(app.state.novel_video_proxy_secret, "POST", unsafe_target, session=session),
        )
        direct = caller.get(target)

    assert safe.status_code == 200
    assert unsafe.status_code == 403
    assert direct.status_code == 403


def test_proxy_nonce_replay_is_atomic_across_real_sync_endpoint(tmp_path):
    app = _assertion_app(tmp_path)
    service = app.state.novel_video_service
    service.create_project(ProjectCreateRequest(**_project_payload()), principal="desktop")
    session = "shared-session"
    app.state.novel_video_sessions[session] = {
        "principal": "desktop",
        "expires_at": datetime.now(timezone.utc) + timedelta(minutes=5),
    }
    target = "/api/core/novel-video/projects/novel-route-project"
    headers = _proxy_headers(
        app.state.novel_video_proxy_secret,
        "GET",
        target,
        session=session,
        nonce="concurrent-replay-nonce-0123456789",
    )

    def request_once() -> int:
        with TestClient(app, headers={"Origin": "http://localhost:5173"}) as caller:
            caller.cookies.set("novel_video_session", session, path="/api/core/novel-video")
            return caller.get(target, headers=headers).status_code

    with ThreadPoolExecutor(max_workers=12) as pool:
        statuses = list(pool.map(lambda _: request_once(), range(12)))

    assert statuses.count(200) == 1
    assert statuses.count(403) == 11


def test_proxy_nonce_cache_is_bounded_and_never_evicts_live_entries():
    from backend.novel_video.routes import ProxyNonceCache

    cache = ProxyNonceCache(max_entries=3, ttl_seconds=30)
    assert cache.consume("nonce-a", now=100.0) == "accepted"
    assert cache.consume("nonce-b", now=100.0) == "accepted"
    assert cache.consume("nonce-c", now=100.0) == "accepted"
    assert cache.consume("nonce-d", now=100.0) == "full"
    assert cache.consume("nonce-a", now=100.0) == "replayed"
    for index in range(10_000):
        assert cache.consume(f"high-cardinality-{index}", now=100.0) == "full"
    assert len(cache) == 3
    assert cache.consume("nonce-d", now=131.0) == "accepted"
    assert len(cache) == 1


def test_proxy_nonce_capacity_fails_closed_and_old_timestamp_stays_expired(tmp_path):
    from backend.novel_video.routes import ProxyNonceCache

    app = _assertion_app(tmp_path)
    service = app.state.novel_video_service
    service.create_project(ProjectCreateRequest(**_project_payload()), principal="desktop")
    session = "bounded-session"
    app.state.novel_video_sessions[session] = {
        "principal": "desktop",
        "expires_at": datetime.now(timezone.utc) + timedelta(minutes=5),
    }
    app.state.novel_video_proxy_nonces = ProxyNonceCache(max_entries=1)
    target = "/api/core/novel-video/projects/novel-route-project"
    with TestClient(app, headers={"Origin": "http://localhost:5173"}) as caller:
        caller.cookies.set("novel_video_session", session, path="/api/core/novel-video")
        first = caller.get(target, headers=_proxy_headers("test-proxy-secret", "GET", target, session=session))
        full = caller.get(target, headers=_proxy_headers("test-proxy-secret", "GET", target, session=session))
        old_timestamp = str(int(datetime.now(timezone.utc).timestamp()) - 31)
        expired = caller.get(
            target,
            headers=_proxy_headers(
                "test-proxy-secret", "GET", target, session=session,
                timestamp=old_timestamp, nonce="expired-old-nonce-0123456789",
            ),
        )
    assert first.status_code == 200
    assert full.status_code == 429
    assert expired.status_code == 403
    assert len(app.state.novel_video_proxy_nonces) == 1


@pytest.mark.parametrize(
    "timestamp",
    ["9" * 5000, "+1786612000", " 1786612000", "1786612000 ", "-1786612000"],
)
def test_proxy_timestamp_rejects_noncanonical_or_unbounded_values_without_500(tmp_path, timestamp):
    app = _assertion_app(tmp_path)
    headers = _proxy_headers(
        app.state.novel_video_proxy_secret,
        "POST",
        "/api/core/novel-video/session",
        timestamp=timestamp,
    )
    with TestClient(app, headers={"Origin": "http://localhost:5173"}) as caller:
        response = caller.post(
            "/api/core/novel-video/session",
            headers={"X-Novel-Video-Capability": "cap", **headers},
        )
    assert response.status_code == 403


def test_session_rejects_query_and_events_bind_exact_raw_query_target(client):
    assert client.post("/api/core/novel-video/projects", json=_project_payload()).status_code == 201
    _upload(client, "novel-route-project", "第一章\n故事内容足够用于测试。".encode())
    plan = client.post(
        "/api/core/novel-video/projects/novel-route-project/analyze",
        json={"chapter_indexes": [1], "target_seconds": 15, "max_shots": 3},
    ).json()
    run = _create_run(client, "novel-route-project", plan["plan_id"], key="query-binding-run").json()
    app = client.app
    app.state.novel_video_proxy_assertion_bypass = False
    from backend.novel_video.routes import ProxyNonceCache
    app.state.novel_video_proxy_secret = "query-binding-secret"
    app.state.novel_video_proxy_nonces = ProxyNonceCache(max_entries=64)
    session = client.cookies.get("novel_video_session")

    session_target = "/api/core/novel-video/session?unexpected=1"
    rejected_session = client.post(
        session_target,
        headers={
            "X-Novel-Video-Capability": "test-capability",
            **_proxy_headers("query-binding-secret", "POST", session_target, session=session),
        },
    )
    assert rejected_session.status_code == 403

    base = f"/api/core/novel-video/runs/{run['id']}/events"
    exact_target = f"{base}?after=0&limit=1"
    exact = client.get(
        exact_target,
        headers=_proxy_headers("query-binding-secret", "GET", exact_target, session=session),
    )
    assert exact.status_code == 200

    signed_target = f"{base}?after=0&after=1&limit=1"
    duplicated = client.get(
        signed_target,
        headers=_proxy_headers("query-binding-secret", "GET", signed_target, session=session),
    )
    assert duplicated.status_code == 200

    mutated = client.get(
        f"{base}?after=1&limit=1",
        headers=_proxy_headers("query-binding-secret", "GET", exact_target, session=session),
    )
    assert mutated.status_code == 403


@pytest.mark.parametrize(
    ("requested", "signed"),
    [
        ("/api/core/novel-video/session/", "/api/core/novel-video/session"),
        ("/api/core/novel-video/%73ession", "/api/core/novel-video/session"),
        ("/api/core/novel-video/%2573ession", "/api/core/novel-video/session"),
        ("/api/core/novel-video/projects/%E8%B4%AA%E7%8B%BC", "/api/core/novel-video/projects/贪狼"),
    ],
)
def test_proxy_target_rejects_encoding_and_trailing_slash_mismatch(tmp_path, requested, signed):
    app = _assertion_app(tmp_path)
    headers = {
        "X-Novel-Video-Capability": "cap",
        **_proxy_headers("test-proxy-secret", "POST", signed),
    }
    with TestClient(app, headers={"Origin": "http://localhost:5173"}, follow_redirects=False) as caller:
        response = caller.post(requested, headers=headers)
    assert response.status_code == 403


def test_create_run_idempotency_replays_exactly_and_rejects_mismatch(client):
    assert client.post("/api/core/novel-video/projects", json=_project_payload()).status_code == 201
    _upload(client, "novel-route-project", "第一章\n故事内容足够用于测试。".encode())
    plan = client.post(
        "/api/core/novel-video/projects/novel-route-project/analyze",
        json={"chapter_indexes": [1], "target_seconds": 15, "max_shots": 3},
    ).json()
    first = _create_run(client, "novel-route-project", plan["plan_id"], key="same-request")
    replay = _create_run(client, "novel-route-project", plan["plan_id"], key="same-request")
    assert first.status_code == 201
    assert replay.status_code == 200
    assert replay.json()["id"] == first.json()["id"]
    service = client.app.state.novel_video_service
    assert len(service.repo.list_runs()) == 1
    changed = client.post(
        "/api/core/novel-video/projects/novel-route-project/runs",
        json={"plan_id": plan["plan_id"], "mode": "professional"},
        headers={"Idempotency-Key": "same-request"},
    )
    assert changed.status_code == 409


def test_domain_errors_are_opaque_and_do_not_leak_local_paths(client):
    response = client.get("/api/core/novel-video/projects/missing-project")
    assert response.status_code == 404
    rendered = response.text.lower()
    assert "projects" not in rendered
    assert "tmp" not in rendered


def test_raw_ingress_limit_rejects_chunked_body_before_downstream_handler():
    from backend.novel_video.routes import NovelVideoIngressLimitMiddleware

    called = []
    sent = []
    chunks = iter([
        {"type": "http.request", "body": b"12345", "more_body": True},
        {"type": "http.request", "body": b"67890", "more_body": False},
    ])

    async def downstream(scope, receive, send):
        called.append(True)
        await receive()
        await receive()

    async def receive():
        return next(chunks)

    async def send(message):
        sent.append(message)

    asyncio.run(NovelVideoIngressLimitMiddleware(downstream, limit_bytes=8)(
        {"type": "http", "path": "/api/core/novel-video/projects/x/source", "headers": []}, receive, send
    ))
    # A generic downstream ASGI app is entered to obtain its receive callable,
    # but receives no over-limit chunk and therefore cannot invoke a route.
    assert called == [True]
    assert sent[0]["status"] == 413


def test_ingress_cap_prevents_fastapi_upload_handler_for_oversize_chunked_body(tmp_path):
    app = FastAPI()
    app.add_middleware(NovelVideoIngressLimitMiddleware, limit_bytes=8)
    app.include_router(router, prefix="/api/core/novel-video")
    service = NovelVideoService(
        repo=NovelVideoRepository(OrchestrationDatabase(str(tmp_path / "novel.db"))),
        asset_store=AtomicAssetStore(), projects_root=tmp_path / "projects",
    )
    app.state.novel_video_service = service
    app.state.novel_video_capabilities = {"cap": "alice"}
    app.state.novel_video_sessions = {}
    app.state.novel_video_proxy_assertion_bypass = True
    app.state.novel_video_allowed_origins = set()
    service.create_project(ProjectCreateRequest(**_project_payload()), principal="alice")
    calls = []
    original = service.import_source
    service.import_source = lambda *args, **kwargs: calls.append(True) or original(*args, **kwargs)
    with TestClient(app, headers={"X-Novel-Video-Capability": "cap"}) as test_client:
        response = test_client.post(
            "/api/core/novel-video/projects/novel-route-project/source",
            files={"file": ("source.txt", b"more than eight bytes", "text/plain")},
        )
    assert response.status_code == 413
    assert calls == []
    assert not list((tmp_path / "projects").rglob(".upload-*"))


def test_upload_staging_rejects_reparse_or_symlink_source_directory(client, monkeypatch):
    from backend.novel_video import service as service_module

    assert client.post("/api/core/novel-video/projects", json=_project_payload()).status_code == 201
    project = client.app.state.novel_video_service.get_project("novel-route-project")
    (project.root / "source").mkdir(parents=True, exist_ok=True)
    original = service_module._is_reparse_point
    monkeypatch.setattr(
        service_module,
        "_is_reparse_point",
        lambda path: path.name == "source" or original(path),
    )
    response = client.post(
        "/api/core/novel-video/projects/novel-route-project/source",
        files={"file": ("source.txt", b"safe words", "text/plain")},
    )
    assert response.status_code == 422


def test_create_upload_staging_file_rechecks_after_exclusive_open(client, monkeypatch):
    from backend.novel_video import service as service_module

    assert client.post("/api/core/novel-video/projects", json=_project_payload()).status_code == 201
    service = client.app.state.novel_video_service
    original_open = service_module.os.open
    switched = {"value": False}

    def swapping_open(*args, **kwargs):
        descriptor = original_open(*args, **kwargs)
        switched["value"] = True
        return descriptor

    original_reparse = service_module._is_reparse_point
    monkeypatch.setattr(service_module.os, "open", swapping_open)
    monkeypatch.setattr(
        service_module,
        "_is_reparse_point",
        lambda path: switched["value"] and path.name == "source" or original_reparse(path),
    )
    with pytest.raises(ValueError, match="changed"):
        service.create_upload_staging_file("novel-route-project", principal="alice", suffix=".txt")
    assert not list((service.projects_root / "novel-route-project" / "source").glob(".upload-*"))


def test_legacy_local_owner_is_available_only_to_authenticated_desktop_principal(tmp_path):
    service = NovelVideoService(
        repo=NovelVideoRepository(OrchestrationDatabase(str(tmp_path / "novel.db"))),
        projects_root=tmp_path / "projects",
    )
    project = service.create_project(ProjectCreateRequest(**_project_payload()), principal="local")
    assert service.get_project_for_principal(project.id, principal="desktop").id == project.id
    with pytest.raises(PermissionError):
        service.get_project_for_principal(project.id, principal="alice")


def test_capability_handoff_is_private_file_not_http_response(tmp_path):
    from backend.novel_video.capability import write_desktop_capability

    path = write_desktop_capability(tmp_path / "runtime", "test-secret")
    assert path.read_text(encoding="utf-8") == "test-secret"
    assert path.name == "novel-video-capability"
    if os.name != "nt":
        assert path.stat().st_mode & 0o077 == 0


def test_vite_proxy_owns_capability_and_renderer_source_has_no_capability_env():
    root = Path(__file__).resolve().parents[2]
    vite = (root / "frontend" / "vite.config.ts").read_text(encoding="utf-8")
    renderer = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (root / "frontend" / "src").rglob("*.ts*")
    )
    launcher = (root / "run.bat").read_text(encoding="utf-8")
    assert "process.env.AI_MANGA_NOVEL_VIDEO_CAPABILITY" in vite
    assert "proxyReq.setHeader(\"X-Novel-Video-Capability\"" in vite
    assert "VITE_NOVEL_VIDEO_CAPABILITY" not in vite
    assert "VITE_NOVEL_VIDEO_CAPABILITY" not in renderer
    assert "X-Novel-Video-Capability" not in renderer
    assert "/core/novel-video/session" in renderer
    assert "--host 127.0.0.1" in launcher
    assert "--host 0.0.0.0" not in launcher


def test_main_lifespan_injects_the_formal_service(tmp_path, monkeypatch):
    from backend import main

    monkeypatch.chdir(tmp_path)
    lifecycle_calls = []
    monkeypatch.setattr(main.OrchestratorWorker, "start", lambda self: lifecycle_calls.append("start"))
    monkeypatch.setattr(main.OrchestratorWorker, "stop", lambda self: lifecycle_calls.append("stop"))
    app = FastAPI()

    async def exercise():
        async with main.lifespan(app):
            assert app.state.novel_video_service.repo is app.state.novel_video_repo
            assert app.state.novel_video_service.projects_root == (tmp_path / "projects").resolve()

    asyncio.run(exercise())
    assert lifecycle_calls == ["start", "stop"]
    assert not (tmp_path / "storage" / "runtime" / "novel-video-capability").exists()


def test_lifespan_closes_formal_repository_once_when_recovery_fails(tmp_path, monkeypatch):
    from backend import main

    monkeypatch.chdir(tmp_path)
    closed = []

    async def fail_recovery(*args, **kwargs):
        raise RuntimeError("recovery failure")

    monkeypatch.setattr(main, "reconcile_emergency_prompt_journals", fail_recovery)
    monkeypatch.setattr(main.NovelVideoRepository, "close", lambda self: closed.append("closed"))
    with pytest.raises(RuntimeError, match="recovery failure"):
        asyncio.run(_enter_lifespan(main, FastAPI()))
    assert closed == ["closed"]


async def _enter_lifespan(main_module, app):
    async with main_module.lifespan(app):
        raise AssertionError("recovery should have failed before yielding")


def test_run_commands_are_status_driven_and_event_page_resumes_from_database(client):
    assert client.post("/api/core/novel-video/projects", json=_project_payload()).status_code == 201
    _upload(client, "novel-route-project", "第一章\n故事内容足够用于测试。".encode())
    plan = client.post(
        "/api/core/novel-video/projects/novel-route-project/analyze",
        json={"chapter_indexes": [1], "target_seconds": 15, "max_shots": 3},
    ).json()
    run = _create_run(client, "novel-route-project", plan["plan_id"]).json()
    run_id = run["id"]
    assert client.post(f"/api/core/novel-video/runs/{run_id}/start", json={}).json()["status"] == "rendering"
    assert client.post(f"/api/core/novel-video/runs/{run_id}/pause", json={}).json()["status"] == "paused"
    assert client.post(f"/api/core/novel-video/runs/{run_id}/resume", json={}).json()["status"] == "rendering"
    assert client.post(f"/api/core/novel-video/runs/{run_id}/cancel", json={}).json()["status"] == "cancelled"
    assert client.post(f"/api/core/novel-video/runs/{run_id}/cancel", json={}).json()["status"] == "cancelled"

    first_page = client.get(f"/api/core/novel-video/runs/{run_id}/events?limit=1")
    assert first_page.status_code == 200
    assert len(first_page.json()["events"]) == 1
    after = first_page.json()["next_sequence"]
    resumed = client.get(f"/api/core/novel-video/runs/{run_id}/events?after=999", headers={"Last-Event-ID": str(after)})
    assert resumed.status_code == 200
    assert all(item["sequence"] > after for item in resumed.json()["events"])


def test_live_sse_reads_persisted_event_heartbeats_and_stops_on_disconnect(client):
    from backend.novel_video.routes import _stream_events

    assert client.post("/api/core/novel-video/projects", json=_project_payload()).status_code == 201
    _upload(client, "novel-route-project", "第一章\n故事内容足够用于测试。".encode())
    plan = client.post(
        "/api/core/novel-video/projects/novel-route-project/analyze",
        json={"chapter_indexes": [1], "target_seconds": 15, "max_shots": 3},
    ).json()
    run = _create_run(client, "novel-route-project", plan["plan_id"], key="sse-run-key").json()
    service = client.app.state.novel_video_service
    disconnected = iter([False, False, True])

    async def is_disconnected():
        return next(disconnected)

    async def consume():
        generator = _stream_events(
            service, run["id"], after=0, limit=10,
            is_disconnected=is_disconnected, heartbeat_seconds=0,
        )
        result = []
        async for item in generator:
            result.append(item)
        return result

    items = asyncio.run(consume())
    assert any("event: run_created" in item for item in items)
    assert ": heartbeat\n\n" in items


def test_sse_asgi_stream_honors_disconnect_and_send_backpressure(client):
    assert client.post("/api/core/novel-video/projects", json=_project_payload()).status_code == 201
    _upload(client, "novel-route-project", "第一章\n故事内容足够用于测试。".encode())
    plan = client.post(
        "/api/core/novel-video/projects/novel-route-project/analyze",
        json={"chapter_indexes": [1], "target_seconds": 15, "max_shots": 3},
    ).json()
    run = _create_run(client, "novel-route-project", plan["plan_id"], key="asgi-sse-run").json()
    session = client.cookies.get("novel_video_session")
    path = f"/api/core/novel-video/runs/{run['id']}/events"
    sent = []
    first_body_started = asyncio.Event()
    receive_count = 0

    async def receive():
        nonlocal receive_count
        receive_count += 1
        if receive_count == 1:
            return {"type": "http.request", "body": b"", "more_body": False}
        await first_body_started.wait()
        return {"type": "http.disconnect"}

    async def send(message):
        sent.append(message)
        if message["type"] == "http.response.body" and message.get("body"):
            first_body_started.set()
            # The producer must await this send; release only after the
            # disconnect is observable by the ASGI receive side.
            await asyncio.sleep(0.02)

    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "GET",
        "scheme": "http",
        "path": path,
        "raw_path": path.encode("ascii"),
        "query_string": b"stream=true&limit=1",
        "root_path": "",
        "headers": [
            (b"origin", b"http://localhost:5173"),
            (b"cookie", f"novel_video_session={session}".encode("ascii")),
        ],
        "client": ("127.0.0.1", 1),
        "server": ("127.0.0.1", 8000),
        "app": client.app,
        "state": {},
    }

    asyncio.run(asyncio.wait_for(client.app(scope, receive, send), timeout=2.0))
    assert first_body_started.is_set()
    assert receive_count >= 2
    assert sent[0]["type"] == "http.response.start"
    assert sent[0]["status"] == 200
    bodies = [message.get("body", b"") for message in sent if message["type"] == "http.response.body"]
    assert any(b"event: run_created" in body for body in bodies)
    assert len([body for body in bodies if body]) == 1


def test_shot_retry_requires_a_failed_or_blocked_shot(client):
    assert client.post("/api/core/novel-video/projects", json=_project_payload()).status_code == 201
    _upload(client, "novel-route-project", "第一章\n故事内容足够用于测试。".encode())
    plan = client.post(
        "/api/core/novel-video/projects/novel-route-project/analyze",
        json={"chapter_indexes": [1], "target_seconds": 15, "max_shots": 3},
    ).json()
    run = _create_run(client, "novel-route-project", plan["plan_id"], key="retry-run-key").json()
    service = client.app.state.novel_video_service
    shot = service.repo.list_shots(run["id"])[0]
    assert client.post(f"/api/core/novel-video/shots/{shot.id}/retry", json={}).status_code == 409
    service.repo.update_shot_status(shot.id, type(shot.status).BLOCKED)
    retried = client.post(f"/api/core/novel-video/shots/{shot.id}/retry", json={})
    assert retried.status_code == 200
    assert retried.json()["status"] == "queued"


def test_asset_approval_and_export_lookup_enforce_formal_ownership(client):
    assert client.post("/api/core/novel-video/projects", json=_project_payload()).status_code == 201
    _upload(client, "novel-route-project", "第一章\n故事内容足够用于测试。".encode())
    plan = client.post(
        "/api/core/novel-video/projects/novel-route-project/analyze",
        json={"chapter_indexes": [1], "target_seconds": 15, "max_shots": 3},
    ).json()
    run = _create_run(client, "novel-route-project", plan["plan_id"], key="asset-run-key").json()
    service = client.app.state.novel_video_service
    shot = service.repo.list_shots(run["id"])[0]
    candidate_path = service.repo.get_project("novel-route-project").root / "shots" / "candidate.png"
    candidate_path.parent.mkdir(parents=True, exist_ok=True)
    candidate_path.write_bytes(b"tail")
    from backend.novel_video.models import AssetVersion

    candidate = service.repo.append_asset(AssetVersion(
        id="route-tail", project_id="novel-route-project", run_id=run["id"], shot_id=shot.id,
        kind="tail", path=candidate_path, sha256=sha256(candidate_path.read_bytes()).hexdigest(),
    ))
    approved = client.post(f"/api/core/novel-video/assets/{candidate.id}/approve", json={"approve_tail": True})
    assert approved.status_code == 200, approved.text
    assert approved.json()["state"] == "approved"
    assert client.get("/api/core/novel-video/exports/not-an-export").status_code == 404
