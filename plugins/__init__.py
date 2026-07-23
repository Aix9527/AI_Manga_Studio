"""
AI Manga Studio Pro V1.0 — Plugin Registry

Central plugin loader and registry. Handles discovery, loading,
and lifecycle management of all plugins.

Usage:
    from plugins import PluginRegistry

    registry = PluginRegistry()
    image_plugin = registry.get_image_plugin("flux")
    result = image_plugin.generate(shot)
"""

from __future__ import annotations

import importlib
import os
from typing import Any, Dict, Optional, Type

from loguru import logger

from plugins.base import (
    ImagePlugin,
    MusicPlugin,
    QualityPlugin,
    SubtitlePlugin,
    TTSPlugin,
    VideoPlugin,
)


# ------------------------------------------------------------
# Plugin Metadata
# ------------------------------------------------------------

PLUGIN_DIRS: Dict[str, str] = {
    "image": "flux",
    "video": "wan",
    "tts": "tts",
    "subtitle": "subtitle",
    "music": "music",
    "quality": "quality",
}

PLUGIN_BASE_CLASSES: Dict[str, Type] = {
    "image": ImagePlugin,
    "video": VideoPlugin,
    "tts": TTSPlugin,
    "subtitle": SubtitlePlugin,
    "music": MusicPlugin,
    "quality": QualityPlugin,
}

# Each plugin's module name under plugins/<name>/
PLUGIN_MODULE_NAME: str = "plugin"
PLUGIN_CLASS_NAME: str = "Plugin"


# ------------------------------------------------------------
# Plugin Registry
# ------------------------------------------------------------

class PluginRegistry:
    """Central registry for all plugins.

    Loads plugins lazily on first access. Each plugin type
    has a default plugin name (configurable).
    """

    def __init__(self, base_path: str = "") -> None:
        """Initialize registry.

        Args:
            base_path: Root path for plugins directory.
                       Defaults to ../plugins relative to this file.
        """
        if not base_path:
            base_path = os.path.dirname(os.path.abspath(__file__))
        self._base_path = base_path
        self._instances: Dict[str, Any] = {}
        self._active: Dict[str, str] = dict(PLUGIN_DIRS)

    # ----------------------------------------------------------
    # Plugin Accessors
    # ----------------------------------------------------------

    def get_image_plugin(self, name: str = "") -> ImagePlugin:
        """Get active image generation plugin."""
        return self._load("image", name or self._active.get("image", "flux"))

    def get_video_plugin(self, name: str = "") -> VideoPlugin:
        """Get active video generation plugin."""
        return self._load("video", name or self._active.get("video", "wan"))

    def get_tts_plugin(self, name: str = "") -> TTSPlugin:
        """Get active TTS plugin."""
        return self._load("tts", name or self._active.get("tts", "tts"))

    def get_subtitle_plugin(self, name: str = "") -> SubtitlePlugin:
        """Get active subtitle plugin."""
        return self._load("subtitle", name or self._active.get("subtitle", "subtitle"))

    def get_music_plugin(self, name: str = "") -> MusicPlugin:
        """Get active music plugin."""
        return self._load("music", name or self._active.get("music", "music"))

    def get_quality_plugin(self, name: str = "") -> QualityPlugin:
        """Get active quality plugin."""
        return self._load("quality", name or self._active.get("quality", "quality"))

    # ----------------------------------------------------------
    # Plugin Management
    # ----------------------------------------------------------

    def set_active(self, plugin_type: str, plugin_name: str) -> bool:
        """Switch active plugin for a type.

        Args:
            plugin_type: 'image' / 'video' / 'tts' / etc.
            plugin_name: Plugin directory name.

        Returns:
            True if switched successfully.
        """
        if plugin_type not in PLUGIN_DIRS:
            logger.error(f"PluginRegistry: Unknown plugin type '{plugin_type}'")
            return False

        plugin_path = os.path.join(self._base_path, plugin_name)
        if not os.path.isdir(plugin_path):
            logger.error(f"PluginRegistry: Plugin dir not found: {plugin_path}")
            return False

        # Clear cached instance so it reloads
        cache_key = f"{plugin_type}:{plugin_name}"
        self._instances.pop(cache_key, None)
        self._active[plugin_type] = plugin_name

        logger.info(
            f"PluginRegistry: Switched {plugin_type} → {plugin_name}"
        )
        return True

    def list_plugins(self, plugin_type: str = "") -> Dict[str, list]:
        """List all available plugins.

        Args:
            plugin_type: Filter by type. Empty = all.

        Returns:
            Dict of type → list of plugin names.
        """
        if plugin_type:
            return self._discover(plugin_type)

        result = {}
        for ptype in PLUGIN_DIRS:
            result[ptype] = self._discover(ptype).get(ptype, [])
        return result

    # ----------------------------------------------------------
    # Internal: Plugin Loading
    # ----------------------------------------------------------

    def _discover(self, plugin_type: str) -> Dict[str, list]:
        """Discover plugin directories for a type."""
        names = []
        type_dir = os.path.join(self._base_path, plugin_type)
        if os.path.isdir(type_dir):
            for entry in os.listdir(self._base_path):
                entry_path = os.path.join(self._base_path, entry)
                if os.path.isdir(entry_path) and not entry.startswith("_"):
                    # Check if it has plugin.py
                    if os.path.exists(os.path.join(entry_path, "plugin.py")):
                        names.append(entry)
        return {plugin_type: names}

    def _load(self, plugin_type: str, plugin_name: str) -> Any:
        """Load a plugin instance (cached).

        Args:
            plugin_type: Plugin type string.
            plugin_name: Plugin directory name.

        Returns:
            Plugin instance.
        """
        cache_key = f"{plugin_type}:{plugin_name}"

        if cache_key in self._instances:
            return self._instances[cache_key]

        # Build module path: plugins.<name>.plugin
        module_path = f"plugins.{plugin_name}.{PLUGIN_MODULE_NAME}"

        try:
            module = importlib.import_module(module_path)
            plugin_class = getattr(module, PLUGIN_CLASS_NAME)
            instance = plugin_class()

            # Validate it implements the correct base class
            base_class = PLUGIN_BASE_CLASSES.get(plugin_type)
            if base_class and isinstance(instance, base_class):
                logger.info(
                    f"PluginRegistry: Loaded {plugin_type}/{plugin_name}"
                )
            else:
                logger.warning(
                    f"PluginRegistry: {plugin_name}.Plugin does not "
                    f"inherit {base_class.__name__ if base_class else '?'}"
                )

            self._instances[cache_key] = instance
            return instance

        except ImportError as e:
            logger.error(
                f"PluginRegistry: Failed to import {module_path}: {e}"
            )
            raise
        except AttributeError:
            logger.error(
                f"PluginRegistry: {module_path} has no class '{PLUGIN_CLASS_NAME}'"
            )
            raise

    def reload(self) -> None:
        """Clear all cached plugin instances."""
        self._instances.clear()
        logger.info("PluginRegistry: All plugins reloaded")


# ------------------------------------------------------------
# Singleton
# ------------------------------------------------------------

_registry: Optional[PluginRegistry] = None


def get_registry() -> PluginRegistry:
    """Get or create the global plugin registry."""
    global _registry
    if _registry is None:
        _registry = PluginRegistry()
    return _registry


def reset_registry() -> None:
    """Reset the global registry (for testing)."""
    global _registry
    _registry = None
