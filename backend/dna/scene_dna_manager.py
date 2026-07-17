"""
V3.0 Layer 4 — Scene DNA Manager

Singleton registry for ScenePack definitions. All downstream modules
query this manager for scene backgrounds and spatial context.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Dict, List, Optional

from loguru import logger

from backend.dna.scene_dna import ScenePack


class SceneDNAManager:
    """Singleton registry for ScenePack instances.

    Usage:
        mgr = SceneDNAManager.instance()
        mgr.register_pack(ScenePack(...))
        bg = mgr.get_scene("villa_01", "大厅", "雨", "夜晚")
    """

    _instance: Optional["SceneDNAManager"] = None

    def __init__(self):
        self._packs: Dict[str, ScenePack] = {}

    @classmethod
    def instance(cls) -> "SceneDNAManager":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    # ── Registration ──────────────────────────────────────

    def register_pack(self, pack: ScenePack) -> None:
        """Register or update a scene pack."""
        self._packs[pack.scene_id] = pack
        logger.info(f"SceneDNA: Registered '{pack.name}' (id={pack.scene_id}, {len(pack.sub_areas)} sub-areas)")

    def register_many(self, packs: List[ScenePack]) -> None:
        for pack in packs:
            self.register_pack(pack)

    # ── Retrieval ─────────────────────────────────────────

    def get_pack(self, scene_id: str) -> Optional[ScenePack]:
        """Get full ScenePack by ID."""
        return self._packs.get(scene_id)

    def get_by_name(self, name: str) -> Optional[ScenePack]:
        """Find ScenePack by display name."""
        for pack in self._packs.values():
            if pack.name == name:
                return pack
        return None

    def get_all(self) -> Dict[str, ScenePack]:
        """Return all registered packs."""
        return dict(self._packs)

    def get_names(self) -> List[str]:
        """Return all registered scene names."""
        return [p.name for p in self._packs.values()]

    # ── Scene access ──────────────────────────────────────

    def get_scene(
        self,
        scene_id: str,
        sub_area_name: str = "",
        weather: str = "",
        time: str = "",
    ) -> str:
        """Get best matching background image path.

        Args:
            scene_id: ScenePack ID.
            sub_area_name: Sub-area within the scene (e.g., "大厅").
            weather: Weather condition (e.g., "雨", "雪").
            time: Time of day (e.g., "白天", "夜晚").

        Returns:
            Absolute path to background image, or "" if not found.
        """
        pack = self.get_pack(scene_id)
        return pack.get_scene(sub_area_name, weather, time) if pack else ""

    def get_sub_area(self, scene_id: str, sub_area_name: str) -> str:
        """Get default image path for a sub-area."""
        pack = self.get_pack(scene_id)
        return pack.get_sub_area(sub_area_name) if pack else ""

    def get_sub_areas(self, scene_id: str) -> Dict[str, str]:
        """Get all sub-area name → path mappings."""
        pack = self.get_pack(scene_id)
        return dict(pack.sub_areas) if pack else {}

    def get_lighting(self, scene_id: str) -> str:
        """Get default lighting description."""
        pack = self.get_pack(scene_id)
        return pack.default_lighting if pack else "自然光"

    def get_dimension(self, scene_id: str) -> str:
        """Get spatial dimension."""
        pack = self.get_pack(scene_id)
        return pack.dimension if pack else "large"

    # ── Prompt context ────────────────────────────────────

    def get_scene_prompt(self, scene_id: str, weather: str = "", time: str = "") -> str:
        """Build scene portion of generation prompt."""
        pack = self.get_pack(scene_id)
        if not pack:
            return ""
        parts = [f"{pack.name}"]
        if pack.architectural_style:
            parts.append(f"{pack.architectural_style} style")
        weather = weather or pack.default_weather
        time = time or pack.default_time
        parts.append(f"{weather} {time}")
        if pack.default_lighting:
            parts.append(pack.default_lighting)
        return ", ".join(parts)

    # ── Persistence ───────────────────────────────────────

    def save_to_json(self, json_path: str) -> None:
        """Export all scene packs to JSON."""
        data = {sid: pack.to_dict() for sid, pack in self._packs.items()}
        Path(json_path).parent.mkdir(parents=True, exist_ok=True)
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        logger.info(f"SceneDNA: Exported {len(data)} packs to {json_path}")

    def load_from_json(self, json_path: str) -> None:
        """Import scene packs from JSON."""
        if not os.path.isfile(json_path):
            logger.warning(f"SceneDNA: JSON not found: {json_path}")
            return
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        for sid, d in data.items():
            pack = ScenePack.from_dict(d)
            pack.scene_id = sid
            self._packs[sid] = pack
        logger.info(f"SceneDNA: Imported {len(data)} packs from {json_path}")

    def __len__(self) -> int:
        return len(self._packs)
