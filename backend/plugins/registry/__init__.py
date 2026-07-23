"""
Plugin Registry — Registration and discovery (Part 18)

Manages plugin registration, capability exposure, and
runtime isolation across all plugin types.
"""

from __future__ import annotations

import logging
from typing import Any

from backend.plugins.domain.plugin import (
    Plugin,
    PluginCapability,
    PluginLifecycle,
    PluginPermission,
)

logger = logging.getLogger(__name__)


class PluginRegistry:
    """
    Central registry for all installed plugins.

    Manages lifecycle: install → activate → run → deactivate → uninstall.
    """

    def __init__(self) -> None:
        self._plugins: dict[str, Plugin] = {}  # plugin_id → Plugin

    # ── Registration ──────────────────────────────────────────────────

    def register(self, plugin: Plugin) -> None:
        """Register a plugin (must have valid manifest)."""
        pid = plugin.manifest.plugin_id
        if pid in self._plugins:
            raise ValueError(f"Plugin '{pid}' is already registered")
        self._plugins[pid] = plugin
        plugin._transition(PluginLifecycle.INSTALLED)
        logger.info(f"Plugin '{pid}' v{plugin.manifest.version} registered")

    def unregister(self, plugin_id: str) -> None:
        """Unregister and remove a plugin."""
        plugin = self._plugins.pop(plugin_id, None)
        if plugin:
            plugin._transition(PluginLifecycle.UNINSTALLED)
            logger.info(f"Plugin '{plugin_id}' unregistered")

    # ── Lifecycle ─────────────────────────────────────────────────────

    async def activate(self, plugin_id: str) -> None:
        """Activate a plugin."""
        plugin = self._get(plugin_id)
        await plugin.on_activate()
        plugin._transition(PluginLifecycle.ACTIVATED)

    async def deactivate(self, plugin_id: str) -> None:
        """Deactivate a plugin."""
        plugin = self._get(plugin_id)
        await plugin.on_deactivate()
        plugin._transition(PluginLifecycle.DEACTIVATED)

    async def activate_all(self) -> None:
        for pid in list(self._plugins.keys()):
            await self.activate(pid)

    # ── Query ─────────────────────────────────────────────────────────

    def _get(self, plugin_id: str) -> Plugin:
        plugin = self._plugins.get(plugin_id)
        if not plugin:
            raise KeyError(f"Plugin '{plugin_id}' not found")
        return plugin

    def get(self, plugin_id: str) -> Plugin | None:
        return self._plugins.get(plugin_id)

    def list_by_capability(self, capability: PluginCapability) -> list[Plugin]:
        return [p for p in self._plugins.values()
                if capability in p.manifest.capabilities
                and p.state == PluginLifecycle.ACTIVATED]

    def list_all(self) -> list[Plugin]:
        return list(self._plugins.values())

    def check_permissions(self, plugin_id: str, required: PluginPermission) -> bool:
        """Check if a plugin has the required permissions."""
        plugin = self._plugins.get(plugin_id)
        if not plugin:
            return False
        return (plugin.manifest.permissions & required) == required


class CapabilityRegistry:
    """
    Maps capability types to actual registered implementations.

    Each capability category (Agent, Provider, etc.) has its own
    sub-registry that plugins populate during activation.
    """

    def __init__(self) -> None:
        self._agents: dict[str, Any] = {}
        self._providers: dict[str, Any] = {}
        self._workflow_nodes: dict[str, Any] = {}
        self._media_processors: dict[str, Any] = {}
        self._exporters: dict[str, Any] = {}
        self._importers: dict[str, Any] = {}
        self._ui_components: dict[str, Any] = {}
        self._automation_hooks: dict[str, Any] = {}

    def register_agent(self, name: str, agent_cls: type[Any]) -> None:
        self._agents[name] = agent_cls

    def register_provider(self, name: str, provider: Any) -> None:
        self._providers[name] = provider

    def register_workflow_node(self, name: str, node_cls: type[Any]) -> None:
        self._workflow_nodes[name] = node_cls

    def register_media_processor(self, name: str, processor: Any) -> None:
        self._media_processors[name] = processor

    def register_exporter(self, name: str, exporter: Any) -> None:
        self._exporters[name] = exporter

    def register_importer(self, name: str, importer: Any) -> None:
        self._importers[name] = importer

    def register_ui_component(self, name: str, component: Any) -> None:
        self._ui_components[name] = component

    def register_automation_hook(self, name: str, hook: Any) -> None:
        self._automation_hooks[name] = hook

    def get_agent(self, name: str) -> Any:
        return self._agents.get(name)

    def get_provider(self, name: str) -> Any:
        return self._providers.get(name)

    def get_workflow_node(self, name: str) -> Any:
        return self._workflow_nodes.get(name)

    def list_all_capabilities(self) -> dict[str, list[str]]:
        return {
            "agents": list(self._agents.keys()),
            "providers": list(self._providers.keys()),
            "workflow_nodes": list(self._workflow_nodes.keys()),
            "media_processors": list(self._media_processors.keys()),
            "exporters": list(self._exporters.keys()),
            "importers": list(self._importers.keys()),
            "ui_components": list(self._ui_components.keys()),
            "automation_hooks": list(self._automation_hooks.keys()),
        }


class RuntimeManager:
    """
    Manages plugin runtime isolation and health.

    Responsibilities:
    - Fault isolation: Plugin failures don't crash the platform
    - Resource monitoring: Track CPU/memory per plugin
    - Health checks: Detect hung or misbehaving plugins
    """

    def __init__(self) -> None:
        self._error_counts: dict[str, int] = {}  # plugin_id → error count
        self._max_errors: int = 5

    def record_error(self, plugin_id: str) -> None:
        count = self._error_counts.get(plugin_id, 0) + 1
        self._error_counts[plugin_id] = count
        if count >= self._max_errors:
            logger.warning(f"Plugin '{plugin_id}' exceeded error threshold ({count} errors)")

    def is_healthy(self, plugin_id: str) -> bool:
        """Check if a plugin is still functioning."""
        return self._error_counts.get(plugin_id, 0) < self._max_errors

    def reset_errors(self, plugin_id: str) -> None:
        self._error_counts.pop(plugin_id, None)


# ── Global singletons ─────────────────────────────────────────────────

plugin_registry = PluginRegistry()
capability_registry = CapabilityRegistry()
runtime_manager = RuntimeManager()
