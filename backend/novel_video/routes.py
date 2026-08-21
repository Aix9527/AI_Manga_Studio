"""HTTP boundary for the formal, local-first novel-to-video workflow.

The browser may upload bytes and choose production settings, but it can never
name a server-side source path.  All durable state and authorization decisions
remain in :class:`NovelVideoService` and its repository.
"""
from __future__ import annotations

import asyncio
import hmac
import hashlib
import json
import logging
import re
import sqlite3
import secrets
import threading
import time
from datetime import datetime, timedelta, timezone
from dataclasses import asdict
from pathlib import Path
from typing import Any, AsyncIterator

from fastapi import APIRouter, Body, File, Header, HTTPException, Query, Request, UploadFile, status
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse, Response, StreamingResponse

from backend.novel_video.models import RunCommand
from backend.novel_video.schemas import (
    AssetApprovalRequest,
    ChapterSelectionRequest,
    EmptyRequest,
    ProjectCreateRequest,
    RunCreateRequest,
    ShotReviewRequest,
    SourceImportResponse,
)
from backend.novel_video.service import NovelVideoService
from backend.production.input_loader import InputDecodeError
from backend.production.preflight import run_preflight


router = APIRouter()
logger = logging.getLogger(__name__)

MAX_SOURCE_BYTES = 20 * 1024 * 1024
MAX_MULTIPART_OVERHEAD_BYTES = 256 * 1024
MAX_NOVEL_VIDEO_REQUEST_BYTES = MAX_SOURCE_BYTES + MAX_MULTIPART_OVERHEAD_BYTES
MAX_SSE_EVENT_BYTES = 64 * 1024
SESSION_TTL_SECONDS = 10 * 60
PROXY_ASSERTION_TTL_SECONDS = 30
MAX_PROXY_NONCES = 4096
_FORMAL_PREFIX = "/api/core/novel-video/"
_EVENTS_PATH = re.compile(r"^/api/core/novel-video/runs/[^/]+/events$")
_SAFE_FILENAME = re.compile(r'^[^<>:"/\\|?*\x00-\x1f]{1,240}\.(?:txt|md)$', re.IGNORECASE)
_TEXT_CONTENT_TYPES = {"text/plain", "text/markdown", "application/octet-stream"}


class _BodyTooLarge(Exception):
    pass


class ProxyNonceCache:
    """Atomic, bounded replay cache that never evicts an unexpired nonce."""

    def __init__(
        self,
        *,
        max_entries: int = MAX_PROXY_NONCES,
        ttl_seconds: float = PROXY_ASSERTION_TTL_SECONDS,
    ):
        if max_entries < 1 or ttl_seconds <= 0:
            raise ValueError("nonce cache bounds must be positive")
        self._max_entries = max_entries
        self._ttl_seconds = ttl_seconds
        self._expires_at: dict[str, float] = {}
        self._lock = threading.Lock()

    def consume(self, nonce: str, *, now: float | None = None) -> str:
        current = time.monotonic() if now is None else now
        with self._lock:
            expired = [key for key, expiry in self._expires_at.items() if expiry <= current]
            for key in expired:
                del self._expires_at[key]
            if nonce in self._expires_at:
                return "replayed"
            if len(self._expires_at) >= self._max_entries:
                return "full"
            self._expires_at[nonce] = current + self._ttl_seconds
            return "accepted"

    def __len__(self) -> int:
        with self._lock:
            return len(self._expires_at)


class NovelVideoIngressLimitMiddleware:
    """Pass through raw ASGI chunks while counting before multipart spooling."""

    def __init__(self, app, *, limit_bytes: int = MAX_NOVEL_VIDEO_REQUEST_BYTES):
        self.app = app
        self.limit_bytes = limit_bytes

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or not scope.get("path", "").startswith("/api/core/novel-video/"):
            await self.app(scope, receive, send)
            return
        headers = {key.lower(): value for key, value in scope.get("headers", [])}
        content_length = headers.get(b"content-length")
        if content_length and content_length.isdigit() and int(content_length) > self.limit_bytes:
            await self._too_large(send)
            return
        received = 0
        response_started = False

        async def bounded_receive():
            nonlocal received
            message = await receive()
            if message.get("type") == "http.request":
                received += len(message.get("body", b""))
                if received > self.limit_bytes:
                    raise _BodyTooLarge()
            return message

        async def guarded_send(message):
            nonlocal response_started
            if message.get("type") == "http.response.start":
                response_started = True
            await send(message)

        try:
            await self.app(scope, bounded_receive, guarded_send)
        except _BodyTooLarge:
            if not response_started:
                await self._too_large(send)

    @staticmethod
    async def _too_large(send):
        body = b'{"detail":{"code":"source_too_large","message":"request body exceeds the permitted size"}}'
        await send({"type": "http.response.start", "status": 413, "headers": [(b"content-type", b"application/json"), (b"content-length", str(len(body)).encode())]})
        await send({"type": "http.response.body", "body": body})


