"""Episode SQLite repository + append-only episode audit chain (Phase 13.1)."""

from __future__ import annotations

import sqlite3
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

from backend.story.episode.model import Episode


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


class EpisodeRepository:
    def __init__(self, db_path: str = "storage/orchestrator.db"):
        self.db_path = db_path
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self.initialize_schema()

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def initialize_schema(self) -> None:
        with self._conn() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS episodes (
                    id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    season INTEGER NOT NULL DEFAULT 1,
                    episode_no INTEGER NOT NULL,
                    title TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL DEFAULT 'draft',
                    hook TEXT NOT NULL DEFAULT '',
                    conflict TEXT NOT NULL DEFAULT '',
                    climax TEXT NOT NULL DEFAULT '',
                    ending TEXT NOT NULL DEFAULT '',
                    retention_strategy TEXT NOT NULL DEFAULT '',
                    script_version TEXT NOT NULL DEFAULT '',
                    storyboard_version TEXT NOT NULL DEFAULT '',
                    production_progress REAL NOT NULL DEFAULT 0.0,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    approved_at TEXT NOT NULL DEFAULT '',
                    published_at TEXT NOT NULL DEFAULT '',
                    meta TEXT NOT NULL DEFAULT '{}'
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS episode_audit (
                    id TEXT PRIMARY KEY,
                    episode_id TEXT NOT NULL,
                    action TEXT NOT NULL,
                    from_status TEXT NOT NULL DEFAULT '',
                    to_status TEXT NOT NULL DEFAULT '',
                    operator TEXT NOT NULL DEFAULT '',
                    detail TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_episodes_project ON episodes(project_id, season, episode_no)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_episode_audit_ep ON episode_audit(episode_id, created_at)"
            )

    # ------------------------------------------------------------- episodes
    def create(self, episode: Episode) -> Episode:
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO episodes (
                    id, project_id, season, episode_no, title, status, hook, conflict,
                    climax, ending, retention_strategy, script_version, storyboard_version,
                    production_progress, created_at, updated_at, approved_at, published_at, meta
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    episode.id, episode.project_id, episode.season, episode.episode_no,
                    episode.title, episode.status, episode.hook, episode.conflict,
                    episode.climax, episode.ending, episode.retention_strategy,
                    episode.script_version, episode.storyboard_version,
                    episode.production_progress, episode.created_at, episode.updated_at,
                    episode.approved_at, episode.published_at,
                    __import__("json").dumps(episode.meta, ensure_ascii=False),
                ),
            )
            conn.commit()
        return episode

    def get(self, episode_id: str) -> Optional[Episode]:
        with self._conn() as conn:
            row = conn.execute("SELECT * FROM episodes WHERE id=?", (episode_id,)).fetchone()
        return self._row_to_episode(row) if row else None

    def list_by_project(self, project_id: str) -> list[Episode]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM episodes WHERE project_id=? ORDER BY season, episode_no",
                (project_id,),
            ).fetchall()
        return [self._row_to_episode(row) for row in rows]

    def list_all(self) -> list[Episode]:
        with self._conn() as conn:
            rows = conn.execute("SELECT * FROM episodes ORDER BY created_at DESC").fetchall()
        return [self._row_to_episode(row) for row in rows]

    def update(self, episode: Episode) -> Episode:
        episode.updated_at = _now()
        with self._conn() as conn:
            conn.execute(
                """
                UPDATE episodes SET title=?, status=?, hook=?, conflict=?, climax=?, ending=?,
                    retention_strategy=?, script_version=?, storyboard_version=?,
                    production_progress=?, updated_at=?, approved_at=?, published_at=?, meta=?
                WHERE id=?
                """,
                (
                    episode.title, episode.status, episode.hook, episode.conflict,
                    episode.climax, episode.ending, episode.retention_strategy,
                    episode.script_version, episode.storyboard_version,
                    episode.production_progress, episode.updated_at,
                    episode.approved_at, episode.published_at,
                    __import__("json").dumps(episode.meta, ensure_ascii=False),
                    episode.id,
                ),
            )
            conn.commit()
        return episode

    def delete(self, episode_id: str) -> bool:
        with self._conn() as conn:
            cur = conn.execute("DELETE FROM episodes WHERE id=?", (episode_id,))
            conn.commit()
        return cur.rowcount > 0

    # ------------------------------------------------------------- audit
    def record_audit(
        self,
        episode_id: str,
        action: str,
        from_status: str,
        to_status: str,
        operator: str = "system",
        detail: dict | None = None,
    ) -> dict:
        entry = {
            "id": f"AUD-EP-{uuid.uuid4().hex[:10]}",
            "episode_id": episode_id,
            "action": action,
            "from_status": from_status,
            "to_status": to_status,
            "operator": operator,
            "detail": detail or {},
            "created_at": _now(),
        }
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO episode_audit (id, episode_id, action, from_status, to_status,
                    operator, detail, created_at)
                VALUES (?,?,?,?,?,?,?,?)
                """,
                (
                    entry["id"], episode_id, action, from_status, to_status,
                    operator, __import__("json").dumps(entry["detail"], ensure_ascii=False),
                    entry["created_at"],
                ),
            )
            conn.commit()
        return entry

    def audit(self, episode_id: str) -> list[dict]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM episode_audit WHERE episode_id=? ORDER BY rowid",
                (episode_id,),
            ).fetchall()
        return [
            {
                "id": row["id"],
                "episode_id": row["episode_id"],
                "action": row["action"],
                "from_status": row["from_status"],
                "to_status": row["to_status"],
                "operator": row["operator"],
                "detail": __import__("json").loads(row["detail"] or "{}"),
                "created_at": row["created_at"],
            }
            for row in rows
        ]

    @staticmethod
    def _row_to_episode(row: sqlite3.Row) -> Episode:
        return Episode(
            id=row["id"],
            project_id=row["project_id"],
            season=row["season"],
            episode_no=row["episode_no"],
            title=row["title"],
            status=row["status"],
            hook=row["hook"],
            conflict=row["conflict"],
            climax=row["climax"],
            ending=row["ending"],
            retention_strategy=row["retention_strategy"],
            script_version=row["script_version"],
            storyboard_version=row["storyboard_version"],
            production_progress=row["production_progress"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            approved_at=row["approved_at"],
            published_at=row["published_at"],
            meta=__import__("json").loads(row["meta"] or "{}"),
        )
