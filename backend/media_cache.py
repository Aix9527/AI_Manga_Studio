"""
AI Manga Studio Pro V1.0 — Content-Aware Cache

Hash-based cache for generated media. Same input → same output,
skipping expensive ComfyUI GPU inference entirely.

Cache layout:
  cache/
    characters/  角色名_<hash>.png    ← 角色参考图
    scenes/      场景名_<hash>.png    ← 场景背景
    shots/       <project>/<chapter>/<shot_id>_<hash>.png  ← 分镜图

Usage:
  cache = MediaCache()
  path = cache.get_or_generate(
      key="林凡_portrait",
      generator=lambda: generate_via_comfyui(林凡),
      category="characters",
  )
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from loguru import logger


class MediaCache:
    """Hash-based media cache with hit/miss tracking.

    Each cache entry is keyed by a content hash, ensuring
    identical inputs always produce identical cached outputs.
    """

    def __init__(self, cache_root: str = "") -> None:
        if cache_root:
            self.root = Path(cache_root)
        else:
            from backend.config import get_config
            cfg = get_config()
            self.root = Path(cfg.project.cache_path or "D:/AI_Manga_Studio/cache")

        self.root.mkdir(parents=True, exist_ok=True)

        # Subdirectories
        self.characters_dir = self.root / "characters"
        self.scenes_dir = self.root / "scenes"
        self.shots_dir = self.root / "shots"
        self.manifest_dir = self.root / "manifest"

        for d in [self.characters_dir, self.scenes_dir, self.shots_dir, self.manifest_dir]:
            d.mkdir(parents=True, exist_ok=True)

        # Stats
        self.hits: int = 0
        self.misses: int = 0
        self.saves: int = 0

        logger.info(f"MediaCache: Root = {self.root}")

    # ----------------------------------------------------------
    # Public API
    # ----------------------------------------------------------

    def get_or_generate(
        self,
        key: str,
        generator: Callable[[], str],
        category: str = "shots",
        metadata: Optional[Dict[str, Any]] = None,
        extension: str = ".png",
    ) -> Tuple[str, bool]:
        """Get cached file or generate and cache it.

        Args:
            key: Unique content key (e.g. "林凡_portrait_fullbody").
            generator: Callable that produces the file path.
            category: "characters" / "scenes" / "shots".
            metadata: Extra metadata to include in hash.
            extension: Output file extension.

        Returns:
            Tuple of (file_path, was_cache_hit).
        """
        # Build hash from key + metadata
        content_hash = self._hash(key, metadata)
        subdir = self._category_dir(category, metadata)
        cache_path = subdir / f"{self._safe_name(key)}_{content_hash}{extension}"

        # HIT: file already exists
        if cache_path.exists():
            self.hits += 1
            logger.info(f"MediaCache: HIT  {key} → {cache_path.name}")
            return str(cache_path), True

        # MISS: generate
        self.misses += 1
        logger.info(f"MediaCache: MISS {key} — generating...")

        generated_path = generator()

        if not generated_path or not os.path.exists(generated_path):
            raise RuntimeError(f"MediaCache: Generator failed for '{key}'")

        # Copy to cache
        shutil.copy2(generated_path, cache_path)
        self.saves += 1

        # Write manifest
        self._write_manifest(key, content_hash, category, metadata)

        logger.info(f"MediaCache: SAVED {key} → {cache_path.name}")
        return str(cache_path), False

    def get(self, key: str, category: str = "shots", metadata: Optional[Dict[str, Any]] = None) -> Optional[str]:
        """Check if item exists in cache.

        Returns:
            File path if cached, None otherwise.
        """
        content_hash = self._hash(key, metadata)
        subdir = self._category_dir(category, metadata)

        # Search for any file with this hash
        for f in subdir.glob(f"*_{content_hash}.*"):
            return str(f)

        return None

    def invalidate(self, key: str, category: str = "shots", metadata: Optional[Dict[str, Any]] = None) -> bool:
        """Remove a specific cached entry.

        Returns:
            True if any files were removed.
        """
        content_hash = self._hash(key, metadata)
        subdir = self._category_dir(category, metadata)
        removed = 0

        for f in subdir.glob(f"*_{content_hash}.*"):
            f.unlink()
            removed += 1

        if removed:
            logger.info(f"MediaCache: Invalidated {removed} files for '{key}'")
        return removed > 0

    def clear_category(self, category: str) -> int:
        """Clear all cached files in a category.

        Returns:
            Number of files removed.
        """
        subdir = self._category_dir(category)
        count = 0
        for f in subdir.iterdir():
            if f.is_file():
                f.unlink()
                count += 1

        logger.info(f"MediaCache: Cleared {count} files from {category}")
        return count

    def clear_all(self) -> int:
        """Clear entire cache.

        Returns:
            Number of files removed.
        """
        total = 0
        for category in ["characters", "scenes", "shots"]:
            total += self.clear_category(category)
        return total

    def stats(self) -> Dict[str, Any]:
        """Get cache statistics.

        Returns:
            Dict with hits, misses, saves, and file counts.
        """
        file_counts = {}
        for cat in ["characters", "scenes", "shots"]:
            subdir = self._category_dir(cat)
            file_counts[cat] = len(list(subdir.glob("*")))

        return {
            "hits": self.hits,
            "misses": self.misses,
            "saves": self.saves,
            "hit_rate": f"{self.hits / max(1, self.hits + self.misses) * 100:.1f}%",
            "files": file_counts,
            "root": str(self.root),
        }

    # ----------------------------------------------------------
    # Character-specific helpers
    # ----------------------------------------------------------

    def get_character(
        self,
        name: str,
        pose: str = "fullbody",
        expression: str = "neutral",
    ) -> Optional[str]:
        """Get cached character reference image.

        Args:
            name: Character name (e.g. "林凡").
            pose: Pose type.
            expression: Expression.

        Returns:
            Cached path or None.
        """
        key = f"{name}_{pose}_{expression}"
        metadata = {"name": name, "pose": pose, "expression": expression}
        return self.get(key, "characters", metadata)

    def cache_character(
        self,
        name: str,
        generated_path: str,
        pose: str = "fullbody",
        expression: str = "neutral",
        generator: Optional[Callable[[], str]] = None,
    ) -> Optional[str]:
        """Cache a character image or regenerate it."""
        key = f"{name}_{pose}_{expression}"
        metadata = {"name": name, "pose": pose, "expression": expression}

        if generated_path and os.path.exists(generated_path):
            return self._copy_to_cache(key, generated_path, "characters", metadata)

        if generator:
            path, _ = self.get_or_generate(key, generator, "characters", metadata)
            return path

        return None

    def get_scene(
        self,
        name: str,
        weather: str = "clear",
        time_of_day: str = "day",
    ) -> Optional[str]:
        """Get cached scene background."""
        key = f"{name}_{weather}_{time_of_day}"
        metadata = {"name": name, "weather": weather, "time_of_day": time_of_day}
        return self.get(key, "scenes", metadata)

    def cache_scene(
        self,
        name: str,
        generated_path: str,
        weather: str = "clear",
        time_of_day: str = "day",
    ) -> Optional[str]:
        """Cache a scene background."""
        key = f"{name}_{weather}_{time_of_day}"
        metadata = {"name": name, "weather": weather, "time_of_day": time_of_day}
        return self._copy_to_cache(key, generated_path, "scenes", metadata)

    def get_shot(
        self,
        project_id: str,
        chapter: int,
        shot_id: str,
        prompt_hash: str = "",
    ) -> Optional[str]:
        """Get cached shot image."""
        key = f"{project_id}/ch{chapter:02d}/{shot_id}"
        metadata = {
            "project": project_id,
            "chapter": chapter,
            "shot_id": shot_id,
            "prompt_hash": prompt_hash,
        }
        return self.get(key, "shots", metadata)

    def cache_shot(
        self,
        project_id: str,
        chapter: int,
        shot_id: str,
        generated_path: str,
        prompt_hash: str = "",
    ) -> Optional[str]:
        """Cache a shot image."""
        key = f"{project_id}/ch{chapter:02d}/{shot_id}"
        metadata = {
            "project": project_id,
            "chapter": chapter,
            "shot_id": shot_id,
            "prompt_hash": prompt_hash,
        }
        return self._copy_to_cache(key, generated_path, "shots", metadata)

    # ----------------------------------------------------------
    # Internal
    # ----------------------------------------------------------

    def _hash(self, key: str, metadata: Optional[Dict[str, Any]] = None) -> str:
        """Compute content hash from key + metadata."""
        data = key
        if metadata:
            data += json.dumps(metadata, sort_keys=True, ensure_ascii=False)
        return hashlib.md5(data.encode("utf-8")).hexdigest()[:12]

    @staticmethod
    def _safe_name(key: str) -> str:
        """Convert key to safe filename."""
        return key.replace("/", "_").replace("\\", "_").replace(" ", "_")[:60]

    def _category_dir(self, category: str, metadata: Optional[Dict] = None) -> Path:
        """Get subdirectory for a category."""
        if category == "characters":
            return self.characters_dir
        elif category == "scenes":
            return self.scenes_dir
        elif category == "shots":
            if metadata and metadata.get("project"):
                sub = self.shots_dir / self._safe_name(metadata["project"])
                sub.mkdir(parents=True, exist_ok=True)
                return sub
            return self.shots_dir
        return self.root / category

    def _copy_to_cache(
        self,
        key: str,
        source_path: str,
        category: str,
        metadata: Optional[Dict] = None,
    ) -> str:
        """Copy an already-generated file into the cache."""
        content_hash = self._hash(key, metadata)
        subdir = self._category_dir(category, metadata)
        ext = os.path.splitext(source_path)[1] or ".png"
        cache_path = subdir / f"{self._safe_name(key)}_{content_hash}{ext}"

        shutil.copy2(source_path, cache_path)
        self.saves += 1
        self._write_manifest(key, content_hash, category, metadata)
        logger.info(f"MediaCache: Cached {key} → {cache_path.name}")
        return str(cache_path)

    def _write_manifest(
        self,
        key: str,
        content_hash: str,
        category: str,
        metadata: Optional[Dict] = None,
    ) -> None:
        """Write a manifest entry for tracking."""
        entry = {
            "key": key,
            "hash": content_hash,
            "category": category,
            "metadata": metadata or {},
        }
        manifest_path = self.manifest_dir / f"{content_hash}.json"
        with open(manifest_path, "w", encoding="utf-8") as f:
            json.dump(entry, f, ensure_ascii=False, indent=2)


# ----------------------------------------------------------
# Singleton
# ----------------------------------------------------------

_cache: Optional[MediaCache] = None


def get_cache() -> MediaCache:
    """Get or create the global media cache."""
    global _cache
    if _cache is None:
        _cache = MediaCache()
    return _cache
