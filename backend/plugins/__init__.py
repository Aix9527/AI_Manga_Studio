"""
Plugin SDK & Extension Architecture (Part 18)

Defines the plugin lifecycle, extension points, and SDK
for third-party developers to extend AI_Manga_Studio.

Architecture:
- PluginBase: abstract lifecycle interface
- PluginManager: registry, loading, activation, deactivation
- PluginManifest: metadata and dependency declaration
- Extension Points: hooks for customizing pipeline stages
- SDK: public API surface for plugin authors
"""

from __future__ import annotations

import importlib
import importlib.util
import json
import logging
import os
import sys
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable, ClassVar

logger = logging.getLogger(__name__)


# ── Plugin Lifecycle ───────────────────────────────────────────────────


class PluginState(Enum):
    """Plugin lifecycle states."""

    DISCOVERED = "discovered"
    LOADED = "loaded"
    INITIALIZED = "initialized"
    ACTIVATED = "activated"
    DEACTIVATED = "deactivated"
    ERROR = "error"
    DISABLED = "disabled"


@dataclass
class PluginManifest:
    """Plugin metadata and dependency declaration."""

    name: str
    version: str
    description: str = ""
    author: str = ""
    license_type: str = "MIT"

    # Dependencies
    requires: list[str] = field(default_factory=list)  # Plugin names
    min_studio_version: str = "1.0.0"

    # Extension points this plugin hooks into
    hooks: list[str] = field(default_factory=list)

    # Configuration schema
    config_schema: dict[str, Any] = field(default_factory=dict)

    # Entry point
    entry_point: str = ""  # "module:class" or "module:method"

    @classmethod
    def from_json(cls, path: str) -> PluginManifest:
        """Load manifest from a manifest.json file."""
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return cls(**data)


# ── Plugin Base Class ──────────────────────────────────────────────────


class PluginBase(ABC):
    """
    Abstract base for all plugins.

    Lifecycle:
    1. __init__()  -- Python-level instantiation
    2. initialize() -- One-time setup (register hooks, load config)
    3. activate()   -- Start processing, subscribe to events
    4. deactivate() -- Stop processing, unsubscribe
    5. shutdown()   -- Clean up resources
    """

    manifest: PluginManifest
    state: PluginState = PluginState.DISCOVERED
    plugin_dir: str = ""

    def __init__(self) -> None:
        self.state = PluginState.LOADED

    @abstractmethod
    async def initialize(self, context: dict[str, Any]) -> bool:
        """
        Initialize the plugin with the studio context.

        Args:
            context: Studio context with registry, config, etc.

        Returns:
            True if initialization succeeded
        """
        ...

    @abstractmethod
    async def activate(self) -> bool:
        """
        Activate the plugin (start processing, subscribe to events).

        Returns:
            True if activation succeeded
        """
        ...

    @abstractmethod
    async def deactivate(self) -> bool:
        """
        Deactivate the plugin (stop processing, unsubscribe).

        Returns:
            True if deactivation succeeded
        """
        ...

    @abstractmethod
    async def shutdown(self) -> None:
        """Final cleanup before unloading."""
        ...

    def get_config(self) -> dict[str, Any]:
        """Return the current plugin configuration."""
        return {}

    def update_config(self, config: dict[str, Any]) -> None:
        """Update plugin configuration at runtime."""
        pass


# ── Extension Points ───────────────────────────────────────────────────


class ExtensionPoint(ABC):
    """
    Base class for extension points that plugins can hook into.

    Extension points are the "hooks" where plugins can inject
    custom behavior into the studio pipeline.
    """

    point_name: ClassVar[str] = ""

    @abstractmethod
    async def execute(
        self, context: dict[str, Any], **kwargs: Any
    ) -> dict[str, Any]:
        """
        Execute all registered handlers for this extension point.

        Args:
            context: Pipeline context with shared state
            **kwargs: Extension-specific parameters

        Returns:
            Aggregated results from all handlers
        """
        ...

    def register(self, handler: Callable[..., Any], priority: int = 0) -> None:
        """Register a handler for this extension point."""
        pass

    def unregister(self, handler: Callable[..., Any]) -> None:
        """Unregister a handler."""
        pass


class PipelineStageExtension(ExtensionPoint):
    """
    Extension point for hooking into pipeline stages.

    Plugins can register pre-stage and post-stage hooks
    for any pipeline stage (story_parsing, image_generation, etc.).
    """

    point_name = "pipeline_stage"


