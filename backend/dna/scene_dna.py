"""
V3.0 Layer 4 — Scene DNA (Scene Pack)

Scene identity with sub-areas, weather & time variants, and spatial metadata.
Each ScenePack acts as a multi-layer background lookup table.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class ScenePack:
    """Complete scene definition with sub-areas and variants.

    A ScenePack represents one location (e.g., "别墅") with:
      - Multiple sub-areas (e.g., 大厅, 门口, 书房, 花园)
      - Weather variants per sub-area (晴, 雨, 雪, 雾)
      - Time variants per sub-area (白天, 黄昏, 夜晚)
      - Spatial metadata for composition guidance
    """

    scene_id: str
    name: str                                   # Display name: "别墅"

    # ── Sub-scene spatial data ─────────────────────────────
    sub_scenes: List[str] = field(default_factory=list)
    # Ordered sub-scene names, e.g. ["入口", "大厅", "楼梯", "客厅", "走廊"]
    spatial_map: Dict[str, str] = field(default_factory=dict)
    # Sub-area → description mapping, e.g. {"大厅": "grand hall with chandelier"}

    # ── Sub-area Maps ─────────────────────────────────────
    sub_areas: Dict[str, str] = field(default_factory=dict)
    # {"大厅": "path/to/hall.png", "门口": "path/to/entrance.png", ...}

    # ── Variant Maps ──────────────────────────────────────
    weather_variants: Dict[str, Dict[str, str]] = field(default_factory=dict)
    # {"雨": {"大厅": "path/to/hall_rain.png", "门口": "path/to/entrance_rain.png"}}

    time_variants: Dict[str, Dict[str, str]] = field(default_factory=dict)
    # {"夜晚": {"大厅": "path/to/hall_night.png", "门口": "path/to/entrance_night.png"}}

    # ── Variant combos (weather + time) ───────────────────
    combo_variants: Dict[str, Dict[str, str]] = field(default_factory=dict)
    # {"雨_夜晚": {"大厅": "path/to/hall_rain_night.png"}}

    # ── Spatial Metadata ──────────────────────────────────
    default_weather: str = "晴天"
    default_time: str = "白天"
    default_lighting: str = "自然光"
    dimension: str = "large"              # small/medium/large/vast
    orientation: str = "horizontal"       # horizontal/vertical
    depth_layers: int = 3                 # foreground/midground/background

    # ── Visual Metadata ───────────────────────────────────
    color_palette: str = ""               # Dominant color palette
    architectural_style: str = ""         # 现代/古典/哥特/日式/...
    key_features: list[str] = field(default_factory=list)
    # Landmarks or distinctive elements

    def get_sub_area(self, sub_area_name: str) -> str:
        """Get the default image path for a sub-area."""
        return self.sub_areas.get(sub_area_name, "")

    def get_scene(
        self,
        sub_area_name: str = "",
        weather: str = "",
        time: str = "",
    ) -> str:
        """Get the best matching image path for sub-area + weather + time.

        Fallback chain:
          1. combo_variants[weather_time][sub_area]
          2. weather_variants[weather][sub_area]
          3. time_variants[time][sub_area]
          4. sub_areas[sub_area]
          5. ""
        """
        weather = weather or self.default_weather
        time = time or self.default_time
        sub_area_name = sub_area_name or list(self.sub_areas.keys())[0] if self.sub_areas else ""

        # Combo variant (weather + time)
        combo_key = f"{weather}_{time}"
        if combo_key in self.combo_variants and sub_area_name in self.combo_variants[combo_key]:
            return self.combo_variants[combo_key][sub_area_name]

        # Weather variant
        if weather in self.weather_variants and sub_area_name in self.weather_variants[weather]:
            return self.weather_variants[weather][sub_area_name]

        # Time variant
        if time in self.time_variants and sub_area_name in self.time_variants[time]:
            return self.time_variants[time][sub_area_name]

        # Default sub-area
        return self.sub_areas.get(sub_area_name, "")

    def get_all_for_weather_time(self, weather: str, time: str) -> Dict[str, str]:
        """Get all sub-area paths for a given weather + time combo."""
        result: Dict[str, str] = {}
        for area_name in self.sub_areas:
            path = self.get_scene(area_name, weather, time)
            if path:
                result[area_name] = path
        return result

    def to_dict(self) -> dict:
        return {
            "scene_id": self.scene_id,
            "name": self.name,
            "sub_scenes": self.sub_scenes,
            "spatial_map": self.spatial_map,
            "sub_areas": self.sub_areas,
            "weather_variants": self.weather_variants,
            "time_variants": self.time_variants,
            "combo_variants": self.combo_variants,
            "default_weather": self.default_weather,
            "default_time": self.default_time,
            "default_lighting": self.default_lighting,
            "dimension": self.dimension,
            "orientation": self.orientation,
            "depth_layers": self.depth_layers,
            "color_palette": self.color_palette,
            "architectural_style": self.architectural_style,
            "key_features": self.key_features,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ScenePack":
        return cls(
            scene_id=data.get("scene_id", ""),
            name=data.get("name", ""),
            sub_scenes=data.get("sub_scenes", []),
            spatial_map=data.get("spatial_map", {}),
            sub_areas=data.get("sub_areas", {}),
            weather_variants=data.get("weather_variants", {}),
            time_variants=data.get("time_variants", {}),
            combo_variants=data.get("combo_variants", {}),
            default_weather=data.get("default_weather", "晴天"),
            default_time=data.get("default_time", "白天"),
            default_lighting=data.get("default_lighting", "自然光"),
            dimension=data.get("dimension", "large"),
            orientation=data.get("orientation", "horizontal"),
            depth_layers=data.get("depth_layers", 3),
            color_palette=data.get("color_palette", ""),
            architectural_style=data.get("architectural_style", ""),
            key_features=data.get("key_features", []),
        )
