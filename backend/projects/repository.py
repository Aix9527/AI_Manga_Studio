from __future__ import annotations

import json
from uuid import uuid4

from backend.orchestration.repository import utcnow
from backend.projects.schemas import ProjectCreate, SourceCreate


class ProjectRepository:
    def __init__(self, database):
        self.database = database

    def create(self, command: ProjectCreate) -> dict:
        project_id = str(uuid4())
        now = utcnow()
        with self.database.transaction() as connection:
            connection.execute(
                '''INSERT INTO projects(
                    id, name, description, mode, content_style,
                    target_duration_seconds, width, height, fps,
                    quality_preset, created_at, updated_at
                ) VALUES (?, ?, ?, ?, 'live_action', ?, ?, ?, ?,
                          'preview_then_quality', ?, ?)''',
                (
                    project_id,
                    command.name,
                    command.description,
                    command.mode,
                    command.target_duration_seconds,
                    command.width,
                    command.height,
                    command.fps,
                    now,
                    now,
                ),
            )
        return self.get(project_id)

    def get(
        self,
        project_id: str,
        include_archived: bool = False,
    ) -> dict | None:
        condition = '' if include_archived else ' AND status != \'archived\''
        with self.database.connection() as connection:
            row = connection.execute(
                f'SELECT * FROM projects WHERE id=?{condition}',
                (project_id,),
            ).fetchone()
            if row is None:
                return None
            project = dict(row)
            project['sources'] = [
                self._source(source_row)
                for source_row in connection.execute(
                    '''SELECT * FROM source_items
                       WHERE project_id=?
                       ORDER BY created_at, id''',
                    (project_id,),
                )
            ]
            return project

    def list(self, include_archived: bool = False) -> list[dict]:
        where = '' if include_archived else 'WHERE status != \'archived\''
        with self.database.connection() as connection:
            return [
                dict(row)
                for row in connection.execute(
                    f'''SELECT * FROM projects {where}
                        ORDER BY updated_at DESC, id'''
                )
            ]

    def archive(self, project_id: str) -> dict:
        with self.database.transaction() as connection:
            cursor = connection.execute(
                '''UPDATE projects
                   SET status='archived', updated_at=?
                   WHERE id=?''',
                (utcnow(), project_id),
            )
            if cursor.rowcount != 1:
                raise LookupError('project not found')
        return self.get(project_id, include_archived=True)

    def add_source(self, project_id: str, command: SourceCreate) -> dict:
        if self.get(project_id, include_archived=True) is None:
            raise LookupError('project not found')
        source_id = str(uuid4())
        with self.database.transaction() as connection:
            connection.execute(
                '''INSERT INTO source_items(
                    id, project_id, kind, original_name, original_location,
                    managed_path, sha256, rights_confirmed, metadata_json,
                    created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                (
                    source_id,
                    project_id,
                    command.kind,
                    command.original_name,
                    command.original_location,
                    command.managed_path,
                    command.sha256,
                    int(command.rights_confirmed),
                    json.dumps(
                        command.metadata,
                        ensure_ascii=False,
                        sort_keys=True,
                        allow_nan=False,
                    ),
                    utcnow(),
                ),
            )
        with self.database.connection() as connection:
            row = connection.execute(
                'SELECT * FROM source_items WHERE id=?',
                (source_id,),
            ).fetchone()
            return self._source(row)

    @staticmethod
    def _source(row) -> dict:
        item = dict(row)
        item['rights_confirmed'] = bool(item['rights_confirmed'])
        item['metadata'] = json.loads(item.pop('metadata_json'))
        return item
