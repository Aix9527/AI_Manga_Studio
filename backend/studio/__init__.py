"""
Studio OS — Global asset intelligence & open ecosystem (Part 36)

Provides the Studio-level operating layer above individual projects:
- Global asset registry with cross-project intelligence
- Style library with reusable visual templates
- Studio-wide settings and preferences
- Open ecosystem bridge (marketplace, community)
- Meta-workflow for multi-project orchestration
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class AssetCategory(str, Enum):
    CHARACTER = "character"
    BACKGROUND = "background"
    PROP = "prop"
    EFFECT = "effect"
    UI = "ui"
    TEMPLATE = "template"


@dataclass
class GlobalAsset:
    """
    A globally shared asset accessible across projects.

    Unlike project-scoped assets, these can be referenced
    by any project within the studio.
    """
    asset_id: str = ""
    name: str = ""
    category: AssetCategory = AssetCategory.CHARACTER
    tags: list[str] = field(default_factory=list)
    file_path: str = ""
    thumbnail_path: str = ""
    preview_path: str = ""
    source_project_id: str = ""  # Which project this originated from
    usage_count: int = 0
    rating: float = 0.0
    created_at: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class StylePreset:
    """A reusable visual style preset."""
    style_id: str = ""
    name: str = ""
    description: str = ""
    category: str = ""  # anime/realistic/comic/painterly/pixel
    prompt_prefix: str = ""
    prompt_suffix: str = ""
    negative_prompt: str = ""
    default_width: int = 1024
    default_height: int = 1024
    reference_images: list[str] = field(default_factory=list)
    color_palette: list[str] = field(default_factory=list)
    is_builtin: bool = False


# ── Global Asset Registry ─────────────────────────────────────────────

class GlobalAssetRegistry:
    """
    Cross-project asset intelligence.

    Tracks all assets across all projects, enabling:
    - Duplicate detection (same character reused across projects)
    - Style similarity matching
    - Asset sharing between projects
    """

    def __init__(self) -> None:
        self._assets: dict[str, GlobalAsset] = {}
        self._by_tag: dict[str, list[str]] = {}  # tag -> [asset_id, ...]

    def register(self, asset: GlobalAsset) -> None:
        self._assets[asset.asset_id] = asset
        for tag in asset.tags:
            if tag not in self._by_tag:
                self._by_tag[tag] = []
            self._by_tag[tag].append(asset.asset_id)

    def search(self, tags: list[str], category: AssetCategory | None = None) -> list[GlobalAsset]:
        """Search assets by tags and optional category."""
        candidates: set[str] = set()
        for tag in tags:
            candidates.update(self._by_tag.get(tag, []))

        results = []
        for aid in candidates:
            asset = self._assets.get(aid)
            if asset and (category is None or asset.category == category):
                results.append(asset)

        return sorted(results, key=lambda a: a.usage_count, reverse=True)

    def get_popular(self, limit: int = 20) -> list[GlobalAsset]:
        """Get most-used assets across all projects."""
        sorted_assets = sorted(self._assets.values(), key=lambda a: a.usage_count, reverse=True)
        return sorted_assets[:limit]


# ── Style Library ─────────────────────────────────────────────────────

class StyleLibrary:
    """Centralized style management for the entire studio."""

    def __init__(self) -> None:
        self._styles: dict[str, StylePreset] = {}
        self._register_builtins()

    def _register_builtins(self) -> None:
        """Register built-in style presets."""
        builtins = [
            StylePreset(
                style_id="anime_cinematic",
                name="Anime Cinematic",
                category="anime",
                description="High-quality anime cinematic style",
                prompt_prefix="masterpiece, best quality, cinematic anime",
                negative_prompt="low quality, 3d, realistic, photograph",
                is_builtin=True,
            ),
            StylePreset(
                style_id="manga_bw",
                name="Manga Black & White",
                category="comic",
                description="Classic black and white manga style with screentones",
                prompt_prefix="manga style, black and white, screentones, hatching",
                negative_prompt="color, 3d, realistic, photograph",
                is_builtin=True,
            ),
            StylePreset(
                style_id="comic_color",
                name="Color Comic",
                category="comic",
                description="Vibrant color comic book style",
                prompt_prefix="comic book style, vibrant colors, bold outlines",
                negative_prompt="3d, realistic, photograph, blurry",
                is_builtin=True,
            ),
            StylePreset(
                style_id="ghibli",
                name="Studio Ghibli Style",
                category="anime",
                description="Soft, painterly anime style inspired by Ghibli",
                prompt_prefix="studio ghibli style, soft colors, detailed background, hand-drawn",
                negative_prompt="3d, realistic, photograph, dark, gritty",
                is_builtin=True,
            ),
        ]
        for style in builtins:
            self._styles[style.style_id] = style

    def register(self, style: StylePreset) -> None:
        self._styles[style.style_id] = style

    def get(self, style_id: str) -> StylePreset | None:
        return self._styles.get(style_id)

    def list_by_category(self, category: str) -> list[StylePreset]:
        return [s for s in self._styles.values() if s.category == category]

    def list_all(self) -> list[StylePreset]:
        return list(self._styles.values())


# ── Studio Manager ────────────────────────────────────────────────────

class StudioManager:
    """
    Top-level studio orchestrator.

    Manages:
    - Global asset registry
    - Style library
    - Studio-wide settings
    - Ecosystem bridge (plugin marketplace, community templates)
    """

    def __init__(self) -> None:
        self.asset_registry = GlobalAssetRegistry()
        self.style_library = StyleLibrary()
        self._settings: dict[str, Any] = {
            "default_fps": 24,
            "default_resolution": {"width": 1920, "height": 1080},
            "default_style": "anime_cinematic",
            "enable_telemetry": False,
            "auto_backup": True,
        }

    def get_setting(self, key: str, default: Any = None) -> Any:
        return self._settings.get(key, default)

    def update_settings(self, **kwargs: Any) -> None:
        self._settings.update(kwargs)

    def suggest_style(self, project_description: str) -> list[StylePreset]:
        """Suggest styles based on project description."""
        keywords = project_description.lower()

        if any(k in keywords for k in ("action", "shounen", "battle")):
            return [self.style_library.get("anime_cinematic"),
                    self.style_library.get("comic_color")]
        elif any(k in keywords for k in ("romance", "slice of life", "drama")):
            return [self.style_library.get("ghibli"),
                    self.style_library.get("anime_cinematic")]
        elif any(k in keywords for k in ("horror", "thriller", "noir")):
            return [self.style_library.get("manga_bw")]
        else:
            return self.style_library.list_all()

    def get_or_create_asset(
        self,
        name: str,
        category: AssetCategory,
        **kwargs: Any,
    ) -> GlobalAsset:
        """Find or create a global asset."""
        # Search existing
        for asset in self.asset_registry.search([name], category):
            if asset.name == name:
                asset.usage_count += 1
                return asset

        # Create new
        asset = GlobalAsset(
            asset_id=f"{category.value}_{name.lower().replace(' ', '_')}",
            name=name,
            category=category,
            **kwargs,
        )
        self.asset_registry.register(asset)
        return asset


# Global studio instance
studio = StudioManager()
