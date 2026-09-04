from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote
from uuid import uuid4

from backend.orchestration.database import OrchestrationDatabase
from backend.workspace.models import (
    ProductionTemplateList,
    ProductionTemplateVersion,
    ProjectAsset,
    StageAutomation,
    StageKey,
)


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

    def save_production_template_version(
        self,
        project_id: str,
        payload: dict[str, object],
    ) -> ProductionTemplateVersion:
        now = _now_iso()
        with self.db.transaction(immediate=True) as conn:
            head = conn.execute(
                "SELECT latest_version FROM project_production_templates WHERE project_id=?",
                (project_id,),
            ).fetchone()
            if head is None:
                latest_version = 0
                conn.execute(
                    """INSERT INTO project_production_templates
                       (project_id, published_version_id, latest_version, updated_at)
                       VALUES (?, NULL, 0, ?)""",
                    (project_id, now),
                )
            else:
                latest_version = int(head["latest_version"])
            version = latest_version + 1
            version_id = f"ptv_{uuid4().hex}"
            conn.execute(
                """INSERT INTO project_production_template_versions
                   (id, project_id, version, name, schema_version, content_json,
                    content_sha256, compiled_json, compiled_sha256, status,
                    created_at, published_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'active', ?, NULL)""",
                (
                    version_id,
                    project_id,
                    version,
                    str(payload.get("name") or ""),
                    int(payload.get("schema_version") or 1),
                    str(payload.get("content_json") or "{}"),
                    str(payload.get("content_sha256") or ""),
                    str(payload.get("compiled_json") or "{}"),
                    str(payload.get("compiled_sha256") or ""),
                    now,
                ),
            )
            conn.execute(
                """UPDATE project_production_templates
                   SET latest_version=?, updated_at=? WHERE project_id=?""",
                (version, now, project_id),
            )
            row = conn.execute(
                "SELECT * FROM project_production_template_versions WHERE id=?",
                (version_id,),
            ).fetchone()
        return self._template_from_row(row)

    def get_production_template_version(
        self, project_id: str, version: int
    ) -> ProductionTemplateVersion | None:
        with self.db.connect() as conn:
            row = conn.execute(
                """SELECT * FROM project_production_template_versions
                   WHERE project_id=? AND version=?""",
                (project_id, version),
            ).fetchone()
        return self._template_from_row(row) if row else None

    def get_published_production_template(
        self, project_id: str
    ) -> ProductionTemplateVersion | None:
        with self.db.connect() as conn:
            row = conn.execute(
                """SELECT versions.*
                   FROM project_production_templates AS head
                   JOIN project_production_template_versions AS versions
                     ON versions.id=head.published_version_id
                   WHERE head.project_id=?""",
                (project_id,),
            ).fetchone()
        return self._template_from_row(row) if row else None

    def list_production_template_versions(self, project_id: str) -> ProductionTemplateList:
        with self.db.connect() as conn:
            head = conn.execute(
                """SELECT head.latest_version, versions.version AS published_version
                   FROM project_production_templates AS head
                   LEFT JOIN project_production_template_versions AS versions
                     ON versions.id=head.published_version_id
                   WHERE head.project_id=?""",
                (project_id,),
            ).fetchone()
            rows = conn.execute(
                """SELECT * FROM project_production_template_versions
                   WHERE project_id=? ORDER BY version DESC""",
                (project_id,),
            ).fetchall()
        return ProductionTemplateList(
            project_id=project_id,
            latest_version=int(head["latest_version"]) if head else 0,
            published_version=(int(head["published_version"]) if head and head["published_version"] is not None else None),
            versions=[self._template_from_row(row) for row in rows],
        )

    def publish_production_template(
        self, project_id: str, version: int
    ) -> ProductionTemplateVersion:
        now = _now_iso()
        with self.db.transaction(immediate=True) as conn:
            row = conn.execute(
                """SELECT * FROM project_production_template_versions
                   WHERE project_id=? AND version=?""",
                (project_id, version),
            ).fetchone()
            if row is None:
                raise ValueError("template version not found")
            if row["status"] == "archived":
                raise ValueError("archived template cannot be published")
            conn.execute(
                """UPDATE project_production_templates
                   SET published_version_id=?, updated_at=? WHERE project_id=?""",
                (row["id"], now, project_id),
            )
            conn.execute(
                """UPDATE project_production_template_versions
                   SET published_at=COALESCE(published_at, ?) WHERE id=?""",
                (now, row["id"]),
            )
            updated = conn.execute(
                "SELECT * FROM project_production_template_versions WHERE id=?",
                (row["id"],),
            ).fetchone()
        return self._template_from_row(updated)

    def set_production_template_archived(
        self, project_id: str, version: int, archived: bool
    ) -> ProductionTemplateVersion:
        with self.db.transaction(immediate=True) as conn:
            row = conn.execute(
                """SELECT versions.*, head.published_version_id
                   FROM project_production_template_versions AS versions
                   LEFT JOIN project_production_templates AS head
                     ON head.project_id=versions.project_id
                   WHERE versions.project_id=? AND versions.version=?""",
                (project_id, version),
            ).fetchone()
            if row is None:
                raise ValueError("template version not found")
            if archived and row["published_version_id"] == row["id"]:
                raise ValueError("published template cannot be archived")
            status = "archived" if archived else "active"
            conn.execute(
                "UPDATE project_production_template_versions SET status=? WHERE id=?",
                (status, row["id"]),
            )
            updated = conn.execute(
                "SELECT * FROM project_production_template_versions WHERE id=?",
                (row["id"],),
            ).fetchone()
        return self._template_from_row(updated)

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

    def update_project_asset_director(
        self,
        project_id: str,
        asset_id: int,
        director: dict[str, object],
    ) -> ProjectAsset | None:
        with self.db.transaction(immediate=True) as conn:
            row = conn.execute(
                "SELECT * FROM artifacts WHERE project_id=? AND id=?",
                (project_id, asset_id),
            ).fetchone()
            if row is None:
                return None
            try:
                metadata = json.loads(row["metadata"] or "{}")
                if not isinstance(metadata, dict):
                    metadata = {}
            except (TypeError, json.JSONDecodeError):
                metadata = {}
            metadata["director"] = director
            conn.execute(
                "UPDATE artifacts SET metadata=? WHERE project_id=? AND id=?",
                (json.dumps(metadata, ensure_ascii=False), project_id, asset_id),
            )
            updated = conn.execute(
                "SELECT * FROM artifacts WHERE project_id=? AND id=?",
                (project_id, asset_id),
            ).fetchone()
        return self._asset_from_row(updated) if updated else None

    def get_project_asset_stored_path(self, project_id: str, asset_id: int) -> str | None:
        with self.db.connect() as conn:
            row = conn.execute(
                "SELECT path FROM artifacts WHERE project_id=? AND id=?", (project_id, asset_id)
            ).fetchone()
        return row["path"] if row else None

    def _template_from_row(self, row: Any) -> ProductionTemplateVersion:
        return ProductionTemplateVersion(
            id=row["id"],
            project_id=row["project_id"],
            version=int(row["version"]),
            name=row["name"],
            schema_version=int(row["schema_version"]),
            content_json=row["content_json"],
            content_sha256=row["content_sha256"],
            compiled_json=row["compiled_json"],
            compiled_sha256=row["compiled_sha256"],
            status=row["status"],
            created_at=row["created_at"],
            published_at=row["published_at"],
        )

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
            media_url=f"/api/workspace/{quote(project_id, safe='')}/assets/{row['id']}/media",
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
