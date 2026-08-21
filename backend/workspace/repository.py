from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote

from backend.orchestration.database import OrchestrationDatabase
from backend.workspace.models import ProjectAsset, StageAutomation, StageKey


class WorkspaceRepository:
    def __init__(self, db: OrchestrationDatabase, projects_root: str | Path = "projects"):
        self.db = db
        self.projects_root = Path(projects_root)

    def upsert_project(
        self,
        project_id: str,
        title: str | None = None,
        source_path: str | None = None,
    ) -> None:
        with self.db.transaction() as conn:
            existing = conn.execute(
                "SELECT title, source_path FROM project_workspaces WHERE project_id=?", (project_id,)
            ).fetchone()
            if existing:
                conn.execute(
                    """UPDATE project_workspaces
                       SET title=?, source_path=?, updated_at=?
                       WHERE project_id=?""",
                    (
                        title or existing["title"],
                        source_path or existing["source_path"],
                        _now_iso(),
                        project_id,
                    ),
                )
                return
            conn.execute(
                """INSERT INTO project_workspaces
                   (project_id, title, source_path, version, updated_at)
                   VALUES (?, ?, ?, 1, ?)""",
                (project_id, title or project_id, source_path or "", _now_iso()),
            )

    def get_project(self, project_id: str) -> dict | None:
        with self.db.connect() as conn:
            row = conn.execute(
                "SELECT project_id, title, source_path, version FROM project_workspaces WHERE project_id=?",
                (project_id,),
            ).fetchone()
        return dict(row) if row else None

    def upsert_stage_automation(self, project_id: str, value: StageAutomation) -> None:
        with self.db.transaction() as conn:
            conn.execute(
                """INSERT INTO stage_automation (project_id, stage_key, settings, updated_at)
                   VALUES (?, ?, ?, ?)
                   ON CONFLICT(project_id, stage_key) DO UPDATE SET
                       settings=excluded.settings,
                       updated_at=excluded.updated_at""",
                (project_id, value.stage_key.value, value.model_dump_json(), _now_iso()),
            )

    def get_stage_automation(self, project_id: str, stage_key: StageKey) -> StageAutomation:
        with self.db.connect() as conn:
            row = conn.execute(
                "SELECT settings FROM stage_automation WHERE project_id=? AND stage_key=?",
                (project_id, stage_key.value),
            ).fetchone()
        return StageAutomation.model_validate_json(row["settings"]) if row else StageAutomation(stage_key=stage_key)

    def get_all_stage_automation(self, project_id: str) -> list[StageAutomation]:
        with self.db.connect() as conn:
            rows = conn.execute(
                "SELECT stage_key, settings FROM stage_automation WHERE project_id=?", (project_id,)
            ).fetchall()
        saved = {StageKey(row["stage_key"]): StageAutomation.model_validate_json(row["settings"]) for row in rows}
        return [saved.get(stage_key, StageAutomation(stage_key=stage_key)) for stage_key in StageKey]

    def add_project_asset(
        self,
        job_id: str,
        kind: str,
        path: str,
        stage_key: str = "",
        scene_id: str = "",
        shot_id: str = "",
        parent_artifact_id: int | None = None,
        quality_status: str = "unreviewed",
        metadata: dict[str, object] | None = None,
        sha256: str = "",
    ) -> ProjectAsset:
        lineage = (kind, stage_key, scene_id, shot_id)
        with self.db.transaction(immediate=True) as conn:
            job = conn.execute("SELECT project_id FROM jobs WHERE id=?", (job_id,)).fetchone()
            if job is None:
                raise ValueError("任务不存在")
            project_id = job["project_id"]

            if parent_artifact_id is not None:
                parent = conn.execute(
                    "SELECT * FROM artifacts WHERE id=?", (parent_artifact_id,)
                ).fetchone()
                if parent is None:
                    raise ValueError("父素材不存在")
                if parent["project_id"] != project_id:
                    raise ValueError("父素材必须属于同一项目")
                parent_lineage = (
                    parent["kind"], parent["stage_key"], parent["scene_id"], parent["shot_id"]
                )
                if parent_lineage != lineage:
                    raise ValueError("父素材与新素材版本链不匹配")
                version = int(parent["version"]) + 1
                duplicate = conn.execute(
                    """SELECT 1 FROM artifacts
                       WHERE project_id=? AND kind=? AND stage_key=? AND scene_id=?
                         AND shot_id=? AND version=?""",
                    (project_id, *lineage, version),
                ).fetchone()
                if duplicate:
                    raise ValueError("该父素材已有下一版本")
            else:
                row = conn.execute(
                    """SELECT COALESCE(MAX(version), 0) AS max_version FROM artifacts
                       WHERE project_id=? AND kind=? AND stage_key=? AND scene_id=? AND shot_id=?""",
                    (project_id, *lineage),
                ).fetchone()
                version = int(row["max_version"]) + 1

            step = conn.execute(
                """SELECT id FROM job_steps
                   WHERE job_id=? AND (?='' OR stage_key=?) AND (?='' OR shot_id=?)
                   ORDER BY sequence LIMIT 1""",
                (job_id, stage_key, stage_key, shot_id, shot_id),
            ).fetchone()
            if step is None:
                step = conn.execute(
                    "SELECT id FROM job_steps WHERE job_id=? ORDER BY sequence LIMIT 1", (job_id,)
                ).fetchone()
            if step is None:
                raise ValueError("任务没有可关联制作步骤")

            conn.execute(
                """UPDATE artifacts SET active=0
                   WHERE project_id=? AND kind=? AND stage_key=? AND scene_id=? AND shot_id=?
                     AND active=1""",
                (project_id, *lineage),
            )
            cursor = conn.execute(
                """INSERT INTO artifacts
                   (job_id, step_id, kind, path, sha256, metadata, active, project_id,
                    parent_artifact_id, version, stage_key, scene_id, shot_id, quality_status)
                   VALUES (?, ?, ?, ?, ?, ?, 1, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    job_id,
                    step["id"],
                    kind,
                    path,
                    sha256,
                    json.dumps(metadata or {}, ensure_ascii=False),
                    project_id,
                    parent_artifact_id,
                    version,
                    stage_key,
                    scene_id,
                    shot_id,
                    quality_status,
                ),
            )
            asset_id = int(cursor.lastrowid)
            row = conn.execute("SELECT * FROM artifacts WHERE id=?", (asset_id,)).fetchone()
        return self._asset_from_row(row)

    def find_asset_by_sha256(self, project_id: str, kind: str, sha256: str) -> ProjectAsset | None:
        """Return an active asset with the same project/kind/content-hash (dedup)."""
        if not sha256:
            return None
        with self.db.transaction() as conn:
            row = conn.execute(
                """SELECT * FROM artifacts
                   WHERE project_id=? AND kind=? AND sha256=? AND active=1
                   ORDER BY id DESC LIMIT 1""",
                (project_id, kind, sha256),
            ).fetchone()
        return self._asset_from_row(row) if row else None

    def list_project_assets(
        self,
        project_id: str,
        *,
        kind: str | None = None,
        stage_key: str | None = None,
        scene_id: str | None = None,
        shot_id: str | None = None,
        quality_status: str | None = None,
        active: bool | None = None,
    ) -> list[ProjectAsset]:
        clauses = ["artifacts.project_id=?"]
        params: list[Any] = [project_id]
        for column, value in (
            ("kind", kind),
            ("stage_key", stage_key),
            ("scene_id", scene_id),
            ("shot_id", shot_id),
            ("quality_status", quality_status),
        ):
            if value is not None:
                clauses.append(f"artifacts.{column}=?")
                params.append(value)
        if active is not None:
            clauses.append("artifacts.active=?")
            params.append(int(active))
        with self.db.connect() as conn:
            rows = conn.execute(
                f"""SELECT artifacts.* FROM artifacts
                    WHERE {' AND '.join(clauses)}
                    ORDER BY artifacts.active DESC, artifacts.version DESC, artifacts.id DESC""",
                params,
            ).fetchall()
        return [self._asset_from_row(row) for row in rows]

    def get_project_asset(self, project_id: str, asset_id: int) -> ProjectAsset | None:
        with self.db.connect() as conn:
            row = conn.execute(
                """SELECT artifacts.* FROM artifacts
                   WHERE artifacts.project_id=? AND artifacts.id=?""",
                (project_id, asset_id),
            ).fetchone()
        return self._asset_from_row(row) if row else None

    def get_project_asset_stored_path(self, project_id: str, asset_id: int) -> str | None:
        with self.db.connect() as conn:
            row = conn.execute(
                "SELECT path FROM artifacts WHERE project_id=? AND id=?", (project_id, asset_id)
            ).fetchone()
        return row["path"] if row else None

    def _asset_from_row(self, row: Any) -> ProjectAsset:
        try:
            metadata = json.loads(row["metadata"] or "{}")
            if not isinstance(metadata, dict):
                metadata = {}
        except (TypeError, json.JSONDecodeError):
            metadata = {}
        try:
            quality_report = json.loads(row["quality_report"] or "{}")
            if not isinstance(quality_report, dict):
                quality_report = {}
        except (TypeError, json.JSONDecodeError):
            quality_report = {}
        project_id = row["project_id"]
        return ProjectAsset(
            id=row["id"],
            project_id=project_id,
            job_id=row["job_id"],
            step_id=row["step_id"],
            kind=row["kind"],
            path=self._display_path(project_id, row["path"]),
            media_url=(
                f"/api/workspace/{quote(project_id, safe='')}/assets/{row['id']}/media"
            ),
            stage_key=row["stage_key"] or None,
            scene_id=row["scene_id"],
            shot_id=row["shot_id"],
            version=row["version"],
            parent_artifact_id=row["parent_artifact_id"],
            active=bool(row["active"]),
            quality_status=row["quality_status"],
            quality_attempt=row["quality_attempt"],
            quality_report=quality_report,
            metadata=metadata,
            created_at=row["created_at"],
        )

    def _display_path(self, project_id: str, stored_path: str) -> str:
        path = Path(stored_path)
        project_root = (self.projects_root / project_id).resolve()
        if path.is_absolute():
            candidate = path.resolve()
        else:
            legacy_candidate = path.resolve()
            try:
                legacy_candidate.relative_to(project_root)
            except ValueError:
                parts = path.parts
                if (
                    len(parts) >= 2
                    and parts[0].casefold() == self.projects_root.name.casefold()
                    and parts[1].casefold() == project_id.casefold()
                ):
                    candidate = project_root.joinpath(*parts[2:]).resolve()
                else:
                    candidate = (project_root / path).resolve()
            else:
                candidate = legacy_candidate
        try:
            return candidate.relative_to(project_root).as_posix()
        except ValueError:
            return path.name


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")
