from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any
from hashlib import sha256
from pathlib import Path


MAX_EVENT_PAYLOAD_BYTES = 64 * 1024

from backend.novel_video.models import (
    AssetVersion,
    NovelVideoProject,
    ProductionRun,
    RunEvent,
    RunStatus,
    ShotRecord,
    ShotStatus,
)
from backend.novel_video.state_machine import InvalidTransition, transition_run, transition_shot
from backend.orchestration.database import OrchestrationDatabase
from backend.production.contracts import ChapterPlanBundle, DialogueLine, ScenePlan, ShotPlan


class ConcurrentTransitionError(RuntimeError):
    """Raised when a guarded state update loses its compare-and-swap race."""


class NovelVideoRepository:
    def __init__(self, database: OrchestrationDatabase):
        self.database = database
        self.ensure_schema()

    def ensure_schema(self) -> None:
        statements = (
            """CREATE TABLE IF NOT EXISTS novel_video_projects (
                id TEXT PRIMARY KEY, payload TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
            )""",
            """CREATE TABLE IF NOT EXISTS novel_video_runs (
                id TEXT PRIMARY KEY, project_id TEXT NOT NULL, status TEXT NOT NULL,
                payload TEXT NOT NULL, lease_id TEXT, lease_expires_at TEXT,
                created_at TEXT NOT NULL, updated_at TEXT NOT NULL
            )""",
            """CREATE TABLE IF NOT EXISTS novel_video_shots (
                id TEXT PRIMARY KEY, run_id TEXT NOT NULL, sequence INTEGER NOT NULL,
                status TEXT NOT NULL, payload TEXT NOT NULL, updated_at TEXT NOT NULL,
                UNIQUE(run_id, sequence)
            )""",
            """CREATE TABLE IF NOT EXISTS novel_video_assets (
                id TEXT PRIMARY KEY, project_id TEXT NOT NULL, run_id TEXT NOT NULL,
                shot_id TEXT, parent_id TEXT, kind TEXT NOT NULL, state TEXT NOT NULL,
                path TEXT NOT NULL, sha256 TEXT NOT NULL, payload TEXT NOT NULL, created_at TEXT NOT NULL
            )""",
            """CREATE UNIQUE INDEX IF NOT EXISTS idx_novel_video_assets_path
               ON novel_video_assets(path)""",
            """CREATE TABLE IF NOT EXISTS novel_video_events (
                sequence INTEGER PRIMARY KEY AUTOINCREMENT, run_id TEXT NOT NULL,
                event_type TEXT NOT NULL, payload TEXT NOT NULL, created_at TEXT NOT NULL
            )""",
            """CREATE TABLE IF NOT EXISTS novel_video_chapter_plans (
                project_id TEXT NOT NULL, selection_key TEXT NOT NULL,
                source_asset_id TEXT NOT NULL, payload TEXT NOT NULL,
                created_at TEXT NOT NULL,
                PRIMARY KEY (project_id, selection_key)
            )""",
            """CREATE TABLE IF NOT EXISTS novel_video_chapter_plan_versions (
                plan_id TEXT PRIMARY KEY, project_id TEXT NOT NULL,
                source_asset_id TEXT NOT NULL, source_sha256 TEXT NOT NULL,
                selection_key TEXT NOT NULL, target_seconds REAL NOT NULL,
                max_shots INTEGER, payload TEXT NOT NULL, created_at TEXT NOT NULL,
                UNIQUE(project_id, source_asset_id, selection_key, target_seconds, max_shots)
            )""",
            """CREATE TABLE IF NOT EXISTS novel_video_run_idempotency (
                project_id TEXT NOT NULL, principal TEXT NOT NULL,
                idempotency_key TEXT NOT NULL, request_fingerprint TEXT NOT NULL,
                run_id TEXT NOT NULL UNIQUE, created_at TEXT NOT NULL,
                PRIMARY KEY (project_id, principal, idempotency_key)
            )""",
            """CREATE TABLE IF NOT EXISTS novel_video_shot_decisions (
                transaction_token TEXT PRIMARY KEY, run_id TEXT NOT NULL,
                shot_id TEXT NOT NULL UNIQUE, candidate_video_id TEXT NOT NULL,
                candidate_tail_id TEXT NOT NULL, approved_video_id TEXT NOT NULL,
                approved_tail_id TEXT NOT NULL, request_sha256 TEXT NOT NULL,
                payload TEXT NOT NULL, created_at TEXT NOT NULL
            )""",
        )
        with self.database.transaction(immediate=True) as conn:
            for statement in statements:
                conn.execute(statement)

    def create_project(self, project: NovelVideoProject) -> NovelVideoProject:
        with self.database.transaction(immediate=True) as conn:
            conn.execute(
                "INSERT INTO novel_video_projects (id, payload, created_at, updated_at) VALUES (?, ?, ?, ?)",
                (project.id, project.model_dump_json(), project.created_at.isoformat(), project.updated_at.isoformat()),
            )
        return project

    def get_project(self, project_id: str) -> NovelVideoProject | None:
        row = self._fetch_one("SELECT payload FROM novel_video_projects WHERE id = ?", (project_id,))
        return NovelVideoProject.model_validate_json(row["payload"]) if row else None

    def update_project(self, project: NovelVideoProject) -> NovelVideoProject:
        """Persist a revised project record without altering its immutable assets."""
        with self.database.transaction(immediate=True) as conn:
            cursor = conn.execute(
                """UPDATE novel_video_projects SET payload = ?, updated_at = ?
                   WHERE id = ?""",
                (project.model_dump_json(), project.updated_at.isoformat(), project.id),
            )
            if cursor.rowcount != 1:
                raise KeyError(f"project {project.id} does not exist")
        return project

    def list_projects(self) -> list[NovelVideoProject]:
        with self.database.connect() as conn:
            rows = conn.execute("SELECT payload FROM novel_video_projects ORDER BY id").fetchall()
        return [NovelVideoProject.model_validate_json(row["payload"]) for row in rows]

    def save_run(self, run: ProductionRun) -> ProductionRun:
        with self.database.transaction(immediate=True) as conn:
            row = conn.execute(
                "SELECT status FROM novel_video_runs WHERE id = ?", (run.id,)
            ).fetchone()
            if row is None:
                if run.status is not RunStatus.DRAFT:
                    raise InvalidTransition("new run must start in draft")
                conn.execute(
                    """INSERT INTO novel_video_runs
                       (id, project_id, status, payload, lease_id, lease_expires_at, created_at, updated_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                    self._run_parameters(run),
                )
            else:
                current = RunStatus(row["status"])
                transition_run(current, run.status)
                self._update_run_row(conn, run, current)
        return run

    def create_run_with_shots(
        self, run: ProductionRun, shots: list[ShotRecord]
    ) -> ProductionRun:
        """Create a draft run and its ordered draft shots in one transaction."""
        if run.status is not RunStatus.DRAFT:
            raise InvalidTransition("new run must start in draft")
        if not shots or any(shot.run_id != run.id for shot in shots):
            raise ValueError("run shots must be non-empty and owned by the new run")
        expected = list(range(1, len(shots) + 1))
        if [shot.sequence for shot in shots] != expected:
            raise ValueError("run shots must have contiguous ordered sequences")
        if any(shot.status is not ShotStatus.DRAFT for shot in shots):
            raise InvalidTransition("new shots must start in draft")
        with self.database.transaction(immediate=True) as conn:
            if conn.execute("SELECT 1 FROM novel_video_runs WHERE id = ?", (run.id,)).fetchone():
                raise ValueError(f"run {run.id} already exists")
            conn.execute(
                """INSERT INTO novel_video_runs
                   (id, project_id, status, payload, lease_id, lease_expires_at, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                self._run_parameters(run),
            )
            for shot in shots:
                conn.execute(
                    """INSERT INTO novel_video_shots
                       (id, run_id, sequence, status, payload, updated_at)
                       VALUES (?, ?, ?, ?, ?, ?)""",
                    self._shot_parameters(shot),
                )
        return run

    def create_run_with_shots_idempotent(
        self, run: ProductionRun, shots: list[ShotRecord], *, principal: str,
        idempotency_key: str, request_fingerprint: str,
    ) -> tuple[ProductionRun, bool]:
        """Atomically create one formal run or return its exact prior replay."""
        if not principal or not idempotency_key or not request_fingerprint:
            raise ValueError("idempotency principal, key, and fingerprint are required")
        if run.status is not RunStatus.DRAFT or not shots or any(shot.run_id != run.id for shot in shots):
            raise ValueError("idempotent formal run must start with owned draft shots")
        if [shot.sequence for shot in shots] != list(range(1, len(shots) + 1)):
            raise ValueError("run shots must have contiguous ordered sequences")
        with self.database.transaction(immediate=True) as conn:
            row = conn.execute(
                "SELECT request_fingerprint, run_id FROM novel_video_run_idempotency "
                "WHERE project_id = ? AND principal = ? AND idempotency_key = ?",
                (run.project_id, principal, idempotency_key),
            ).fetchone()
            if row is not None:
                if row["request_fingerprint"] != request_fingerprint:
                    raise ValueError("idempotency key was already used for a different request")
                replay = conn.execute(
                    "SELECT payload FROM novel_video_runs WHERE id = ?", (row["run_id"],)
                ).fetchone()
                if replay is None:
                    raise RuntimeError("idempotency record has no formal run")
                return ProductionRun.model_validate_json(replay["payload"]), True
            conn.execute(
                """INSERT INTO novel_video_runs
                   (id, project_id, status, payload, lease_id, lease_expires_at, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                self._run_parameters(run),
            )
            for shot in shots:
                conn.execute(
                    """INSERT INTO novel_video_shots
                       (id, run_id, sequence, status, payload, updated_at)
                       VALUES (?, ?, ?, ?, ?, ?)""",
                    self._shot_parameters(shot),
                )
            conn.execute(
                """INSERT INTO novel_video_run_idempotency
                   (project_id, principal, idempotency_key, request_fingerprint, run_id, created_at)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (run.project_id, principal, idempotency_key, request_fingerprint, run.id, datetime.now(timezone.utc).isoformat()),
            )
        return run, False

    def get_run(self, run_id: str) -> ProductionRun | None:
        row = self._fetch_one("SELECT payload FROM novel_video_runs WHERE id = ?", (run_id,))
        return ProductionRun.model_validate_json(row["payload"]) if row else None

    def list_runs(self) -> list[ProductionRun]:
        with self.database.connect() as conn:
            rows = conn.execute(
                "SELECT payload FROM novel_video_runs ORDER BY created_at, id"
            ).fetchall()
        return [ProductionRun.model_validate_json(row["payload"]) for row in rows]

    def active_lease_ids(self, now: datetime) -> set[str]:
        if now.tzinfo is None or now.utcoffset() != timezone.utc.utcoffset(now):
            raise ValueError("now must use a UTC offset of zero")
        with self.database.connect() as conn:
            rows = conn.execute(
                """SELECT lease_id FROM novel_video_runs
                   WHERE lease_id IS NOT NULL AND lease_id != ''
                     AND lease_expires_at IS NOT NULL AND lease_expires_at > ?""",
                (now.isoformat(),),
            ).fetchall()
        return {row["lease_id"] for row in rows}

    def claim_run_lease(self, run_id: str, lease_id: str, expires_at: datetime) -> bool:
        """Atomically claim one persisted runner lease, never stealing a live owner."""
        if expires_at.tzinfo is None or expires_at.utcoffset() != timezone.utc.utcoffset(expires_at):
            raise ValueError("lease expiry must use a UTC offset of zero")
        now = datetime.now(timezone.utc)
        with self.database.transaction(immediate=True) as conn:
            row = conn.execute("SELECT status, payload FROM novel_video_runs WHERE id = ?", (run_id,)).fetchone()
            if row is None:
                raise KeyError(f"run {run_id} does not exist")
            run = ProductionRun.model_validate_json(row["payload"])
            updated = run.model_copy(update={"lease_id": lease_id, "lease_expires_at": expires_at, "updated_at": now})
            cursor = conn.execute(
                """UPDATE novel_video_runs SET lease_id = ?, lease_expires_at = ?, payload = ?, updated_at = ?
                   WHERE id = ? AND status = ? AND (lease_id IS NULL OR lease_id = '' OR lease_expires_at <= ?)""",
                (lease_id, expires_at.isoformat(), updated.model_dump_json(), now.isoformat(), run_id, row["status"], now.isoformat()),
            )
        return cursor.rowcount == 1

    def release_run_lease(self, run_id: str, lease_id: str) -> bool:
        """Release only a lease owned by this runner; a newer owner is untouched."""
        now = datetime.now(timezone.utc)
        with self.database.transaction(immediate=True) as conn:
            row = conn.execute("SELECT status, payload FROM novel_video_runs WHERE id = ?", (run_id,)).fetchone()
            if row is None:
                return False
            run = ProductionRun.model_validate_json(row["payload"])
            if run.lease_id != lease_id:
                return False
            updated = run.model_copy(update={"lease_id": None, "lease_expires_at": None, "updated_at": now})
            cursor = conn.execute(
                """UPDATE novel_video_runs SET lease_id = NULL, lease_expires_at = NULL, payload = ?, updated_at = ?
                   WHERE id = ? AND status = ? AND lease_id = ?""",
                (updated.model_dump_json(), now.isoformat(), run_id, row["status"], lease_id),
            )
        return cursor.rowcount == 1

    def update_run_status(self, run_id: str, status: RunStatus) -> ProductionRun:
        with self.database.transaction(immediate=True) as conn:
            row = conn.execute(
                "SELECT status, payload FROM novel_video_runs WHERE id = ?", (run_id,)
            ).fetchone()
            if row is None:
                raise KeyError(f"run {run_id} does not exist")
            current = RunStatus(row["status"])
            transition_run(current, status)
            run = ProductionRun.model_validate_json(row["payload"])
            updated = run.model_copy(
                update={"status": status, "updated_at": datetime.now(timezone.utc)}
            )
            self._update_run_row(conn, updated, current)
        return updated

    def save_shot(self, shot: ShotRecord) -> ShotRecord:
        with self.database.transaction(immediate=True) as conn:
            row = conn.execute(
                "SELECT status FROM novel_video_shots WHERE id = ?", (shot.id,)
            ).fetchone()
            if row is None:
                if shot.status is not ShotStatus.DRAFT:
                    raise InvalidTransition("new shot must start in draft")
                conn.execute(
                    """INSERT INTO novel_video_shots
                       (id, run_id, sequence, status, payload, updated_at)
                       VALUES (?, ?, ?, ?, ?, ?)""",
                    self._shot_parameters(shot),
                )
            else:
                current = ShotStatus(row["status"])
                transition_shot(current, shot.status)
                self._update_shot_row(conn, shot, current)
        return shot

    def get_shot(self, shot_id: str) -> ShotRecord | None:
        row = self._fetch_one("SELECT payload FROM novel_video_shots WHERE id = ?", (shot_id,))
        return ShotRecord.model_validate_json(row["payload"]) if row else None

    def list_shots(self, run_id: str) -> list[ShotRecord]:
        with self.database.connect() as conn:
            rows = conn.execute(
                "SELECT payload FROM novel_video_shots WHERE run_id = ? ORDER BY sequence", (run_id,)
            ).fetchall()
        return [ShotRecord.model_validate_json(row["payload"]) for row in rows]

    def update_shot_status(self, shot_id: str, status: ShotStatus) -> ShotRecord:
        with self.database.transaction(immediate=True) as conn:
            row = conn.execute(
                "SELECT status, payload FROM novel_video_shots WHERE id = ?", (shot_id,)
            ).fetchone()
            if row is None:
                raise KeyError(f"shot {shot_id} does not exist")
            current = ShotStatus(row["status"])
            transition_shot(current, status)
            shot = ShotRecord.model_validate_json(row["payload"])
            updated = shot.model_copy(
                update={"status": status, "updated_at": datetime.now(timezone.utc)}
            )
            self._update_shot_row(conn, updated, current)
        return updated

    def append_asset(self, asset: AssetVersion) -> AssetVersion:
        if not asset.path.is_file() or asset.path.stat().st_size == 0:
            raise ValueError("asset file is missing or empty")
        actual_sha256 = _sha256_file(asset.path)
        if actual_sha256 != asset.sha256:
            raise ValueError("asset SHA-256 does not match the file")
        with self.database.transaction(immediate=True) as conn:
            self._validate_asset_ownership(conn, asset)
            if conn.execute("SELECT 1 FROM novel_video_assets WHERE id = ?", (asset.id,)).fetchone():
                raise ValueError(f"asset {asset.id} already exists")
            if conn.execute(
                "SELECT 1 FROM novel_video_assets WHERE path = ?", (str(asset.path),)
            ).fetchone():
                raise ValueError(f"asset path {asset.path} is already registered")
            conn.execute(
                """INSERT INTO novel_video_assets
                   (id, project_id, run_id, shot_id, parent_id, kind, state, path, sha256, payload, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (asset.id, asset.project_id, asset.run_id, asset.shot_id, asset.parent_id, asset.kind, asset.state, str(asset.path), asset.sha256, asset.model_dump_json(), asset.created_at.isoformat()),
            )
        return asset

    def register_source_asset(self, asset: AssetVersion) -> AssetVersion:
        """Atomically adopt one immutable imported source and update its project.

        Replays return the original registered source; a concurrent importer
        cannot add another row for the same project/path/hash.
        """
        if asset.kind != "novel_source" or asset.state != "approved":
            raise ValueError("source registration requires an approved novel_source asset")
        if not asset.path.is_file() or _sha256_file(asset.path) != asset.sha256:
            raise ValueError("source asset file or SHA-256 does not verify")
        with self.database.transaction(immediate=True) as conn:
            self._validate_asset_ownership(conn, asset)
            rows = conn.execute(
                "SELECT payload FROM novel_video_assets WHERE project_id = ? AND kind = ? AND sha256 = ?",
                (asset.project_id, "novel_source", asset.sha256),
            ).fetchall()
            matches = [AssetVersion.model_validate_json(row["payload"]) for row in rows]
            if matches:
                exact = [item for item in matches if item.path == asset.path]
                if not exact:
                    raise ValueError("same source hash is already registered at another immutable path")
                registered = exact[0]
            else:
                if conn.execute("SELECT 1 FROM novel_video_assets WHERE id = ?", (asset.id,)).fetchone():
                    raise ValueError(f"asset {asset.id} already exists")
                if conn.execute("SELECT 1 FROM novel_video_assets WHERE path = ?", (str(asset.path),)).fetchone():
                    raise ValueError(f"asset path {asset.path} is already registered")
                conn.execute(
                    """INSERT INTO novel_video_assets
                       (id, project_id, run_id, shot_id, parent_id, kind, state, path, sha256, payload, created_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (asset.id, asset.project_id, asset.run_id, asset.shot_id, asset.parent_id, asset.kind, asset.state, str(asset.path), asset.sha256, asset.model_dump_json(), asset.created_at.isoformat()),
                )
                registered = asset
            project_row = conn.execute("SELECT payload FROM novel_video_projects WHERE id = ?", (asset.project_id,)).fetchone()
            project = NovelVideoProject.model_validate_json(project_row["payload"])
            if project.source_asset_version_id != registered.id:
                project = project.model_copy(update={"source_asset_version_id": registered.id, "updated_at": datetime.now(timezone.utc)})
                conn.execute(
                    "UPDATE novel_video_projects SET payload = ?, updated_at = ? WHERE id = ?",
                    (project.model_dump_json(), project.updated_at.isoformat(), project.id),
                )
        return registered

    def get_asset(self, asset_id: str) -> AssetVersion | None:
        row = self._fetch_one("SELECT payload FROM novel_video_assets WHERE id = ?", (asset_id,))
        return AssetVersion.model_validate_json(row["payload"]) if row else None

    def list_assets(self, run_id: str, *, state: str | None = None) -> list[AssetVersion]:
        query = "SELECT payload FROM novel_video_assets WHERE run_id = ?"
        parameters: tuple[str, ...] = (run_id,)
        if state is not None:
            query += " AND state = ?"
            parameters = (run_id, state)
        query += " ORDER BY created_at, id"
        with self.database.connect() as conn:
            rows = conn.execute(query, parameters).fetchall()
        return [AssetVersion.model_validate_json(row["payload"]) for row in rows]

    def list_assets_for_project(self, project_id: str) -> list[AssetVersion]:
        with self.database.connect() as conn:
            rows = conn.execute(
                "SELECT payload FROM novel_video_assets WHERE project_id = ? ORDER BY created_at, id",
                (project_id,),
            ).fetchall()
        return [AssetVersion.model_validate_json(row["payload"]) for row in rows]

    def save_chapter_plan(
        self, project_id: str, bundle: ChapterPlanBundle, *, source_asset_id: str
    ) -> ChapterPlanBundle:
        if not bundle.plan_id or not bundle.source_asset_version_id:
            raise ValueError("chapter plans require plan_id and source_asset_version_id")
        if bundle.source_asset_version_id != source_asset_id:
            raise ValueError("chapter plan source asset does not match persistence request")
        selection_key = _chapter_selection_key(bundle.chapter_indexes)
        payload = _chapter_plan_payload(bundle)
        encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        with self.database.transaction(immediate=True) as conn:
            row = conn.execute(
                "SELECT payload FROM novel_video_chapter_plan_versions WHERE plan_id = ?",
                (bundle.plan_id,),
            ).fetchone()
            if row is None:
                conn.execute(
                    """INSERT INTO novel_video_chapter_plan_versions
                       (plan_id, project_id, source_asset_id, source_sha256, selection_key, target_seconds, max_shots, payload, created_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (bundle.plan_id, project_id, source_asset_id, bundle.source_sha256, selection_key, bundle.target_seconds, bundle.max_shots, encoded, datetime.now(timezone.utc).isoformat()),
                )
            elif row["payload"] != encoded:
                raise ValueError("chapter plan id already has an immutable different payload")
        return bundle

    def get_chapter_plan(
        self, project_id: str, chapter_indexes: list[int] | tuple[int, ...], *,
        source_asset_id: str | None = None, target_seconds: float | None = None,
        max_shots: int | None = None, plan_id: str | None = None,
    ) -> ChapterPlanBundle | None:
        if plan_id:
            row = self._fetch_one("SELECT payload FROM novel_video_chapter_plan_versions WHERE plan_id = ? AND project_id = ?", (plan_id, project_id))
        else:
            selection_key = _chapter_selection_key(chapter_indexes)
            query = "SELECT payload FROM novel_video_chapter_plan_versions WHERE project_id = ? AND selection_key = ?"
            parameters: list[object] = [project_id, selection_key]
            if source_asset_id is not None:
                query += " AND source_asset_id = ?"
                parameters.append(source_asset_id)
            if target_seconds is not None:
                query += " AND target_seconds = ?"
                parameters.append(target_seconds)
            if max_shots is not None:
                query += " AND max_shots = ?"
                parameters.append(max_shots)
            query += " ORDER BY created_at DESC LIMIT 1"
            with self.database.connect() as conn:
                row = conn.execute(query, tuple(parameters)).fetchone()
        return _chapter_plan_from_payload(json.loads(row["payload"])) if row else None

    def approve_candidate_asset(self, candidate_id: str, approved: AssetVersion) -> AssetVersion:
        """Atomically freeze a candidate and update all real project descendants."""
        with self.database.transaction(immediate=True) as conn:
            candidate_row = conn.execute("SELECT payload FROM novel_video_assets WHERE id = ?", (candidate_id,)).fetchone()
            if candidate_row is None:
                raise KeyError(f"asset {candidate_id} does not exist")
            candidate = AssetVersion.model_validate_json(candidate_row["payload"])
            if candidate.state != "candidate":
                raise ValueError("only candidate assets may be approved")
            if not candidate.path.is_file() or _sha256_file(candidate.path) != candidate.sha256:
                raise ValueError("candidate asset file or SHA-256 no longer verifies")
            if (approved.parent_id != candidate.id or approved.project_id != candidate.project_id
                    or approved.run_id != candidate.run_id or approved.shot_id != candidate.shot_id
                    or approved.kind != candidate.kind or approved.state != "approved"):
                raise ValueError("approved asset does not preserve candidate ownership")
            self._validate_asset_ownership(conn, candidate)
            self._validate_asset_ownership(conn, approved)
            if not approved.path.is_file() or _sha256_file(approved.path) != approved.sha256:
                raise ValueError("approved asset file or SHA-256 does not verify")
            existing_rows = conn.execute(
                "SELECT payload FROM novel_video_assets WHERE parent_id = ? AND state = ?", (candidate.id, "approved")
            ).fetchall()
            existing = [AssetVersion.model_validate_json(row["payload"]) for row in existing_rows]
            if existing:
                if len(existing) != 1 or existing[0].kind != approved.kind or existing[0].sha256 != approved.sha256 or existing[0].path != approved.path:
                    raise ValueError("candidate already has a different approved immutable version")
                frozen = existing[0]
            else:
                if conn.execute("SELECT 1 FROM novel_video_assets WHERE id = ?", (approved.id,)).fetchone():
                    raise ValueError(f"asset {approved.id} already exists")
                if conn.execute("SELECT 1 FROM novel_video_assets WHERE path = ?", (str(approved.path),)).fetchone():
                    raise ValueError(f"asset path {approved.path} is already registered")
                conn.execute(
                    """INSERT INTO novel_video_assets
                       (id, project_id, run_id, shot_id, parent_id, kind, state, path, sha256, payload, created_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (approved.id, approved.project_id, approved.run_id, approved.shot_id, approved.parent_id, approved.kind, approved.state, str(approved.path), approved.sha256, approved.model_dump_json(), approved.created_at.isoformat()),
                )
                frozen = approved
            shot_row = conn.execute("SELECT status, payload FROM novel_video_shots WHERE id = ? AND run_id = ?", (candidate.shot_id, candidate.run_id)).fetchone()
            shot = ShotRecord.model_validate_json(shot_row["payload"])
            pointer_key = "approved_tail_asset_id" if candidate.kind == "tail" else "approved_video_asset_id"
            replaced = getattr(shot, pointer_key)
            if replaced != frozen.id:
                updated = shot.model_copy(update={pointer_key: frozen.id, "updated_at": datetime.now(timezone.utc)})
                self._update_shot_row(conn, updated, ShotStatus(shot_row["status"]))
            if replaced and replaced != frozen.id:
                self._clear_project_reference_descendants(conn, candidate.project_id, replaced)
        return frozen

    def append_event(self, event: RunEvent) -> RunEvent:
        payload_bytes = len(event.model_dump_json().encode("utf-8"))
        if payload_bytes > MAX_EVENT_PAYLOAD_BYTES:
            raise ValueError("formal event payload exceeds the maximum size")
        with self.database.transaction(immediate=True) as conn:
            cursor = conn.execute(
                "INSERT INTO novel_video_events (run_id, event_type, payload, created_at) VALUES (?, ?, ?, ?)",
                (event.run_id, event.event_type, event.model_dump_json(), event.created_at.isoformat()),
            )
        return event.model_copy(update={"sequence": cursor.lastrowid})

    def validate_shot_candidate_decision(
        self, *, run_id: str, shot_id: str, candidate_video_id: str,
        candidate_tail_id: str, binding: dict[str, str], qa: dict[str, Any],
        expected_lease_id: str | None, task_id: str, task_result: dict[str, Any],
        generation_identity: dict[str, str] | None = None,
    ) -> tuple[ProductionRun, ShotRecord, AssetVersion, AssetVersion]:
        """Fence and authenticate a candidate pair without making it approved.

        This short ``BEGIN IMMEDIATE`` transaction is used immediately before
        filesystem publication.  The final transaction repeats every check;
        this first fence prevents knowingly publishing after pause/cancel or a
        scheduler lease loss.
        """
        with self.database.transaction(immediate=True) as conn:
            return self._validate_shot_candidate_decision(
                conn, run_id=run_id, shot_id=shot_id,
                candidate_video_id=candidate_video_id,
                candidate_tail_id=candidate_tail_id, binding=binding, qa=qa,
                expected_lease_id=expected_lease_id, task_id=task_id,
                task_result=task_result, generation_identity=generation_identity,
            )

    def get_shot_candidate_decision(self, transaction_token: str) -> dict[str, Any] | None:
        row = self._fetch_one(
            "SELECT payload FROM novel_video_shot_decisions WHERE transaction_token = ?",
            (transaction_token,),
        )
        return json.loads(row["payload"]) if row else None

    def get_shot_candidate_decision_for_shot(self, shot_id: str) -> dict[str, Any] | None:
        row = self._fetch_one(
            "SELECT payload FROM novel_video_shot_decisions WHERE shot_id = ?", (shot_id,),
        )
        return json.loads(row["payload"]) if row else None

    def commit_shot_candidate_decision(
        self, *, transaction_token: str, request_sha256: str, run_id: str,
        shot_id: str, candidate_video_id: str, candidate_tail_id: str,
        approved_video: AssetVersion, approved_tail: AssetVersion,
        binding: dict[str, str], qa: dict[str, Any],
        expected_lease_id: str | None, task_id: str,
        task_result: dict[str, Any], generation_identity: dict[str, str] | None = None,
    ) -> ShotRecord:
        """Commit the exact approved pair, shot and audit record once.

        Final files may already exist because filesystems and SQLite cannot
        share a transaction.  Their immutable paths and digests are verified
        inside this transaction before either approved row becomes visible.
        """
        with self.database.transaction(immediate=True) as conn:
            existing = conn.execute(
                "SELECT request_sha256, payload FROM novel_video_shot_decisions "
                "WHERE transaction_token = ? OR shot_id = ?",
                (transaction_token, shot_id),
            ).fetchall()
            if existing:
                if len(existing) != 1 or existing[0]["request_sha256"] != request_sha256:
                    raise ConcurrentTransitionError("shot already has a different approval decision")
                decision = json.loads(existing[0]["payload"])
                if decision.get("transaction_token") != transaction_token:
                    raise ConcurrentTransitionError("shot approval transaction token changed")
                shot_row = conn.execute(
                    "SELECT status, payload FROM novel_video_shots WHERE id = ? AND run_id = ?",
                    (shot_id, run_id),
                ).fetchone()
                if shot_row is None:
                    raise ValueError("committed decision shot is missing")
                shot = ShotRecord.model_validate_json(shot_row["payload"])
                if (ShotStatus(shot_row["status"]) is not ShotStatus.APPROVED
                        or shot.approved_video_asset_id != approved_video.id
                        or shot.approved_tail_asset_id != approved_tail.id
                        or decision.get("approved_video_id") != approved_video.id
                        or decision.get("approved_tail_id") != approved_tail.id
                        or decision.get("candidate_video_id") != candidate_video_id
                        or decision.get("candidate_tail_id") != candidate_tail_id
                        or decision.get("binding") != binding
                        or decision.get("task_id") != task_id):
                    raise ValueError("committed decision lineage or shot pointers do not verify")
                asset_rows = conn.execute(
                    "SELECT payload FROM novel_video_assets WHERE id IN (?, ?)",
                    (approved_video.id, approved_tail.id),
                ).fetchall()
                persisted = {AssetVersion.model_validate_json(row["payload"]).id:
                             AssetVersion.model_validate_json(row["payload"])
                             for row in asset_rows}
                for supplied in (approved_video, approved_tail):
                    frozen = persisted.get(supplied.id)
                    if (frozen is None
                            or any(getattr(frozen, key) != getattr(supplied, key) for key in (
                                "id", "project_id", "run_id", "shot_id", "parent_id",
                                "kind", "state", "path", "sha256", "metadata",
                            ))
                            or not frozen.path.is_file()
                            or _sha256_file(frozen.path) != frozen.sha256):
                        raise ValueError("committed decision approved file or asset does not verify")
                events = conn.execute(
                    "SELECT payload FROM novel_video_events WHERE run_id = ? AND event_type = ?",
                    (run_id, "shot_approved"),
                ).fetchall()
                exact = [json.loads(row["payload"]) for row in events
                         if json.loads(row["payload"]).get("payload", {}).get("decision_token") == transaction_token]
                if len(exact) != 1:
                    raise ValueError("committed decision audit event does not verify")
                return shot

            run, shot, candidate_video, candidate_tail = self._validate_shot_candidate_decision(
                conn, run_id=run_id, shot_id=shot_id,
                candidate_video_id=candidate_video_id,
                candidate_tail_id=candidate_tail_id, binding=binding, qa=qa,
                expected_lease_id=expected_lease_id, task_id=task_id,
                task_result=task_result, generation_identity=generation_identity,
            )
            expected_approved = (
                (approved_video, candidate_video, "video"),
                (approved_tail, candidate_tail, "tail"),
            )
            for approved, candidate, kind in expected_approved:
                if (approved.parent_id != candidate.id or approved.project_id != run.project_id
                        or approved.run_id != run_id or approved.shot_id != shot_id
                        or approved.kind != kind or approved.state != "approved"
                        or approved.sha256 != candidate.sha256):
                    raise ValueError("approved pair does not preserve exact candidate lineage")
                if (not approved.path.is_file()
                        or _sha256_file(approved.path) != approved.sha256):
                    raise ValueError("approved final file or digest does not verify")
                occupied = conn.execute(
                    "SELECT payload FROM novel_video_assets WHERE id = ? OR path = ?",
                    (approved.id, str(approved.path)),
                ).fetchall()
                if occupied:
                    raise ConcurrentTransitionError("approved id or path belongs to another record")
                self._validate_asset_ownership(conn, approved)
                conn.execute(
                    """INSERT INTO novel_video_assets
                       (id, project_id, run_id, shot_id, parent_id, kind, state,
                        path, sha256, payload, created_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (approved.id, approved.project_id, approved.run_id,
                     approved.shot_id, approved.parent_id, approved.kind,
                     approved.state, str(approved.path), approved.sha256,
                     approved.model_dump_json(), approved.created_at.isoformat()),
                )

            verified_qa = self._verified_visual_qa(
                conn, run, shot_id, qa, candidate_video, generation_identity,
            )
            updated = shot.model_copy(update={
                "status": ShotStatus.APPROVED,
                "approved_video_asset_id": approved_video.id,
                "approved_tail_asset_id": approved_tail.id,
                "updated_at": datetime.now(timezone.utc),
            })
            transition_shot(ShotStatus.VALIDATING, ShotStatus.APPROVED)
            self._update_shot_row(conn, updated, ShotStatus.VALIDATING)
            # Explicit human/GPT approval owns the review-gate transition. It
            # is committed beside the two pointers, so a crash cannot expose
            # an approved shot while the run remains stuck at that gate.
            if run.status is RunStatus.AWAITING_REVIEW:
                if run.review_gate != "shot_candidate" or expected_lease_id is not None:
                    raise ConcurrentTransitionError("shot approval review gate changed")
                resumed = run.model_copy(update={
                    "status": RunStatus.RENDERING, "review_gate": None,
                    "updated_at": datetime.now(timezone.utc),
                })
                transition_run(RunStatus.AWAITING_REVIEW, RunStatus.RENDERING)
                self._update_run_row(conn, resumed, RunStatus.AWAITING_REVIEW)
            decision = {
                "transaction_token": transaction_token,
                "request_sha256": request_sha256,
                "run_id": run_id, "shot_id": shot_id,
                "candidate_video_id": candidate_video_id,
                "candidate_tail_id": candidate_tail_id,
                "approved_video_id": approved_video.id,
                "approved_tail_id": approved_tail.id,
                "binding": binding, "qa": verified_qa,
                "task_id": task_id, "prompt_id": candidate_video.metadata.get("prompt_id"),
                "generation_identity": generation_identity or dict(candidate_video.metadata.get("generation_identity", {})),
            }
            event = RunEvent(
                run_id=run_id, event_type="shot_approved",
                payload={
                    "decision_token": transaction_token, "shot_id": shot_id,
                    "video_asset_id": approved_video.id,
                    "tail_asset_id": approved_tail.id,
                    "candidate_video_id": candidate_video_id,
                    "candidate_tail_id": candidate_tail_id,
                    "qa": verified_qa, "binding": binding, "task_id": task_id,
                    "generation_identity": generation_identity or dict(candidate_video.metadata.get("generation_identity", {})),
                },
            )
            conn.execute(
                "INSERT INTO novel_video_events (run_id, event_type, payload, created_at) VALUES (?, ?, ?, ?)",
                (run_id, event.event_type, event.model_dump_json(), event.created_at.isoformat()),
            )
            conn.execute(
                """INSERT INTO novel_video_shot_decisions
                   (transaction_token, run_id, shot_id, candidate_video_id,
                    candidate_tail_id, approved_video_id, approved_tail_id,
                    request_sha256, payload, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (transaction_token, run_id, shot_id, candidate_video_id,
                 candidate_tail_id, approved_video.id, approved_tail.id,
                 request_sha256, json.dumps(decision, ensure_ascii=False,
                                             sort_keys=True, separators=(",", ":")),
                 datetime.now(timezone.utc).isoformat()),
            )
        return updated

    def reject_shot_candidate_decision(
        self, *, run_id: str, shot_id: str, candidate_video_id: str,
        candidate_tail_id: str, binding: dict[str, str], task_id: str,
        task_result: dict[str, Any], generation_identity: dict[str, str] | None,
    ) -> ShotRecord:
        """Atomically requeue an exact validating pair and append one audit event."""
        with self.database.transaction(immediate=True) as conn:
            prior = [RunEvent.model_validate_json(row["payload"]) for row in conn.execute(
                "SELECT payload FROM novel_video_events WHERE run_id = ? AND event_type = ?",
                (run_id, "shot_candidate_rejected"),
            ).fetchall()]
            if any(event.payload.get("candidate_video_id") == candidate_video_id
                   and event.payload.get("candidate_tail_id") == candidate_tail_id for event in prior):
                existing = conn.execute("SELECT payload FROM novel_video_shots WHERE id = ?", (shot_id,)).fetchone()
                if existing is None:
                    raise ValueError("rejected shot is missing")
                return ShotRecord.model_validate_json(existing["payload"])
            run_row = conn.execute(
                "SELECT status, payload FROM novel_video_runs WHERE id = ?", (run_id,),
            ).fetchone()
            shot_row = conn.execute(
                "SELECT status, payload FROM novel_video_shots WHERE id = ? AND run_id = ?",
                (shot_id, run_id),
            ).fetchone()
            if run_row is None or shot_row is None:
                raise ValueError("run/shot ownership does not verify")
            run = ProductionRun.model_validate_json(run_row["payload"])
            if run.status is not RunStatus.AWAITING_REVIEW or run.review_gate != "shot_candidate":
                raise ConcurrentTransitionError("shot candidate is no longer awaiting review")
            if ShotStatus(shot_row["status"]) is not ShotStatus.VALIDATING:
                raise ConcurrentTransitionError("shot is no longer validating")
            assets = [AssetVersion.model_validate_json(row["payload"]) for row in conn.execute(
                "SELECT payload FROM novel_video_assets WHERE id IN (?, ?)",
                (candidate_video_id, candidate_tail_id),
            ).fetchall()]
            by_id = {asset.id: asset for asset in assets}
            video, tail = by_id.get(candidate_video_id), by_id.get(candidate_tail_id)
            if (video is None or tail is None or video.state != "candidate"
                    or tail.state != "candidate" or tail.parent_id != video.id
                    or video.shot_id != shot_id or tail.shot_id != shot_id):
                raise ValueError("rejected candidate pair does not verify")
            shot = ShotRecord.model_validate_json(shot_row["payload"])
            self._validate_candidate_task_audit(
                conn, run_id=run_id, shot_id=shot_id, video=video, tail=tail,
                binding=binding, task_id=task_id, task_result=task_result,
                generation_identity=generation_identity,
            )
            # Candidate versions remain immutable evidence but are no longer
            # eligible for a future approval.  A semantic nonce makes the
            # next task/output identity distinct even when prompt and seed
            # intentionally stay stable.
            for asset in (video, tail):
                rejected = asset.model_copy(update={"state": "rejected"})
                cursor = conn.execute(
                    "UPDATE novel_video_assets SET state = ?, payload = ? WHERE id = ? AND state = ?",
                    ("rejected", rejected.model_dump_json(), asset.id, "candidate"),
                )
                if cursor.rowcount != 1:
                    raise ConcurrentTransitionError("candidate rejection changed concurrently")
            queued = shot.model_copy(update={
                "status": ShotStatus.QUEUED, "retry_nonce": shot.retry_nonce + 1,
                "updated_at": datetime.now(timezone.utc),
            })
            # Validate both logical edges, then persist only the final state.
            transition_shot(ShotStatus.VALIDATING, ShotStatus.FAILED)
            transition_shot(ShotStatus.FAILED, ShotStatus.QUEUED)
            self._update_shot_row(conn, queued, ShotStatus.VALIDATING)
            resumed = run.model_copy(update={
                "status": RunStatus.RENDERING, "review_gate": None,
                "updated_at": datetime.now(timezone.utc),
            })
            transition_run(RunStatus.AWAITING_REVIEW, RunStatus.RENDERING)
            self._update_run_row(conn, resumed, RunStatus.AWAITING_REVIEW)
            event = RunEvent(
                run_id=run_id, event_type="shot_candidate_rejected",
                payload={"shot_id": shot_id, "candidate_video_id": candidate_video_id,
                         "candidate_tail_id": candidate_tail_id,
                         "retry_nonce": queued.retry_nonce},
            )
            conn.execute(
                "INSERT INTO novel_video_events (run_id, event_type, payload, created_at) VALUES (?, ?, ?, ?)",
                (run_id, event.event_type, event.model_dump_json(), event.created_at.isoformat()),
            )
        return queued

    def _validate_shot_candidate_decision(
        self, conn, *, run_id: str, shot_id: str, candidate_video_id: str,
        candidate_tail_id: str, binding: dict[str, str], qa: dict[str, Any],
        expected_lease_id: str | None, task_id: str, task_result: dict[str, Any],
        generation_identity: dict[str, str] | None = None,
    ) -> tuple[ProductionRun, ShotRecord, AssetVersion, AssetVersion]:
        run_row = conn.execute(
            "SELECT status, payload FROM novel_video_runs WHERE id = ?", (run_id,),
        ).fetchone()
        shot_row = conn.execute(
            "SELECT status, payload FROM novel_video_shots WHERE id = ? AND run_id = ?",
            (shot_id, run_id),
        ).fetchone()
        if run_row is None or shot_row is None:
            raise ValueError("run/shot ownership does not verify")
        run = ProductionRun.model_validate_json(run_row["payload"])
        shot = ShotRecord.model_validate_json(shot_row["payload"])
        now = datetime.now(timezone.utc)
        lease_live = (expected_lease_id is None or
                      (run.lease_id == expected_lease_id and run.lease_expires_at is not None
                       and run.lease_expires_at > now))
        owner_ok = run.status is RunStatus.RENDERING and run.lease_id == expected_lease_id and lease_live
        review_ok = (run.status is RunStatus.AWAITING_REVIEW
                     and run.review_gate == "shot_candidate"
                     and expected_lease_id is None)
        if not (owner_ok or review_ok):
            raise ConcurrentTransitionError("run pause/cancel/lease fence changed")
        if ShotStatus(shot_row["status"]) is not ShotStatus.VALIDATING:
            raise ConcurrentTransitionError("shot is no longer validating")
        if shot.reference_package is None:
            raise ValueError("shot has no immutable H3 reference package")
        package_sha256 = sha256(json.dumps(
            shot.reference_package.model_dump(mode="json"), ensure_ascii=False,
            sort_keys=True, separators=(",", ":"),
        ).encode()).hexdigest()
        if binding != {"run_id": run_id, "shot_id": shot_id,
                       "package_sha256": package_sha256}:
            raise ValueError("decision package binding is stale")
        rows = conn.execute(
            "SELECT payload FROM novel_video_assets WHERE id IN (?, ?)",
            (candidate_video_id, candidate_tail_id),
        ).fetchall()
        assets = {AssetVersion.model_validate_json(row["payload"]).id:
                  AssetVersion.model_validate_json(row["payload"]) for row in rows}
        video, tail = assets.get(candidate_video_id), assets.get(candidate_tail_id)
        if (video is None or tail is None or video.kind != "video" or tail.kind != "tail"
                or video.state != "candidate" or tail.state != "candidate"
                or tail.parent_id != video.id or video.project_id != run.project_id
                or tail.project_id != run.project_id or video.run_id != run_id
                or tail.run_id != run_id or video.shot_id != shot_id
                or tail.shot_id != shot_id):
            raise ValueError("candidate video/tail lineage does not verify")
        asset_identity = dict(video.metadata.get("generation_identity", {}))
        if generation_identity is not None:
            if asset_identity != generation_identity or task_result.get("generation_identity") != generation_identity:
                raise ValueError("candidate full generation identity is stale")
            if {key: generation_identity.get(key) for key in ("run_id", "shot_id", "package_sha256")} != binding:
                raise ValueError("candidate generation identity package binding is stale")
        elif asset_identity != binding:
            raise ValueError("candidate generation/package binding is stale")
        prompt_id = video.metadata.get("prompt_id")
        if (not task_id or not isinstance(prompt_id, str) or not prompt_id
                or task_result.get("video_asset_id") != video.id
                or task_result.get("tail_asset_id") != tail.id
                or task_result.get("prompt_id") != prompt_id):
            raise ValueError("task result does not identify the exact candidate pair and prompt")
        self._validate_candidate_task_audit(
            conn, run_id=run_id, shot_id=shot_id, video=video, tail=tail,
            binding=binding, task_id=task_id, task_result=task_result,
            generation_identity=generation_identity,
        )
        # Candidate bytes are captured and hashed exactly once by the service
        # into destination-local private stages.  Reopening the mutable source
        # paths here would create a second, different authority and a TOCTOU
        # window; this transaction authenticates the unchanged immutable DB
        # records while the service authenticates staged/final bytes.
        self._verified_visual_qa(conn, run, shot_id, qa, video, generation_identity)
        return run, shot, video, tail

    @staticmethod
    def _validate_candidate_task_audit(conn, *, run_id: str, shot_id: str,
                                       video: AssetVersion, tail: AssetVersion,
                                       binding: dict[str, str], task_id: str,
                                       task_result: dict[str, Any],
                                       generation_identity: dict[str, str] | None) -> None:
        prompt_id = video.metadata.get("prompt_id")
        if (not task_id or not isinstance(prompt_id, str) or not prompt_id
                or task_result.get("video_asset_id") != video.id
                or task_result.get("tail_asset_id") != tail.id
                or task_result.get("prompt_id") != prompt_id):
            raise ValueError("task result does not identify the exact candidate pair and prompt")
        events = [RunEvent.model_validate_json(row["payload"]) for row in conn.execute(
            "SELECT payload FROM novel_video_events WHERE run_id = ?", (run_id,),
        ).fetchall()]
        enqueued = [event for event in events if event.event_type == "formal_task_enqueued"
                    and event.payload.get("shot_id") == shot_id
                    and event.payload.get("task_id") == task_id
                    and event.payload.get("binding") == binding
                    and (generation_identity is None or event.payload.get("generation_identity") == generation_identity)]
        succeeded = [event for event in events if event.event_type == "video_generation_succeeded"
                     and event.payload.get("shot_id") == shot_id
                     and event.payload.get("video_asset_id") == video.id
                     and event.payload.get("tail_asset_id") == tail.id
                     and event.payload.get("prompt_id") == prompt_id
                     and event.payload.get("generation_identity") == (generation_identity or binding)]
        if len(enqueued) != 1 or len(succeeded) != 1:
            raise ValueError("candidate task/prompt audit binding does not verify exactly once")

    @staticmethod
    def _verified_visual_qa(conn, run: ProductionRun, shot_id: str,
                            qa: dict[str, Any], video: AssetVersion,
                            generation_identity: dict[str, str] | None) -> dict[str, Any]:
        evidence_ids = qa.get("evidence_asset_ids")
        if (not isinstance(evidence_ids, list) or not evidence_ids
                or len(set(evidence_ids)) != len(evidence_ids)
                or not qa.get("reviewer") or not qa.get("version") or not qa.get("reason")):
            raise ValueError("visual QA decision needs unique evidence, reviewer, version and reason")
        if not isinstance(qa.get("score"), (int, float)) or not 0 <= float(qa["score"]) <= 1:
            raise ValueError("visual QA score must be within zero and one")
        placeholders = ",".join("?" for _ in evidence_ids)
        rows = conn.execute(
            f"SELECT payload FROM novel_video_assets WHERE id IN ({placeholders})",
            tuple(evidence_ids),
        ).fetchall()
        evidence = [AssetVersion.model_validate_json(row["payload"]) for row in rows]
        if (len(evidence) != len(evidence_ids)
                or any(item.kind != "qa_evidence" or item.project_id != run.project_id or item.run_id != run.id
                       or item.shot_id != shot_id or item.state != "approved"
                       or (generation_identity is not None and (item.parent_id != video.id and item.metadata.get("candidate_video_asset_id") != video.id))
                       or (generation_identity is not None and dict(item.metadata.get("generation_identity", {})) != generation_identity)
                       or not item.path.is_file() or _sha256_file(item.path) != item.sha256
                       for item in evidence)):
            raise ValueError("visual QA evidence assets do not verify")
        return {**qa, "evidence_sha256": {item.id: item.sha256 for item in evidence}}

    def close(self) -> None:
        """Release the repository-owned SQLite connection once per lifespan."""
        close = getattr(self.database, "close", None)
        if callable(close):
            close()

    def block_generation_failure(
        self, run_id: str, *, shot_id: str | None, evidence: dict[str, Any]
    ) -> ProductionRun:
        """Atomically block a formal generation run and preserve one idempotent failure event."""
        failure_key = str(evidence.get("failure_key") or "")
        if not failure_key:
            raise ValueError("generation failure evidence requires failure_key")
        with self.database.transaction(immediate=True) as conn:
            run_row = conn.execute(
                "SELECT status, payload FROM novel_video_runs WHERE id = ?", (run_id,)
            ).fetchone()
            if run_row is None:
                raise KeyError(f"run {run_id} does not exist")
            current_run_status = RunStatus(run_row["status"])
            run = ProductionRun.model_validate_json(run_row["payload"])
            if current_run_status is not RunStatus.BLOCKED:
                transition_run(current_run_status, RunStatus.BLOCKED)
                run = run.model_copy(update={"status": RunStatus.BLOCKED, "updated_at": datetime.now(timezone.utc)})
                self._update_run_row(conn, run, current_run_status)
            if shot_id:
                shot_row = conn.execute(
                    "SELECT run_id, status, payload FROM novel_video_shots WHERE id = ?", (shot_id,)
                ).fetchone()
                if shot_row is None:
                    raise KeyError(f"shot {shot_id} does not exist")
                if shot_row["run_id"] != run_id:
                    raise ValueError(f"shot {shot_id} is not owned by run {run_id}")
                current_shot_status = ShotStatus(shot_row["status"])
                if current_shot_status is not ShotStatus.BLOCKED:
                    transition_shot(current_shot_status, ShotStatus.BLOCKED)
                    shot = ShotRecord.model_validate_json(shot_row["payload"]).model_copy(
                        update={"status": ShotStatus.BLOCKED, "updated_at": datetime.now(timezone.utc)}
                    )
                    self._update_shot_row(conn, shot, current_shot_status)
            rows = conn.execute(
                "SELECT payload FROM novel_video_events WHERE run_id = ? AND event_type = ?",
                (run_id, "video_generation_blocked"),
            ).fetchall()
            if not any(json.loads(row["payload"]).get("payload", {}).get("failure_key") == failure_key for row in rows):
                event = RunEvent(run_id=run_id, event_type="video_generation_blocked", payload=evidence)
                conn.execute(
                    "INSERT INTO novel_video_events (run_id, event_type, payload, created_at) VALUES (?, ?, ?, ?)",
                    (run_id, event.event_type, event.model_dump_json(), event.created_at.isoformat()),
                )
        return run

    def record_generation_success(
        self, run_id: str, *, shot_id: str, video_path: Path, tail_path: Path,
        prompt_id: str, metadata: dict[str, Any], generation_identity: dict[str, str] | None = None,
    ) -> tuple[AssetVersion, AssetVersion]:
        """Atomically register immutable candidate pair and a durable formal generation checkpoint."""
        if not video_path.is_file() or not tail_path.is_file():
            raise ValueError("formal generation outputs must exist before writeback")
        video_digest, tail_digest = _sha256_file(video_path), _sha256_file(tail_path)
        with self.database.transaction(immediate=True) as conn:
            run_row = conn.execute("SELECT status, payload FROM novel_video_runs WHERE id = ?", (run_id,)).fetchone()
            shot_row = conn.execute("SELECT status, payload FROM novel_video_shots WHERE id = ? AND run_id = ?", (shot_id, run_id)).fetchone()
            if run_row is None or shot_row is None:
                raise ValueError("formal generation run/shot ownership is invalid")
            run = ProductionRun.model_validate_json(run_row["payload"])
            shot = ShotRecord.model_validate_json(shot_row["payload"])
            if run.status in {RunStatus.BLOCKED, RunStatus.COMPLETED, RunStatus.CANCELLED}:
                raise ValueError(f"formal generation run cannot accept success in {run.status.value}")
            existing = [AssetVersion.model_validate_json(row["payload"]) for row in conn.execute(
                "SELECT payload FROM novel_video_assets WHERE run_id = ? AND shot_id = ?", (run_id, shot_id)
            ).fetchall()]
            videos = [asset for asset in existing if asset.kind == "video" and asset.path == video_path]
            if videos:
                video = videos[0]
                tails = [asset for asset in existing if asset.kind == "tail" and asset.parent_id == video.id and asset.path == tail_path]
                identity_matches = generation_identity is None or dict(video.metadata.get("generation_identity", {})) == generation_identity
                if video.sha256 == video_digest and tails and tails[0].sha256 == tail_digest and video.metadata.get("prompt_id") == prompt_id and identity_matches:
                    return video, tails[0]
                raise ValueError("formal success replay conflicts with an existing candidate pair")
            if ShotStatus(shot_row["status"]) is not ShotStatus.RUNNING:
                raise ValueError("formal generation success requires a running shot")
            project_id = run.project_id
            video_asset = AssetVersion(
                id=f"video-{uuid.uuid4().hex}", project_id=project_id, run_id=run_id, shot_id=shot_id,
                kind="video", state="candidate", path=video_path, sha256=video_digest,
                metadata={"prompt_id": prompt_id, "media": metadata.get("media", {}), "models": metadata.get("models", {}), "recovery": metadata.get("recovery", {}), "generation_identity": generation_identity or {}},
            )
            tail_asset = AssetVersion(
                id=f"tail-{uuid.uuid4().hex}", project_id=project_id, run_id=run_id, shot_id=shot_id,
                parent_id=video_asset.id, kind="tail", state="candidate", path=tail_path, sha256=tail_digest,
                metadata={"prompt_id": prompt_id, "parent_video": video_asset.id},
            )
            for asset in (video_asset, tail_asset):
                self._validate_asset_ownership(conn, asset)
                conn.execute(
                    "INSERT INTO novel_video_assets (id, project_id, run_id, shot_id, parent_id, kind, state, path, sha256, payload, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (asset.id, asset.project_id, asset.run_id, asset.shot_id, asset.parent_id, asset.kind, asset.state, str(asset.path), asset.sha256, asset.model_dump_json(), asset.created_at.isoformat()),
                )
            event = RunEvent(run_id=run_id, event_type="video_generation_succeeded", payload={
                "shot_id": shot_id, "prompt_id": prompt_id, "video_asset_id": video_asset.id, "tail_asset_id": tail_asset.id,
                "media": metadata.get("media", {}), "models": metadata.get("models", {}), "recovery": metadata.get("recovery", {}),
                "generation_identity": generation_identity or {},
            })
            conn.execute("INSERT INTO novel_video_events (run_id, event_type, payload, created_at) VALUES (?, ?, ?, ?)",
                         (run_id, event.event_type, event.model_dump_json(), event.created_at.isoformat()))
            # Resolve this shot's checkpoint only; a future shot must never
            # inherit a prior prompt id.  Candidate media awaits explicit QA.
            settings = dict(run.settings)
            checkpoints = dict(settings.get("formal_prompt_checkpoints", {}))
            checkpoints.pop(shot_id, None)
            settings["formal_prompt_checkpoints"] = checkpoints
            current_run = RunStatus(run_row["status"])
            updated_run = run.model_copy(update={
                "settings": settings,
                "comfy_prompt_id": None if run.comfy_prompt_id == prompt_id else run.comfy_prompt_id,
                "updated_at": datetime.now(timezone.utc),
            })
            self._update_run_row(conn, updated_run, current_run)
            current_shot = ShotStatus(shot_row["status"])
            updated_shot = shot.model_copy(update={"status": ShotStatus.VALIDATING, "current_attempt": shot.current_attempt + 1, "updated_at": datetime.now(timezone.utc)})
            transition_shot(current_shot, ShotStatus.VALIDATING)
            self._update_shot_row(conn, updated_shot, current_shot)
        return video_asset, tail_asset

    def find_generation_success(
        self, run_id: str, *, shot_id: str, generation_identity: dict[str, str],
        video_path: Path, tail_path: Path,
    ) -> tuple[AssetVersion, AssetVersion] | None:
        """Authenticate an exact already-committed formal attempt after queue-only crash.

        This is intentionally stricter than path reuse: identity, paired
        lineage, success event, path and current file digests must all agree.
        """
        with self.database.connect() as conn:
            assets = [AssetVersion.model_validate_json(row["payload"]) for row in conn.execute(
                "SELECT payload FROM novel_video_assets WHERE run_id = ? AND shot_id = ?",
                (run_id, shot_id),
            ).fetchall()]
            event_rows = conn.execute(
                "SELECT payload FROM novel_video_events WHERE run_id = ? AND event_type = ?",
                (run_id, "video_generation_succeeded"),
            ).fetchall()
        videos = [
            asset for asset in assets
            if asset.kind == "video"
            and asset.path.resolve() == video_path.resolve()
            and dict(asset.metadata.get("generation_identity", {})) == generation_identity
        ]
        matches: list[tuple[AssetVersion, AssetVersion]] = []
        for video in videos:
            tails = [
                asset for asset in assets
                if asset.kind == "tail" and asset.parent_id == video.id
                and asset.path.resolve() == tail_path.resolve()
            ]
            for tail in tails:
                events = [RunEvent.model_validate_json(row["payload"]) for row in event_rows]
                exact_events = [
                    event for event in events
                    if event.payload.get("video_asset_id") == video.id
                    and event.payload.get("tail_asset_id") == tail.id
                    and dict(event.payload.get("generation_identity", {})) == generation_identity
                ]
                if len(exact_events) == 1:
                    matches.append((video, tail))
        if len(matches) > 1:
            raise ValueError("formal generation identity resolves to multiple successful pairs")
        if not matches:
            return None
        video, tail = matches[0]
        if not video.path.is_file() or not tail.path.is_file():
            raise ValueError("committed formal success is missing its paired files")
        if _sha256_file(video.path) != video.sha256 or _sha256_file(tail.path) != tail.sha256:
            raise ValueError("committed formal success digest mismatch")
        return video, tail

    def record_generation_prompt(self, run_id: str, *, shot_id: str, prompt_id: str, checkpoint: dict[str, Any] | None = None) -> ProductionRun:
        """Durably checkpoint an accepted Comfy prompt before history polling.

        The transaction is intentionally idempotent: a callback replay may
        repeat the same prompt id, but a different id for one unresolved run
        is a safety violation rather than a second generation attempt.
        """
        canonical = _validated_generation_checkpoint(checkpoint, run_id=run_id, shot_id=shot_id)
        with self.database.transaction(immediate=True) as conn:
            run_row = conn.execute(
                "SELECT status, payload FROM novel_video_runs WHERE id = ?", (run_id,)
            ).fetchone()
            shot_row = conn.execute(
                "SELECT run_id FROM novel_video_shots WHERE id = ?", (shot_id,)
            ).fetchone()
            if run_row is None or shot_row is None or shot_row["run_id"] != run_id:
                raise ValueError("formal prompt run/shot ownership is invalid")
            run = ProductionRun.model_validate_json(run_row["payload"])
            if run.status in {RunStatus.BLOCKED, RunStatus.COMPLETED, RunStatus.CANCELLED}:
                raise ValueError(f"terminal formal run cannot accept prompt: {run.status.value}")
            settings = dict(run.settings)
            checkpoints = dict(settings.get("formal_prompt_checkpoints", {}))
            active = checkpoints.get(shot_id)
            if active and active.get("prompt_id") != prompt_id:
                raise ConcurrentTransitionError(
                    f"shot {shot_id} already owns unresolved prompt {active.get('prompt_id')}"
                )
            if active and active != {**canonical, "prompt_id": prompt_id}:
                raise ConcurrentTransitionError(f"shot {shot_id} prompt checkpoint binding changed during replay")
            other_active = [key for key, value in checkpoints.items() if key != shot_id and value.get("prompt_id")]
            if other_active:
                raise ConcurrentTransitionError(f"run {run_id} already has active formal shot {other_active[0]}")
            checkpoints[shot_id] = {**canonical, "prompt_id": prompt_id}
            settings["formal_prompt_checkpoints"] = checkpoints
            if run.comfy_prompt_id != prompt_id or active is None:
                current = RunStatus(run_row["status"])
                run = run.model_copy(update={"comfy_prompt_id": prompt_id, "settings": settings, "updated_at": datetime.now(timezone.utc)})
                self._update_run_row(conn, run, current)
            duplicate = conn.execute(
                "SELECT 1 FROM novel_video_events WHERE run_id = ? AND event_type = ? AND payload LIKE ?",
                (run_id, "video_generation_prompt_submitted", f'%"prompt_id":"{prompt_id}"%'),
            ).fetchone()
            if duplicate is None:
                event = RunEvent(run_id=run_id, event_type="video_generation_prompt_submitted", payload={"shot_id": shot_id, "prompt_id": prompt_id})
                conn.execute(
                    "INSERT INTO novel_video_events (run_id, event_type, payload, created_at) VALUES (?, ?, ?, ?)",
                    (run_id, event.event_type, event.model_dump_json(), event.created_at.isoformat()),
                )
        return run

    def get_generation_prompt(self, run_id: str, shot_id: str) -> str | None:
        """Return only the unresolved prompt bound to this exact formal shot."""
        run = self.get_run(run_id)
        if run is None:
            return None
        checkpoint = (run.settings.get("formal_prompt_checkpoints", {}) or {}).get(shot_id, {})
        prompt_id = checkpoint.get("prompt_id") if isinstance(checkpoint, dict) else None
        return prompt_id if isinstance(prompt_id, str) and prompt_id else None

    def get_generation_checkpoint(self, run_id: str, shot_id: str) -> dict[str, Any] | None:
        run = self.get_run(run_id)
        if run is None:
            return None
        value = (run.settings.get("formal_prompt_checkpoints", {}) or {}).get(shot_id)
        return dict(value) if isinstance(value, dict) else None

    def mark_generation_started(self, run_id: str, shot_id: str) -> ShotRecord:
        """Normalize a formal shot through DRAFT→QUEUED→RUNNING atomically."""
        with self.database.transaction(immediate=True) as conn:
            row = conn.execute("SELECT status, payload FROM novel_video_shots WHERE id = ? AND run_id = ?", (shot_id, run_id)).fetchone()
            if row is None:
                raise ValueError("formal generation run/shot ownership is invalid")
            shot = ShotRecord.model_validate_json(row["payload"])
            current = ShotStatus(row["status"])
            paths = {
                ShotStatus.DRAFT: (ShotStatus.LOCKED, ShotStatus.QUEUED, ShotStatus.RUNNING),
                ShotStatus.LOCKED: (ShotStatus.QUEUED, ShotStatus.RUNNING),
                ShotStatus.QUEUED: (ShotStatus.RUNNING,),
                ShotStatus.RUNNING: (),
                ShotStatus.VALIDATING: (),
            }
            for target in paths.get(current, ()):
                transition_shot(current, target)
                shot = shot.model_copy(update={"status": target, "updated_at": datetime.now(timezone.utc)})
                self._update_shot_row(conn, shot, current)
                current = target
            return shot

    def list_events(self, run_id: str) -> list[RunEvent]:
        return self.list_events_page(run_id, after_sequence=0, limit=None)

    def list_events_page(
        self, run_id: str, *, after_sequence: int = 0, limit: int | None = 100
    ) -> list[RunEvent]:
        """Read a durable event cursor without relying on process memory."""
        if after_sequence < 0:
            raise ValueError("event cursor cannot be negative")
        if limit is not None and not 1 <= limit <= 500:
            raise ValueError("event page size must be between 1 and 500")
        query = (
            "SELECT sequence, payload FROM novel_video_events "
            "WHERE run_id = ? AND sequence > ? ORDER BY sequence"
        )
        parameters: tuple[object, ...] = (run_id, after_sequence)
        if limit is not None:
            query += " LIMIT ?"
            parameters = (*parameters, limit)
        with self.database.connect() as conn:
            rows = conn.execute(query, parameters).fetchall()
        return [
            RunEvent.model_validate_json(row["payload"]).model_copy(update={"sequence": row["sequence"]})
            for row in rows
        ]

    def _fetch_one(self, query: str, parameters: tuple[str, ...]):
        with self.database.connect() as conn:
            return conn.execute(query, parameters).fetchone()

    @staticmethod
    def _run_parameters(run: ProductionRun) -> tuple[str | None, ...]:
        return (
            run.id,
            run.project_id,
            run.status.value,
            run.model_dump_json(),
            run.lease_id,
            run.lease_expires_at.isoformat() if run.lease_expires_at else None,
            run.created_at.isoformat(),
            run.updated_at.isoformat(),
        )

    @staticmethod
    def _shot_parameters(shot: ShotRecord) -> tuple[str | int, ...]:
        return (
            shot.id,
            shot.run_id,
            shot.sequence,
            shot.status.value,
            shot.model_dump_json(),
            shot.updated_at.isoformat(),
        )

    def _update_run_row(self, conn, run: ProductionRun, current: RunStatus) -> None:
        cursor = conn.execute(
            """UPDATE novel_video_runs SET
                 project_id = ?, status = ?, payload = ?, lease_id = ?,
                 lease_expires_at = ?, created_at = ?, updated_at = ?
               WHERE id = ? AND status = ?""",
            (
                run.project_id,
                run.status.value,
                run.model_dump_json(),
                run.lease_id,
                run.lease_expires_at.isoformat() if run.lease_expires_at else None,
                run.created_at.isoformat(),
                run.updated_at.isoformat(),
                run.id,
                current.value,
            ),
        )
        if cursor.rowcount != 1:
            raise ConcurrentTransitionError(
                f"concurrent run transition conflict for {run.id} from {current.value}"
            )

    def _update_shot_row(self, conn, shot: ShotRecord, current: ShotStatus) -> None:
        cursor = conn.execute(
            """UPDATE novel_video_shots SET
                 run_id = ?, sequence = ?, status = ?, payload = ?, updated_at = ?
               WHERE id = ? AND status = ?""",
            (
                shot.run_id,
                shot.sequence,
                shot.status.value,
                shot.model_dump_json(),
                shot.updated_at.isoformat(),
                shot.id,
                current.value,
            ),
        )
        if cursor.rowcount != 1:
            raise ConcurrentTransitionError(
                f"concurrent shot transition conflict for {shot.id} from {current.value}"
            )

    def _validate_asset_ownership(self, conn, asset: AssetVersion) -> None:
        """Enforce project/run/shot lineage for every persisted asset write."""
        if conn.execute("SELECT 1 FROM novel_video_projects WHERE id = ?", (asset.project_id,)).fetchone() is None:
            raise ValueError("asset project does not exist")
        if asset.kind == "novel_source":
            if asset.run_id != f"source-{asset.project_id}" or asset.shot_id is not None:
                raise ValueError("novel source asset has invalid project-only ownership")
        else:
            run_row = conn.execute("SELECT project_id FROM novel_video_runs WHERE id = ?", (asset.run_id,)).fetchone()
            if run_row is None or run_row["project_id"] != asset.project_id:
                raise ValueError("asset run is missing or belongs to another project")
            if asset.shot_id is not None:
                shot_row = conn.execute("SELECT run_id FROM novel_video_shots WHERE id = ?", (asset.shot_id,)).fetchone()
                if shot_row is None or shot_row["run_id"] != asset.run_id:
                    raise ValueError("asset shot is missing or belongs to another run")
        if asset.parent_id:
            parent_row = conn.execute("SELECT project_id, run_id, shot_id FROM novel_video_assets WHERE id = ?", (asset.parent_id,)).fetchone()
            if parent_row is None or parent_row["project_id"] != asset.project_id or parent_row["run_id"] != asset.run_id:
                raise ValueError("asset parent is missing or belongs to another project/run")
            if asset.shot_id and parent_row["shot_id"] != asset.shot_id:
                raise ValueError("asset parent belongs to another shot")

    def _clear_project_reference_descendants(self, conn, project_id: str, replaced_asset_id: str) -> None:
        """Clear only saved H3 packages that cite the replaced approved version."""
        rows = conn.execute(
            """SELECT s.status, s.payload FROM novel_video_shots AS s
               JOIN novel_video_runs AS r ON r.id = s.run_id
               WHERE r.project_id = ?""",
            (project_id,),
        ).fetchall()
        for row in rows:
            shot = ShotRecord.model_validate_json(row["payload"])
            package = shot.reference_package
            if package is None:
                continue
            references = set(
                package.picture_asset_version_ids
                + package.video_reference_asset_version_ids
                + package.audio_reference_asset_version_ids
            )
            if replaced_asset_id not in references:
                continue
            plan = dict(shot.plan)
            plan["invalidated_by_asset_id"] = replaced_asset_id
            updated = shot.model_copy(update={
                "plan": plan, "reference_package": None,
                "updated_at": datetime.now(timezone.utc),
            })
            self._update_shot_row(conn, updated, ShotStatus(row["status"]))


def _sha256_file(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _chapter_selection_key(chapter_indexes: list[int] | tuple[int, ...]) -> str:
    if not chapter_indexes or any(index < 1 for index in chapter_indexes):
        raise ValueError("chapter plan selection requires positive chapter indexes")
    if len(set(chapter_indexes)) != len(chapter_indexes):
        raise ValueError("chapter plan selection cannot contain duplicate indexes")
    return ",".join(str(index) for index in chapter_indexes)


def _chapter_plan_payload(bundle: ChapterPlanBundle) -> dict[str, Any]:
    return {
        "plan_version": bundle.plan_version,
        "source_sha256": bundle.source_sha256,
        "chapter_indexes": list(bundle.chapter_indexes),
        "target_seconds": bundle.target_seconds,
        "suggested_shot_count": bundle.suggested_shot_count,
        "source_asset_version_id": bundle.source_asset_version_id,
        "plan_id": bundle.plan_id,
        "max_shots": bundle.max_shots,
        "scenes": [
            {
                "id": scene.id,
                "chapter_index": scene.chapter_index,
                "source_excerpt": scene.source_excerpt,
                "narrative_purpose": scene.narrative_purpose,
                "shots": [_shot_plan_payload(shot) for shot in scene.shots],
            }
            for scene in bundle.scenes
        ],
        "shots": [_shot_plan_payload(shot) for shot in bundle.shots],
    }


def _shot_plan_payload(shot: ShotPlan) -> dict[str, Any]:
    return {
        "id": shot.id,
        "sequence": shot.sequence,
        "scene_id": shot.scene_id,
        "source_excerpt": shot.source_excerpt,
        "narrative_purpose": shot.narrative_purpose,
        "duration_seconds": shot.duration_seconds,
        "continuity": shot.continuity,
        "inherit_tail": shot.inherit_tail,
        "prompt": shot.prompt,
        "negative_prompt": shot.negative_prompt,
        "dialogue": [
            {
                "speaker": line.speaker,
                "text": line.text,
                "version_id": line.version_id,
            }
            for line in shot.dialogue
        ],
        "narration": shot.narration,
        "ambience_prompt": shot.ambience_prompt,
    }


def _shot_plan_from_payload(payload: dict[str, Any]) -> ShotPlan:
    return ShotPlan(
        id=str(payload["id"]), sequence=int(payload["sequence"]), scene_id=str(payload["scene_id"]),
        source_excerpt=str(payload["source_excerpt"]), narrative_purpose=str(payload["narrative_purpose"]),
        duration_seconds=float(payload["duration_seconds"]), continuity=str(payload["continuity"]),
        inherit_tail=bool(payload["inherit_tail"]), prompt=str(payload["prompt"]),
        negative_prompt=str(payload["negative_prompt"]),
        dialogue=tuple(
            DialogueLine(
                speaker=str(line["speaker"]),
                text=str(line["text"]),
                version_id=str(line.get("version_id", "")),
            )
            for line in payload.get("dialogue", [])
        ),
        narration=str(payload.get("narration", "")), ambience_prompt=str(payload.get("ambience_prompt", "")),
    )


def _chapter_plan_from_payload(payload: dict[str, Any]) -> ChapterPlanBundle:
    scenes = tuple(
        ScenePlan(
            id=str(scene["id"]), chapter_index=int(scene["chapter_index"]),
            source_excerpt=str(scene["source_excerpt"]), narrative_purpose=str(scene["narrative_purpose"]),
            shots=tuple(_shot_plan_from_payload(shot) for shot in scene["shots"]),
        )
        for scene in payload["scenes"]
    )
    return ChapterPlanBundle(
        plan_version=str(payload["plan_version"]), source_sha256=str(payload["source_sha256"]),
        chapter_indexes=tuple(int(index) for index in payload["chapter_indexes"]),
        target_seconds=float(payload["target_seconds"]), suggested_shot_count=int(payload["suggested_shot_count"]),
        scenes=scenes, shots=tuple(_shot_plan_from_payload(shot) for shot in payload["shots"]),
        source_asset_version_id=str(payload.get("source_asset_version_id", "")),
        plan_id=str(payload.get("plan_id", "")), max_shots=payload.get("max_shots"),
    )


def _validated_generation_checkpoint(checkpoint: dict[str, Any] | None, *, run_id: str, shot_id: str) -> dict[str, Any]:
    required = {
        "task_id", "run_id", "shot_id", "attempt_id", "prompt", "negative_prompt",
        "base_seed", "effective_seed", "width", "height", "fps", "duration_seconds",
        "legal_frame_count", "aspect_ratio", "megapixel_profile", "inputs", "video_asset_ids",
        "audio_asset_ids", "models", "workflow_version", "output_video", "output_tail",
        "idempotency_hash",
    }
    # task_id/run_id/shot_id/attempt_id are the worker-side execution binding
    # merged by the H3 provider before the checkpoint is persisted.
    allowed_extra = {"task_id", "run_id", "shot_id", "attempt_id"}
    if not isinstance(checkpoint, dict):
        raise ValueError("formal prompt checkpoint must contain the exact canonical field set")
    if not required.issubset(set(checkpoint)) or not set(checkpoint).issubset(required | allowed_extra):
        raise ValueError("formal prompt checkpoint must contain the exact canonical field set")
    if checkpoint["run_id"] != run_id or checkpoint["shot_id"] != shot_id:
        raise ValueError("formal prompt checkpoint ownership mismatch")
    core = {key: value for key, value in checkpoint.items() if key != "idempotency_hash"}
    expected = sha256(json.dumps(core, sort_keys=True).encode()).hexdigest()
    if checkpoint["idempotency_hash"] != expected:
        raise ValueError("formal prompt checkpoint hash mismatch")
    return dict(checkpoint)