def _service(request: Request) -> NovelVideoService:
    service = getattr(request.app.state, "novel_video_service", None)
    if not isinstance(service, NovelVideoService):
        raise HTTPException(status_code=503, detail="formal novel-video service is unavailable")
    return service


def _error(status_code: int, code: str, message: str) -> HTTPException:
    return HTTPException(status_code=status_code, detail={"code": code, "message": message})


def _validate_origin(request: Request) -> None:
    origin = request.headers.get("origin")
    allowed_origins = set(getattr(request.app.state, "novel_video_allowed_origins", ()))
    if origin not in allowed_origins:
        raise _error(403, "origin_forbidden", "this origin is not permitted")


def _canonical_formal_target(request: Request) -> str:
    """Return the validated raw request target shared with the Vite signer.

    Formal paths deliberately permit ASCII literals only.  All routes reject
    queries except the event endpoint, whose numeric/boolean query is signed as
    the exact raw byte sequence (including order and duplicate keys).
    """
    raw_path = request.scope.get("raw_path", b"")
    try:
        if isinstance(raw_path, bytes):
            raw_path = raw_path.decode("ascii", "strict")
        raw_query = request.scope.get("query_string", b"")
        if isinstance(raw_query, bytes):
            raw_query = raw_query.decode("ascii", "strict")
    except (UnicodeDecodeError, UnicodeEncodeError) as exc:
        raise _error(403, "proxy_assertion_invalid", "the local proxy assertion is invalid") from exc
    if not isinstance(raw_path, str) or raw_path != request.url.path:
        raise _error(403, "proxy_assertion_invalid", "the local proxy assertion is invalid")
    if not isinstance(raw_query, str):
        raise _error(403, "proxy_assertion_invalid", "the local proxy assertion is invalid")
    if (
        not raw_path.startswith(_FORMAL_PREFIX)
        or "%" in raw_path
        or "\\" in raw_path
        or "\x00" in raw_path
        or any(part in {".", ".."} for part in raw_path.split("/"))
        or raw_path.endswith("/")
    ):
        raise _error(403, "proxy_assertion_invalid", "the local proxy assertion is invalid")
    if not raw_query:
        return raw_path
    if not _EVENTS_PATH.fullmatch(raw_path) or "%" in raw_query or "\\" in raw_query or "\x00" in raw_query:
        raise _error(403, "proxy_assertion_invalid", "the local proxy assertion is invalid")
    for field in raw_query.split("&"):
        if "=" not in field:
            raise _error(403, "proxy_assertion_invalid", "the local proxy assertion is invalid")
        key, value = field.split("=", 1)
        if key in {"after", "limit"}:
            valid = bool(value) and value.isascii() and value.isdigit()
        elif key == "stream":
            valid = value in {"0", "1", "true", "false"}
        else:
            valid = False
        if not valid:
            raise _error(403, "proxy_assertion_invalid", "the local proxy assertion is invalid")
    return f"{raw_path}?{raw_query}"


