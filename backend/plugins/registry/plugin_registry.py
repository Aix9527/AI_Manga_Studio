"""
Plugin Registry — Central plugin registration and lookup (Part 18)

The PluginRegistry is the authority for all installed plugins.
It tracks plugin state, handles registration/unregistration,
and provides lookup by ID, type, or capability.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from typing import Any

from backend.plugins.domain.plugin import Plugin, PluginState
from backend.plugins.domain.capability import Capability, CapabilityType

logger = logging.getLogger(__name__)


class PluginRegistry:
    """Central registry for all plugins in the system."""

    def __init__(self) -> None:
        self._plugins: dict[str, Plugin] = {}
        self._by_state: dict[PluginState, list[str]] = defaultdict(list)
        self._by_type: dict[str, list[str]] = defaultdict(list)

    # ── Registration ──────────────────────────────────────────────────

    def register(self, plugin: Plugin) -> None:
        """Register or update a plugin. Raises if conflict."""
        if plugin.plugin_id in self._plugins:
            existing = self._plugins[plugin.plugin_id]
            if existing.version == plugin.version:
                logger.debug(f"Plugin '{plugin.plugin_id}' already registered, skipping")
                return
            # Allow version upgrade
            logger.info(
                f"Upgrading plugin '{plugin.plugin_id}': "
                f"{existing.version} → {plugin.version}"
            )

        self._plugins[plugin.plugin_id] = plugin
        self._rebuild_indexes()
        logger.info(f"Plugin registered: {plugin.plugin_id} v{plugin.version} [{plugin.state.value}]")

    def unregister(self, plugin_id: str) -> bool:
        """Remove a plugin from the registry."""
        if plugin_id not in self._plugins:
            return False
        del self._plugins[plugin_id]
        self._rebuild_indexes()
        logger.info(f"Plugin unregistered: {plugin_id}")
        return True

    # ── Queries ───────────────────────────────────────────────────────

    def get(self, plugin_id: str) -> Plugin | None:
        return self._plugins.get(plugin_id)

    def list_all(self) -> list[Plugin]:
        return list(self._plugins.values())

    def list_by_state(self, state: PluginState) -> list[Plugin]:
        ids = self._by_state.get(state, [])
        return [self._plugins[pid] for pid in ids if pid in self._plugins]

    def list_enabled(self) -> list[Plugin]:
        return [
            p for p in self._plugins.values()
            if p.state in (PluginState.ENABLED, PluginState.RUNNING)
        ]

    def list_by_type(self, plugin_type: str) -> list[Plugin]:
        ids = self._by_type.get(plugin_type, [])
        return [self._plugins[pid] for pid in ids if pid in self._plugins]

    def find_by_capability(self, cap_type: str, cap_id: str = "") -> list[Plugin]:
        """Find plugins that expose a specific capability."""
        result: list[Plugin] = []
        for plugin in self._plugins.values():
            for cap in plugin.capabilities:
                if cap.matches(cap_type=cap_type, cap_id=cap_id):
                    result.append(plugin)
                    break
        return result

    def exists(self, plugin_id: str) -> bool:
        return plugin_id in self._plugins

    # ── State management ──────────────────────────────────────────────

    def update_state(self, plugin_id: str, new_state: PluginState) -> bool:
        """Transition a plugin to a new state."""
        plugin = self._plugins.get(plugin_id)
        if not plugin:
            return False
        if not plugin.can_transition_to(new_state):
            logger.warning(
                f"Cannot transition plugin '{plugin_id}' "
                f"from {plugin.state.value} to {new_state.value}"
            )
            return False
        plugin.state = new_state
        self._rebuild_indexes()
        logger.info(f"Plugin '{plugin_id}' state → {new_state.value}")
        return True

    # ── Internals ─────────────────────────────────────────────────────

    def _rebuild_indexes(self) -> None:
        """Rebuild derived indexes from the plugin map."""
        self._by_state.clear()
        self._by_type.clear()

        for plugin in self._plugins.values():
            self._by_state[plugin.state].append(plugin.plugin_id)
            if plugin.plugin_type:
                self._by_type[plugin.plugin_type.value].append(plugin.plugin_id)

    # ── Stats ─────────────────────────────────────────────────────────

    def stats(self) -> dict[str, Any]:
        return {
            "total_plugins": len(self._plugins),
            "by_state": {s.value: len(ids) for s, ids in self._by_state.items()},
            "enabled_count": len(self.list_enabled()),
        }