class AssetProcessingExtension(ExtensionPoint):
    """
    Extension point for custom asset processing.

    Plugins can register custom image/video/audio processors
    that plug into the asset pipeline.
    """

    point_name = "asset_processing"


class ExportFormatExtension(ExtensionPoint):
    """
    Extension point for custom export formats.

    Plugins can add new export format handlers.
    """

    point_name = "export_format"


class UIComponentExtension(ExtensionPoint):
    """
    Extension point for custom UI components.

    Plugins can register React components for the frontend.
    """

    point_name = "ui_component"


class ProviderExtension(ExtensionPoint):
    """
    Extension point for custom AI providers.

    Plugins can register new LLM, image, video, or audio providers.
    """

    point_name = "provider"


# ── Plugin Manager ─────────────────────────────────────────────────────


class PluginManager:
    """
    Plugin lifecycle manager.

    Responsibilities:
    - Discover plugins from plugin directories
    - Load and validate manifests
    - Initialize, activate, deactivate, shutdown plugins
    - Manage plugin dependencies and ordering
    - Handle plugin errors gracefully
    """

    def __init__(self, plugin_dir: str = "") -> None:
        self.plugin_dir = plugin_dir or os.path.join(
            os.path.dirname(__file__), "..", "plugins"
        )
        self._plugins: dict[str, PluginBase] = {}
        self._manifests: dict[str, PluginManifest] = {}
        self._loaded_modules: dict[str, Any] = {}

    async def discover(self) -> list[PluginManifest]:
        """
        Discover all plugins in the plugin directory.

        Each plugin must be in its own subdirectory with a manifest.json.
        """
        if not os.path.isdir(self.plugin_dir):
            logger.warning(f"Plugin directory not found: {self.plugin_dir}")
            return []

        manifests = []
        for entry in os.listdir(self.plugin_dir):
            plugin_path = os.path.join(self.plugin_dir, entry)
            manifest_path = os.path.join(plugin_path, "manifest.json")

            if not os.path.isdir(plugin_path):
                continue
            if not os.path.isfile(manifest_path):
                logger.debug(f"No manifest in {plugin_path}, skipping")
                continue

            try:
                manifest = PluginManifest.from_json(manifest_path)
                self._manifests[manifest.name] = manifest
                manifests.append(manifest)
                logger.info(f"Discovered plugin: {manifest.name} v{manifest.version}")
            except Exception as e:
                logger.error(f"Failed to load manifest from {manifest_path}: {e}")

        return manifests

    async def load(self, plugin_name: str) -> PluginBase | None:
        """
        Load a single plugin by name.

        Steps:
        1. Find the plugin directory
        2. Import the module
        3. Instantiate the plugin class
        """
        if plugin_name in self._plugins:
            return self._plugins[plugin_name]

        manifest = self._manifests.get(plugin_name)
        if not manifest:
            logger.error(f"Plugin not discovered: {plugin_name}")
            return None

        plugin_path = os.path.join(self.plugin_dir, plugin_name)
        sys.path.insert(0, plugin_path)

        try:
            # Import the module
            module = importlib.import_module(plugin_name)
            self._loaded_modules[plugin_name] = module

            # Find the plugin class (by naming convention: <Name>Plugin)
            plugin_class = None
            for attr_name in dir(module):
                attr = getattr(module, attr_name)
                if (
                    isinstance(attr, type)
                    and issubclass(attr, PluginBase)
                    and attr != PluginBase
                ):
                    plugin_class = attr
                    break

            if not plugin_class:
                logger.error(f"No PluginBase subclass found in {plugin_name}")
                return None

            # Instantiate
            plugin: PluginBase = plugin_class()
            plugin.manifest = manifest
            plugin.plugin_dir = plugin_path
            self._plugins[plugin_name] = plugin
            plugin.state = PluginState.LOADED

            logger.info(f"Loaded plugin: {plugin_name}")
            return plugin

        except Exception as e:
            logger.error(f"Failed to load plugin {plugin_name}: {e}", exc_info=True)
            return None
        finally:
            if plugin_path in sys.path:
                sys.path.remove(plugin_path)

    async def initialize(
        self, plugin_name: str, context: dict[str, Any]
    ) -> bool:
        """Initialize a loaded plugin with studio context."""
        plugin = self._plugins.get(plugin_name) or await self.load(plugin_name)
        if not plugin:
            return False

        try:
            success = await plugin.initialize(context)
            if success:
                plugin.state = PluginState.INITIALIZED
                logger.info(f"Initialized plugin: {plugin_name}")
            else:
                plugin.state = PluginState.ERROR
            return success
        except Exception as e:
            logger.error(f"Error initializing plugin {plugin_name}: {e}")
            plugin.state = PluginState.ERROR
            return False

    async def activate(self, plugin_name: str) -> bool:
        """Activate a plugin (start processing)."""
        plugin = self._plugins.get(plugin_name)
        if not plugin:
            logger.error(f"Plugin not loaded: {plugin_name}")
            return False
        if plugin.state != PluginState.INITIALIZED:
            logger.error(
                f"Plugin not initialized (state={plugin.state.value}): {plugin_name}"
            )
            return False

        try:
            success = await plugin.activate()
            if success:
                plugin.state = PluginState.ACTIVATED
                logger.info(f"Activated plugin: {plugin_name}")
            else:
                plugin.state = PluginState.ERROR
            return success
        except Exception as e:
            logger.error(f"Error activating plugin {plugin_name}: {e}")
            plugin.state = PluginState.ERROR
            return False

    async def deactivate(self, plugin_name: str) -> bool:
        """Deactivate a plugin (stop processing)."""
        plugin = self._plugins.get(plugin_name)
        if not plugin:
            return False
        if plugin.state != PluginState.ACTIVATED:
            return True  # Already deactivated

        try:
            success = await plugin.deactivate()
            if success:
                plugin.state = PluginState.DEACTIVATED
            return success
        except Exception as e:
            logger.error(f"Error deactivating plugin {plugin_name}: {e}")
            return False

    async def shutdown(self, plugin_name: str) -> bool:
        """Shutdown and unload a plugin."""
        plugin = self._plugins.pop(plugin_name, None)
        if not plugin:
            return False

        try:
            await plugin.shutdown()
            logger.info(f"Shutdown plugin: {plugin_name}")
            return True
        except Exception as e:
            logger.error(f"Error shutting down plugin {plugin_name}: {e}")
            return False

    async def load_all(
        self, context: dict[str, Any]
    ) -> dict[str, bool]:
        """
        Load, initialize, and activate all discovered plugins.

        Returns a dictionary of plugin_name -> success boolean.
        """
        # Resolve dependency order (simple: load all, let plugins handle)
        manifests = await self.discover()
        results: dict[str, bool] = {}

        for manifest in manifests:
            name = manifest.name
            loaded = await self.load(name)
            if loaded:
                initialized = await self.initialize(name, context)
                if initialized:
                    activated = await self.activate(name)
                    results[name] = activated
                else:
                    results[name] = False
            else:
                results[name] = False

        return results

    async def shutdown_all(self) -> None:
        """Shutdown all plugins."""
        for name in list(self._plugins.keys()):
            await self.shutdown(name)

    def list_plugins(self) -> list[dict[str, Any]]:
        """List all plugins with their state."""
        return [
            {
                "name": name,
                "version": plugin.manifest.version if plugin.manifest else "?",
                "state": plugin.state.value,
                "description": plugin.manifest.description if plugin.manifest else "",
            }
            for name, plugin in self._plugins.items()
        ]

    def is_active(self, plugin_name: str) -> bool:
        """Check if a plugin is currently active."""
        plugin = self._plugins.get(plugin_name)
        return plugin is not None and plugin.state == PluginState.ACTIVATED


# ── Plugin SDK (Public API) ────────────────────────────────────────────


class PluginSDK:
    """
    Public SDK surface for plugin developers.

    Provides access to:
    - Studio services and configuration
    - Event bus for pub/sub
    - Asset pipeline hooks
    - UI extension registration
    """

    def __init__(self, context: dict[str, Any]) -> None:
        self.context = context

    @property
    def event_bus(self):
        """Access the studio event bus."""
        return self.context.get("event_bus")

    @property
    def config(self) -> dict[str, Any]:
        """Access studio configuration."""
        return self.context.get("config", {})

    def register_hook(
        self, extension_point: str, handler: Callable[..., Any], priority: int = 0
    ) -> None:
        """Register a hook handler for an extension point."""
        extension_points = self.context.get("extension_points", {})
        ep = extension_points.get(extension_point)
        if ep:
            ep.register(handler, priority)

    def unregister_hook(
        self, extension_point: str, handler: Callable[..., Any]
    ) -> None:
        """Unregister a hook handler."""
        extension_points = self.context.get("extension_points", {})
        ep = extension_points.get(extension_point)
        if ep:
            ep.unregister(handler)