def _validate_proxy_assertion(request: Request) -> None:
    """Require a short-lived Vite-server HMAC on every formal request."""
    if getattr(request.app.state, "novel_video_proxy_assertion_bypass", False):
        return
    secret = getattr(request.app.state, "novel_video_proxy_secret", "")
    timestamp = request.headers.get("x-novel-proxy-timestamp", "")
    nonce = request.headers.get("x-novel-proxy-nonce", "")
    supplied = request.headers.get("x-novel-proxy-assertion", "")
    if (
        not isinstance(secret, str)
        or not secret
        or len(timestamp) != 10
        or not timestamp.isascii()
        or not timestamp.isdigit()
        or len(nonce) < 20
        or len(nonce) > 128
        or not supplied
    ):
        raise _error(403, "proxy_assertion_required", "a valid local proxy assertion is required")
    now = datetime.now(timezone.utc).timestamp()
    try:
        timestamp_seconds = int(timestamp)
    except (TypeError, ValueError, OverflowError) as exc:
        raise _error(403, "proxy_assertion_required", "a valid local proxy assertion is required") from exc
    if abs(now - timestamp_seconds) > PROXY_ASSERTION_TTL_SECONDS:
        raise _error(403, "proxy_assertion_expired", "the local proxy assertion has expired")
    target = _canonical_formal_target(request)
    session_id = request.cookies.get("novel_video_session", "-")
    message = "\n".join((timestamp, nonce, request.method.upper(), target, session_id))
    expected = hmac.new(secret.encode("utf-8"), message.encode("utf-8"), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(supplied, expected):
        raise _error(403, "proxy_assertion_invalid", "the local proxy assertion is invalid")
    nonces = getattr(request.app.state, "novel_video_proxy_nonces", None)
    if not isinstance(nonces, ProxyNonceCache):
        raise _error(503, "proxy_assertion_unavailable", "the local proxy assertion service is unavailable")
    nonce_result = nonces.consume(nonce)
    if nonce_result == "replayed":
        raise _error(403, "proxy_assertion_replayed", "the local proxy assertion was already used")
    if nonce_result == "full":
        raise _error(429, "proxy_assertion_capacity", "the local proxy assertion service is busy")


def _authorize_session(request: Request) -> str:
    """All formal routes except handshake require a bounded browser session."""
    if request.method.upper() not in {"GET", "HEAD"}:
        _validate_origin(request)
    _validate_proxy_assertion(request)
    session = request.cookies.get("novel_video_session", "")
    record = getattr(request.app.state, "novel_video_sessions", {}).get(session)
    if not isinstance(record, dict):
        raise _error(403, "session_required", "a valid local browser session is required")
    expires_at = record.get("expires_at")
    if not isinstance(expires_at, datetime) or expires_at <= datetime.now(timezone.utc):
        request.app.state.novel_video_sessions.pop(session, None)
        raise _error(403, "session_expired", "the local browser session has expired")
    principal = record.get("principal")
    if not isinstance(principal, str):
        raise _error(403, "session_required", "a valid local browser session is required")
    return principal


def _authorize_capability_handshake(request: Request) -> str:
    """The only endpoint that ever accepts the opaque capability header."""
    _validate_origin(request)
    _validate_proxy_assertion(request)
    capabilities = getattr(request.app.state, "novel_video_capabilities", {})
    capability = request.headers.get("x-novel-video-capability", "")
    for configured, principal in capabilities.items():
        if hmac.compare_digest(capability, configured):
            return principal
    raise _error(403, "capability_required", "a valid local capability is required")


@router.post("/session", status_code=status.HTTP_204_NO_CONTENT)
def establish_browser_session(request: Request):
    """Capability-protected proxy handshake; the browser never sees the token."""
    principal = _authorize_capability_handshake(request)
    session = secrets.token_urlsafe(32)
    sessions = getattr(request.app.state, "novel_video_sessions", None)
    if not isinstance(sessions, dict):
        raise _error(503, "session_unavailable", "the local session service is unavailable")
    # One session per principal: a new proxy handshake rotates the old cookie.
    for existing, record in list(sessions.items()):
        if isinstance(record, dict) and record.get("principal") == principal:
            sessions.pop(existing, None)
    sessions[session] = {
        "principal": principal,
        "expires_at": datetime.now(timezone.utc) + timedelta(seconds=SESSION_TTL_SECONDS),
    }
    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    response.set_cookie(
        "novel_video_session", session, httponly=True, samesite="strict",
        secure=request.url.scheme == "https", path="/api/core/novel-video",
        max_age=SESSION_TTL_SECONDS,
    )
    return response


def _raise_domain_error(exc: Exception, *, value_status: int = 409) -> None:
    if isinstance(exc, HTTPException):
        raise exc
    logger.exception("novel-video route failed", exc_info=exc)
    if isinstance(exc, KeyError):
        raise _error(404, "not_found", "the requested formal resource does not exist") from exc
    if isinstance(exc, PermissionError):
        raise _error(403, "forbidden", "the requested operation is not authorized") from exc
    if isinstance(exc, InputDecodeError):
        raise _error(422, "invalid_source", "the uploaded source is not valid text") from exc
    if isinstance(exc, sqlite3.IntegrityError):
        raise _error(409, "conflict", "the resource already exists") from exc
    if isinstance(exc, FileNotFoundError):
        raise _error(404, "not_found", "the requested file is unavailable") from exc
    if isinstance(exc, ValueError):
        raise _error(value_status, "invalid_state" if value_status == 409 else "invalid_request", "the request cannot be completed in its current state") from exc
    raise _error(500, "internal_error", "the formal service could not complete the request") from exc


def _model(value: Any) -> dict[str, Any]:
    return jsonable_encoder(value.model_dump(mode="json"))


def _plan(value: Any) -> dict[str, Any]:
    return jsonable_encoder(asdict(value))


@router.post("/projects", status_code=status.HTTP_201_CREATED)
def create_project(payload: ProjectCreateRequest, request: Request):
    try:
        return _model(_service(request).create_project(payload, principal=_authorize_session(request)))
    except Exception as exc:  # Turn domain errors into explicit HTTP decisions.
        _raise_domain_error(exc)


@router.get("/projects/{project_id}")
def get_project(project_id: str, request: Request):
    try:
        return _model(_service(request).get_project_for_principal(project_id, principal=_authorize_session(request)))
    except Exception as exc:
        _raise_domain_error(exc)


@router.post("/projects/{project_id}/source", status_code=status.HTTP_201_CREATED)
async def import_source(
    project_id: str,
    request: Request,
    file: UploadFile = File(...),
):
    filename = file.filename or ""
    if (
        not _SAFE_FILENAME.fullmatch(filename)
        or Path(filename).name != filename
        or "\\" in filename
    ):
        raise HTTPException(status_code=400, detail="source filename must be a safe .txt or .md basename")
    if file.content_type not in _TEXT_CONTENT_TYPES:
        raise HTTPException(status_code=400, detail="source upload must use a text content type")
    service = _service(request)
    temporary_path: Path | None = None
    temporary_file = None
    try:
        principal = _authorize_session(request)
        temporary_path, temporary_file = service.create_upload_staging_file(
            project_id, principal=principal, suffix=Path(filename).suffix,
        )
        total = 0
        while chunk := await file.read(64 * 1024):
            total += len(chunk)
            if total > MAX_SOURCE_BYTES:
                raise _error(413, "source_too_large", "source upload exceeds the permitted size")
            temporary_file.write(chunk)
        temporary_file.flush()
        temporary_file.close()
        temporary_file = None
        result = service.import_source(project_id, temporary_path)
        return SourceImportResponse(
            project_id=project_id,
            asset_id=result.asset.id,
            sha256=result.sha256,
            encoding=result.encoding,
            chapter_count=result.loaded.contract.chapter_count,
        )
    except HTTPException:
        raise
    except Exception as exc:
        _raise_domain_error(exc, value_status=422)
    finally:
        if temporary_file is not None:
            temporary_file.close()
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
        await file.close()


@router.post("/projects/{project_id}/analyze")
def analyze_project(project_id: str, payload: ChapterSelectionRequest, request: Request):
    try:
        service = _service(request)
        service.get_project_for_principal(project_id, principal=_authorize_session(request))
        return _plan(service.analyze(
            project_id,
            chapter_indexes=payload.chapter_indexes,
            target_seconds=payload.target_seconds,
            max_shots=payload.max_shots,
            provider=payload.provider,
        ))
    except Exception as exc:
        _raise_domain_error(exc, value_status=422)


@router.patch("/projects/{project_id}/chapters")
def select_chapters(project_id: str, payload: ChapterSelectionRequest, request: Request):
    """Persist a new immutable chapter-plan version for the selected chapters."""
    return analyze_project(project_id, payload, request)


@router.post("/projects/{project_id}/bible")
async def generate_bible(project_id: str, request: Request, _: EmptyRequest = Body(...)):
    """Generate approved scene reference images for the latest chapter plan."""
    service = _service(request)
    service.get_project_for_principal(project_id, principal=_authorize_session(request))
    plan_id = None
    for run in reversed(service.repo.list_runs()):
        if run.project_id != project_id:
            continue
        candidate = run.settings.get("chapter_plan_id")
        if candidate:
            plan_id = candidate
            break
    if not plan_id:
        raise _error(409, "plan_required", "analyze a chapter plan before generating bible assets")
    created = await service.generate_bible_assets(project_id, plan_id=plan_id)
    return {"assets": created, "count": len(created)}


@router.post("/projects/{project_id}/preflight")
async def project_preflight(project_id: str, request: Request):
    service = _service(request)
    try:
        project = service.get_project_for_principal(project_id, principal=_authorize_session(request))
    except Exception as exc:
        _raise_domain_error(exc)
    try:
        report = await run_preflight(
            provider=project.primary_video_engine,
            output_root=project.root,
        )
    except Exception as exc:  # A down local ComfyUI is a reportable preflight blocker, not a fake success.
        logger.exception("novel-video preflight unavailable", exc_info=exc)
        return {"ready": False, "blockers": ["preflight_unavailable"], "warnings": []}
    return {
        "ready": report.ok,
        "blockers": list(report.missing),
        "warnings": [check.detail for check in report.checks if not check.ok],
        "resolved_models": dict(report.resolved),
    }


@router.post("/projects/{project_id}/runs")
def create_run(
    project_id: str, payload: RunCreateRequest, request: Request,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    if not idempotency_key or len(idempotency_key) > 200 or any(ord(char) < 33 or ord(char) > 126 for char in idempotency_key):
        raise _error(400, "idempotency_key_required", "a valid Idempotency-Key is required")
    try:
        principal = _authorize_session(request)
        fingerprint = hashlib.sha256(json.dumps({"plan_id": payload.plan_id, "mode": payload.mode.value if payload.mode else None}, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        run, replayed = _service(request).create_run_idempotent(
            project_id, plan_id=payload.plan_id, mode=payload.mode, principal=principal,
            idempotency_key=idempotency_key, request_fingerprint=fingerprint,
        )
        return JSONResponse(_model(run), status_code=200 if replayed else status.HTTP_201_CREATED)
    except Exception as exc:
        _raise_domain_error(exc, value_status=409)


@router.get("/runs/{run_id}")
def get_run(run_id: str, request: Request):
    try:
        return _model(_service(request).get_run_for_principal(run_id, principal=_authorize_session(request)))
    except Exception as exc:
        _raise_domain_error(exc)


def _command_route(run_id: str, command: RunCommand, request: Request):
    try:
        service = _service(request)
        service.get_run_for_principal(run_id, principal=_authorize_session(request))
        return _model(service.command(run_id, command))
    except Exception as exc:
        _raise_domain_error(exc)


@router.post("/runs/{run_id}/start")
def start_run(run_id: str, request: Request, _: EmptyRequest = Body(...)):
    return _command_route(run_id, RunCommand.START, request)


@router.post("/runs/{run_id}/pause")
def pause_run(run_id: str, request: Request, _: EmptyRequest = Body(...)):
    return _command_route(run_id, RunCommand.PAUSE, request)


@router.post("/runs/{run_id}/resume")
def resume_run(run_id: str, request: Request, _: EmptyRequest = Body(...)):
    return _command_route(run_id, RunCommand.RESUME, request)


@router.post("/runs/{run_id}/retry")
def retry_run(run_id: str, request: Request, _: EmptyRequest = Body(...)):
    """Recover a blocked or interrupted run by requeueing its failed shots."""
    return _command_route(run_id, RunCommand.RETRY, request)


@router.post("/runs/{run_id}/cancel")
def cancel_run(run_id: str, request: Request, _: EmptyRequest = Body(...)):
    return _command_route(run_id, RunCommand.CANCEL, request)


@router.post("/shots/{shot_id}/retry")
def retry_shot(shot_id: str, request: Request, _: EmptyRequest = Body(...)):
    try:
        service = _service(request)
        shot = service.repo.get_shot(shot_id)
        if shot is None:
            raise KeyError("shot does not exist")
        service.get_run_for_principal(shot.run_id, principal=_authorize_session(request))
        return _model(service.retry_shot(shot_id))
    except Exception as exc:
        _raise_domain_error(exc)


@router.post("/shots/{shot_id}/review")
def review_shot(shot_id: str, payload: ShotReviewRequest, request: Request):
    try:
        service = _service(request)
        shot = service.repo.get_shot(shot_id)
        if shot is None:
            raise KeyError("shot does not exist")
        service.get_run_for_principal(shot.run_id, principal=_authorize_session(request))
        return _model(service.review_shot_candidate(
            shot_id, approve=payload.approve, candidate_video_id=payload.candidate_video_id,
            candidate_tail_id=payload.candidate_tail_id,
            qa=payload.qa.model_dump() if payload.qa else None,
        ))
    except Exception as exc:
        _raise_domain_error(exc)


@router.post("/assets/{asset_id}/approve")
def approve_asset(asset_id: str, payload: AssetApprovalRequest, request: Request):
    try:
        service = _service(request)
        service.get_asset_for_principal(asset_id, principal=_authorize_session(request))
        return _model(service.approve_asset(asset_id, approve_tail=payload.approve_tail))
    except Exception as exc:
        _raise_domain_error(exc)


@router.get("/exports/{export_id}")
def get_export(export_id: str, request: Request):
    try:
        service = _service(request)
        service.get_asset_for_principal(export_id, principal=_authorize_session(request))
        return _model(service.get_export(export_id))
    except Exception as exc:
        _raise_domain_error(exc)


def _event_page(service: NovelVideoService, run_id: str, after: int, limit: int) -> dict[str, Any]:
    events = service.events_page(run_id, after_sequence=after, limit=limit)
    return {
        "events": [_model(event) for event in events],
        "next_sequence": events[-1].sequence if events else None,
    }


def _event_sse(event: dict[str, Any]) -> str:
    encoded = json.dumps(event, ensure_ascii=False, separators=(",", ":"))
    if len(encoded.encode("utf-8")) > MAX_SSE_EVENT_BYTES:
        raise ValueError("event payload exceeds streaming limit")
    return (
        f"id: {event['sequence']}\n"
        f"event: {event['event_type']}\n"
        f"data: {encoded}\n\n"
    )


async def _stream_events(
    service: NovelVideoService, run_id: str, *, after: int, limit: int,
    is_disconnected, heartbeat_seconds: float = 0.5,
) -> AsyncIterator[str]:
    """Bounded DB polling generator; it retains no unbounded event queue."""
    cursor = after
    while True:
        try:
            page = _event_page(service, run_id, cursor, limit)
        except Exception:
            return
        for event in page["events"]:
            cursor = int(event["sequence"])
            yield _event_sse(event)
        if await is_disconnected():
            return
        if not page["events"]:
            yield ": heartbeat\n\n"
        await asyncio.sleep(heartbeat_seconds)


@router.get("/runs/{run_id}/events")
async def run_events(
    run_id: str,
    request: Request,
    after: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    stream: bool = False,
    last_event_id: str | None = Header(default=None, alias="Last-Event-ID"),
):
    if last_event_id is not None:
        try:
            after = int(last_event_id)
        except ValueError as exc:
            raise _error(422, "invalid_event_cursor", "Last-Event-ID must be a non-negative integer") from exc
        if after < 0:
            raise _error(422, "invalid_event_cursor", "Last-Event-ID must be a non-negative integer")
    service = _service(request)
    try:
        service.get_run_for_principal(run_id, principal=_authorize_session(request))
        page = _event_page(service, run_id, after, limit)
    except Exception as exc:
        _raise_domain_error(exc)
    if not stream:
        return JSONResponse(page)

    return StreamingResponse(
        _stream_events(
            service, run_id, after=after, limit=limit,
            is_disconnected=request.is_disconnected,
        ),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.api_route(
    "/{unmatched_path:path}",
    methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"],
    include_in_schema=False,
)
def reject_unmatched_formal_target(unmatched_path: str, request: Request):
    """Authenticate malformed formal targets instead of redirecting them."""
    _validate_origin(request)
    _validate_proxy_assertion(request)
    raise _error(404, "not_found", "the requested formal resource does not exist")
