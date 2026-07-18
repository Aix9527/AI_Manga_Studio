"""
V3.0 Layer 15 — Multi-Level Cache

Dual-layer cache system: SQLite + filesystem.
Caches intermediate pipeline results to skip redundant computations.

Cache modules:
  - prompt_cache:   DecomposedPrompt cache (key=shot_id+model)
  - model_cache:    ComfyUI output cache (key=workflow_hash)
  - scene_cache:    Scene Pack sub-area cache
  - video_cache:    Video clip cache (key=shot_id+motion_hash)
  - audio_cache:    TTS audio cache (key=character_id+text_hash)
  - subtitle_cache: SRT cache (key=shot_id+text_hash)
"""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


class CacheEntry:
    """A single cache entry."""

    def __init__(self, key: str, value: str, metadata: dict = None):
        self.key = key
        self.value = value
        self.metadata = metadata or {}
        self.timestamp = time.time()


class DualCache:
    """SQLite + filesystem dual-layer cache.

    Layer 1 (SQLite): Key-value lookup for small data (prompts, scores).
    Layer 2 (Filesystem): File path lookup for large binaries (images, videos).

    Usage:
        cache = DualCache(db_path="cache.db", file_cache_dir=".cache")
        cache.put("prompt:shot_001:flux", '{"prompt":"..."}')
        value = cache.get("prompt:shot_001:flux")
        cache.put_file("image:abc123", "/tmp/gen_001.png")
        path = cache.get_file("image:abc123")
    """

    def __init__(self, db_path: str, file_cache_dir: str = ""):
        self.db_path = db_path
        self.file_cache_dir = file_cache_dir

        if file_cache_dir:
            Path(file_cache_dir).mkdir(parents=True, exist_ok=True)

        self._init_db()

    def _init_db(self):
        """Create cache tables if they don't exist."""
        conn = sqlite3.connect(self.db_path)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS cache (
                key TEXT PRIMARY KEY,
                value TEXT,
                metadata_json TEXT,
                created_at REAL,
                accessed_at REAL,
                hit_count INTEGER DEFAULT 0
            )
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_cache_accessed
            ON cache(accessed_at)
        """)
        conn.commit()
        conn.close()

    # ── Basic KV operations ──────────────────────────────────

    def get(self, key: str) -> Optional[str]:
        """Get a value by key. Returns None on miss."""
        conn = sqlite3.connect(self.db_path)
        row = conn.execute(
            "SELECT value FROM cache WHERE key = ?", (key,)
        ).fetchone()
        if row:
            conn.execute(
                "UPDATE cache SET accessed_at = ?, hit_count = hit_count + 1 WHERE key = ?",
                (time.time(), key),
            )
            conn.commit()
        conn.close()
        return row[0] if row else None

    def put(self, key: str, value: str, metadata: Dict = None):
        """Store a key-value pair."""
        conn = sqlite3.connect(self.db_path)
        conn.execute(
            """INSERT OR REPLACE INTO cache
               (key, value, metadata_json, created_at, accessed_at)
               VALUES (?, ?, ?, ?, ?)""",
            (
                key,
                value,
                json.dumps(metadata or {}),
                time.time(),
                time.time(),
            ),
        )
        conn.commit()
        conn.close()

    def exists(self, key: str) -> bool:
        """Check if key exists."""
        conn = sqlite3.connect(self.db_path)
        row = conn.execute("SELECT 1 FROM cache WHERE key = ? LIMIT 1", (key,)).fetchone()
        conn.close()
        return row is not None

    def delete(self, key: str):
        """Remove a key."""
        conn = sqlite3.connect(self.db_path)
        conn.execute("DELETE FROM cache WHERE key = ?", (key,))
        conn.commit()
        conn.close()

    # ── File cache operations ────────────────────────────────

    def get_file(self, key: str) -> Optional[str]:
        """Get a cached file path. Returns path or None."""
        value = self.get(f"file:{key}")
        if not value:
            return None
        # value is the cached file path
        if os.path.isfile(value):
            return value
        # Stale: file deleted, clean up
        self.delete(f"file:{key}")
        return None

    def put_file(self, key: str, source_path: str) -> str:
        """Copy a file into cache and store the path.

        Returns the cached file path.
        """
        if not self.file_cache_dir:
            return source_path

        ext = os.path.splitext(source_path)[1]
        cache_name = f"{key.replace(':', '_').replace('/', '_')}{ext}"
        cache_path = os.path.join(self.file_cache_dir, cache_name)

        # Copy if not already there
        if not os.path.isfile(cache_path):
            import shutil
            shutil.copy2(source_path, cache_path)

        self.put(f"file:{key}", cache_path)
        return cache_path

    # ── Statistics ───────────────────────────────────────────

    def stats(self) -> Dict:
        """Return cache statistics."""
        conn = sqlite3.connect(self.db_path)
        total = conn.execute("SELECT COUNT(*) FROM cache").fetchone()[0]
        hits = conn.execute("SELECT COALESCE(SUM(hit_count), 0) FROM cache").fetchone()[0]
        conn.close()
        return {"total_entries": total, "total_hits": hits}

    def cleanup_expired(self, max_age_seconds: float = 86400 * 7):
        """Remove entries older than max_age_seconds (default: 7 days)."""
        cutoff = time.time() - max_age_seconds
        conn = sqlite3.connect(self.db_path)
        conn.execute("DELETE FROM cache WHERE accessed_at < ?", (cutoff,))
        deleted = conn.total_changes
        conn.commit()
        conn.close()
        return deleted


# ── Specialized cache classes ─────────────────────────────────


class PromptCache:
    """Cache for DecomposedPrompt objects.

    Key: shot_id + model name hash.
    """

    def __init__(self, cache: DualCache):
        self.cache = cache

    def _key(self, shot_id: str, model: str) -> str:
        return f"prompt:{shot_id}:{model}"

    def get(self, shot_id: str, model: str) -> Optional[str]:
        return self.cache.get(self._key(shot_id, model))

    def put(self, shot_id: str, model: str, prompt_json: str):
        self.cache.put(self._key(shot_id, model), prompt_json)


class ModelCache:
    """Cache for ComfyUI output images.

    Key: workflow hash → cached image path.
    """

    def __init__(self, cache: DualCache):
        self.cache = cache

    def _hash_workflow(self, workflow: dict) -> str:
        wf_str = json.dumps(workflow, sort_keys=True)
        return hashlib.sha256(wf_str.encode()).hexdigest()[:32]

    def get(self, workflow: dict) -> Optional[str]:
        key = self._hash_workflow(workflow)
        return self.cache.get_file(key)

    def put(self, workflow: dict, image_path: str) -> str:
        key = self._hash_workflow(workflow)
        return self.cache.put_file(key, image_path)


class SceneCache:
    """Cache for ScenePack sub-area images."""

    def __init__(self, cache: DualCache):
        self.cache = cache

    def _key(self, scene_id: str, sub_area: str, weather: str, time: str) -> str:
        return f"scene:{scene_id}:{sub_area}:{weather}:{time}"

    def get(self, scene_id: str, sub_area: str, weather: str, time: str) -> Optional[str]:
        return self.cache.get_file(self._key(scene_id, sub_area, weather, time))

    def put(self, scene_id: str, sub_area: str, weather: str, time: str, path: str):
        self.cache.put_file(self._key(scene_id, sub_area, weather, time), path)


class VideoCache:
    """Cache for generated video clips.

    Key: shot_id + motion_hash.
    """

    def __init__(self, cache: DualCache):
        self.cache = cache

    def _key(self, shot_id: str, motion_hash: str) -> str:
        return f"video:{shot_id}:{motion_hash}"

    def get(self, shot_id: str, motion_hash: str) -> Optional[str]:
        return self.cache.get_file(self._key(shot_id, motion_hash))

    def put(self, shot_id: str, motion_hash: str, video_path: str):
        self.cache.put_file(self._key(shot_id, motion_hash), video_path)


class AudioCache:
    """Cache for TTS audio files.

    Key: character_id + text hash.
    """

    def __init__(self, cache: DualCache):
        self.cache = cache

    def _key(self, character_id: str, text: str) -> str:
        text_hash = hashlib.sha256(text.encode()).hexdigest()[:16]
        return f"audio:{character_id}:{text_hash}"

    def get(self, character_id: str, text: str) -> Optional[str]:
        return self.cache.get_file(self._key(character_id, text))

    def put(self, character_id: str, text: str, audio_path: str):
        self.cache.put_file(self._key(character_id, text), audio_path)


class SubtitleCache:
    """Cache for generated SRT subtitles.

    Key: shot_id + text hash.
    """

    def __init__(self, cache: DualCache):
        self.cache = cache

    def _key(self, shot_id: str, text: str) -> str:
        text_hash = hashlib.sha256(text.encode()).hexdigest()[:16]
        return f"sub:{shot_id}:{text_hash}"

    def get(self, shot_id: str, text: str) -> Optional[str]:
        return self.cache.get(self._key(shot_id, text))

    def put(self, shot_id: str, text: str, srt_content: str):
        self.cache.put(self._key(shot_id, text), srt_content)


class CacheManager:
    """Centralized cache manager for the entire pipeline.

    Usage:
        mgr = CacheManager(base_dir="D:/AI_Manga_Studio/cache")
        prompt = mgr.prompt.get("shot_001", "flux_kontext")
        if not prompt:
            prompt = generate_prompt(...)
            mgr.prompt.put("shot_001", "flux_kontext", prompt)
    """

    def __init__(self, base_dir: str):
        Path(base_dir).mkdir(parents=True, exist_ok=True)

        db_path = os.path.join(base_dir, "cache.db")
        file_dir = os.path.join(base_dir, "files")

        dual = DualCache(db_path, file_dir)

        self.prompt = PromptCache(dual)
        self.model = ModelCache(dual)
        self.scene = SceneCache(dual)
        self.video = VideoCache(dual)
        self.audio = AudioCache(dual)
        self.subtitle = SubtitleCache(dual)
        self._dual = dual

    def stats(self) -> Dict:
        return self._dual.stats()
