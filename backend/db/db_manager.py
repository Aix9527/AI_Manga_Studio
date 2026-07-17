"""
V3.0 Layer 17 — Database Manager (SQLite)

Unified database manager singleton for all persistence needs.
All 8 sub-schemas share a single SQLite connection pool.

Tables:
  - story_db:      Novel → Chapter → Scene → Beat → Shot hierarchy
  - character_db:  CharacterDNA persistence
  - scene_db:      ScenePack persistence
  - asset_db:      Image/video/audio asset index
  - prompt_db:     Prompt templates and history
  - timeline_db:   Timeline data
  - task_db:       Pipeline task status
  - quality_db:    Quality scores history
"""

from __future__ import annotations

import json
import os
import sqlite3
import time
from pathlib import Path
from threading import Lock
from typing import Any, Dict, List, Optional


class DBManager:
    """Singleton database manager.

    Usage:
        db = DBManager.instance("D:/AI_Manga_Studio/data/pipeline.db")
        db.execute("SELECT * FROM stories WHERE project_id = ?", ("proj_001",))
    """

    _instance: Optional["DBManager"] = None
    _lock = Lock()

    def __init__(self, db_path: str = ""):
        self.db_path = db_path

    @classmethod
    def instance(cls, db_path: str = "") -> "DBManager":
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls(db_path)
                    if db_path:
                        cls._instance.init_all_tables()
        return cls._instance

    def _get_conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    # ── Table initialization ─────────────────────────────────

    def init_all_tables(self):
        """Create all pipeline tables."""
        conn = self._get_conn()

        # Story hierarchy
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS novels (
                novel_id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                author TEXT DEFAULT '',
                raw_path TEXT DEFAULT '',
                metadata_json TEXT DEFAULT '{}',
                created_at REAL NOT NULL
            );

            CREATE TABLE IF NOT EXISTS chapters (
                chapter_id TEXT PRIMARY KEY,
                novel_id TEXT NOT NULL,
                chapter_index INTEGER NOT NULL,
                title TEXT DEFAULT '',
                summary TEXT DEFAULT '',
                created_at REAL NOT NULL,
                FOREIGN KEY (novel_id) REFERENCES novels(novel_id)
            );

            CREATE TABLE IF NOT EXISTS scenes (
                scene_id TEXT PRIMARY KEY,
                chapter_id TEXT NOT NULL,
                scene_index INTEGER NOT NULL,
                location TEXT DEFAULT '',
                time TEXT DEFAULT '',
                weather TEXT DEFAULT '',
                emotion TEXT DEFAULT '',
                duration REAL DEFAULT 0,
                context_json TEXT DEFAULT '{}',
                FOREIGN KEY (chapter_id) REFERENCES chapters(chapter_id)
            );

            CREATE TABLE IF NOT EXISTS beats (
                beat_id TEXT PRIMARY KEY,
                scene_id TEXT NOT NULL,
                beat_index INTEGER NOT NULL,
                beat_type TEXT DEFAULT '',
                description TEXT DEFAULT '',
                characters_json TEXT DEFAULT '[]',
                emotion TEXT DEFAULT '',
                duration REAL DEFAULT 0,
                FOREIGN KEY (scene_id) REFERENCES scenes(scene_id)
            );

            CREATE TABLE IF NOT EXISTS shots (
                shot_id TEXT PRIMARY KEY,
                beat_id TEXT NOT NULL,
                shot_index INTEGER NOT NULL,
                camera TEXT DEFAULT '',
                angle TEXT DEFAULT '',
                action TEXT DEFAULT '',
                composition TEXT DEFAULT '',
                duration REAL DEFAULT 0,
                prompt_json TEXT DEFAULT '{}',
                FOREIGN KEY (beat_id) REFERENCES beats(beat_id)
            );
        """)

        # Characters
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS character_dna (
                character_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                data_json TEXT NOT NULL,
                updated_at REAL NOT NULL
            );
        """)

        # Scenes
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS scene_packs (
                scene_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                data_json TEXT NOT NULL,
                updated_at REAL NOT NULL
            );
        """)

        # Assets
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS assets (
                asset_id TEXT PRIMARY KEY,
                shot_id TEXT DEFAULT '',
                asset_type TEXT NOT NULL,
                file_path TEXT NOT NULL,
                file_size INTEGER DEFAULT 0,
                width INTEGER DEFAULT 0,
                height INTEGER DEFAULT 0,
                duration REAL DEFAULT 0,
                metadata_json TEXT DEFAULT '{}',
                created_at REAL NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_assets_shot ON assets(shot_id);
            CREATE INDEX IF NOT EXISTS idx_assets_type ON assets(asset_type);
        """)

        # Prompts
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS prompts (
                prompt_id TEXT PRIMARY KEY,
                shot_id TEXT DEFAULT '',
                template_name TEXT DEFAULT '',
                positive_prompt TEXT NOT NULL,
                negative_prompt TEXT DEFAULT '',
                decomposed_json TEXT DEFAULT '{}',
                created_at REAL NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_prompts_shot ON prompts(shot_id);
        """)

        # Timeline
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS timelines (
                clip_id TEXT PRIMARY KEY,
                project_id TEXT NOT NULL,
                shot_id TEXT DEFAULT '',
                start_time REAL NOT NULL,
                end_time REAL NOT NULL,
                source_path TEXT DEFAULT '',
                transition_in TEXT DEFAULT 'cut',
                transition_out TEXT DEFAULT 'cut',
                audio_path TEXT DEFAULT '',
                subtitle_text TEXT DEFAULT ''
            );

            CREATE INDEX IF NOT EXISTS idx_timelines_project ON timelines(project_id);
        """)

        # Tasks
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS tasks (
                task_id TEXT PRIMARY KEY,
                project_id TEXT NOT NULL,
                stage_name TEXT NOT NULL,
                status TEXT DEFAULT 'pending',
                progress REAL DEFAULT 0.0,
                started_at REAL,
                completed_at REAL,
                error_message TEXT DEFAULT '',
                metadata_json TEXT DEFAULT '{}'
            );

            CREATE INDEX IF NOT EXISTS idx_tasks_project ON tasks(project_id);
            CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status);
        """)

        # Quality
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS quality_scores (
                score_id TEXT PRIMARY KEY,
                shot_id TEXT DEFAULT '',
                asset_path TEXT DEFAULT '',
                total_score REAL DEFAULT 0,
                grade TEXT DEFAULT 'F',
                passed INTEGER DEFAULT 0,
                scores_json TEXT DEFAULT '{}',
                created_at REAL NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_quality_shot ON quality_scores(shot_id);
        """)

        conn.commit()
        conn.close()

    # ── Generic CRUD ──────────────────────────────────────────

    def execute(self, sql: str, params: tuple = ()) -> sqlite3.Cursor:
        conn = self._get_conn()
        cur = conn.execute(sql, params)
        conn.commit()
        conn.close()
        return cur

    def fetch_all(self, sql: str, params: tuple = ()) -> List[Dict]:
        conn = self._get_conn()
        rows = conn.execute(sql, params).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def fetch_one(self, sql: str, params: tuple = ()) -> Optional[Dict]:
        conn = self._get_conn()
        row = conn.execute(sql, params).fetchone()
        conn.close()
        return dict(row) if row else None

    # ── Story accessors ───────────────────────────────────────

    def save_novel(self, novel_id: str, title: str, raw_path: str = "", metadata: dict = None):
        self.execute(
            """INSERT OR REPLACE INTO novels
               (novel_id, title, raw_path, metadata_json, created_at)
               VALUES (?, ?, ?, ?, ?)""",
            (novel_id, title, raw_path, json.dumps(metadata or {}), time.time()),
        )

    def save_chapter(self, chapter_id: str, novel_id: str, index: int,
                     title: str = "", summary: str = ""):
        self.execute(
            """INSERT OR REPLACE INTO chapters
               (chapter_id, novel_id, chapter_index, title, summary, created_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (chapter_id, novel_id, index, title, summary, time.time()),
        )

    def save_scene(self, scene_id: str, chapter_id: str, index: int,
                   location: str = "", time_of_day: str = "", weather: str = "",
                   emotion: str = "", duration: float = 0, context: dict = None):
        self.execute(
            """INSERT OR REPLACE INTO scenes
               (scene_id, chapter_id, scene_index, location, time, weather,
                emotion, duration, context_json)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (scene_id, chapter_id, index, location, time_of_day, weather,
             emotion, duration, json.dumps(context or {})),
        )

    def save_beat(self, beat_id: str, scene_id: str, index: int,
                  beat_type: str = "", description: str = "",
                  characters: list = None, emotion: str = "", duration: float = 0):
        self.execute(
            """INSERT OR REPLACE INTO beats
               (beat_id, scene_id, beat_index, beat_type, description,
                characters_json, emotion, duration)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (beat_id, scene_id, index, beat_type, description,
             json.dumps(characters or []), emotion, duration),
        )

    def save_shot(self, shot_id: str, beat_id: str, index: int,
                  camera: str = "", angle: str = "", action: str = "",
                  composition: str = "", duration: float = 0, prompt: dict = None):
        self.execute(
            """INSERT OR REPLACE INTO shots
               (shot_id, beat_id, shot_index, camera, angle, action,
                composition, duration, prompt_json)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (shot_id, beat_id, index, camera, angle, action,
             composition, duration, json.dumps(prompt or {})),
        )

    # ── Asset accessors ───────────────────────────────────────

    def save_asset(self, asset_id: str, asset_type: str, file_path: str,
                   shot_id: str = "", width: int = 0, height: int = 0,
                   duration: float = 0, metadata: dict = None):
        file_size = os.path.getsize(file_path) if os.path.isfile(file_path) else 0
        self.execute(
            """INSERT OR REPLACE INTO assets
               (asset_id, shot_id, asset_type, file_path, file_size,
                width, height, duration, metadata_json, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (asset_id, shot_id, asset_type, file_path, file_size,
             width, height, duration, json.dumps(metadata or {}), time.time()),
        )

    # ── Task accessors ────────────────────────────────────────

    def save_task(self, task_id: str, project_id: str, stage_name: str,
                  status: str = "pending", progress: float = 0.0,
                  error: str = "", metadata: dict = None):
        self.execute(
            """INSERT OR REPLACE INTO tasks
               (task_id, project_id, stage_name, status, progress,
                started_at, error_message, metadata_json)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (task_id, project_id, stage_name, status, progress,
             time.time(), error, json.dumps(metadata or {})),
        )

    def get_task_status(self, task_id: str) -> Optional[Dict]:
        return self.fetch_one("SELECT * FROM tasks WHERE task_id = ?", (task_id,))

    def get_project_progress(self, project_id: str) -> Dict:
        rows = self.fetch_all(
            "SELECT stage_name, status, progress FROM tasks WHERE project_id = ?",
            (project_id,),
        )
        completed = sum(1 for r in rows if r["status"] == "completed")
        return {
            "total_stages": len(rows),
            "completed": completed,
            "stages": {r["stage_name"]: r["status"] for r in rows},
        }

    # ── Quality accessors ─────────────────────────────────────

    def save_quality_report(self, score_id: str, shot_id: str,
                            asset_path: str, total_score: float,
                            grade: str, passed: bool, scores: dict):
        self.execute(
            """INSERT OR REPLACE INTO quality_scores
               (score_id, shot_id, asset_path, total_score, grade,
                passed, scores_json, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (score_id, shot_id, asset_path, total_score, grade,
             1 if passed else 0, json.dumps(scores), time.time()),
        )

    def get_quality_history(self, shot_id: str) -> List[Dict]:
        return self.fetch_all(
            "SELECT * FROM quality_scores WHERE shot_id = ? ORDER BY created_at DESC",
            (shot_id,),
        )
