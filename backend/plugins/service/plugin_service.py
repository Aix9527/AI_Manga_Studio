"""
Plugin Service — High-level plugin management API (Part 18)

The PluginService is the facade that coordinates all plugin subsystems:
- Manifest parsing and validation
- Compatibility checking
- Permission review
- Installation and lifecycle management
- Registration (plugin, capability, node, agent, provider)
- Runtime management
- Health monitoring
"""

from __future__ import annotations

import logging
from typing import Any

from backend.plugins.domain.plugin import Plugin, PluginState
from backend.plugins.domain.plugin_manifest import PluginManifest
from backend.plugins.domain.plugin_version import CompatibilityChecker
from backend.plugins.domain.capability import Capability
from backend.plugins.registry.plugin_registry import PluginRegistry
from backend.plugins.registry.capability_registry import CapabilityRegistry
from backend.plugins.registry.node_registry import NodeRegistry
from backend.plugins.registry.agent_registry import AgentRegistry
from backend.plugins.registry.provider_registry import ProviderRegistry
from backend.plugins.runtime.runtime_manager import RuntimeManager

logger = logging.getLogger(__name__)


class PluginService:
    """Orchestrates all plugin operations."""

    def __init__(
        self,
        platform_version: str = "0.9.0",
        plugin_registry: PluginRegistry | None = None,
        capability_registry: CapabilityRegistry | None = None,
        node_registry: NodeRegistry | None = None,
        agent_registry: AgentRegistry | None = None,
        provider_registry: ProviderRegistry | None = None,
        runtime_manager: RuntimeManager | None = None,
    ) -> None:
        self._compat_checker = CompatibilityChecker(platform_version)
        self._plugin_reg = plugin_registry or PluginRegistry()
        self._cap_reg = capability_registry or CapabilityRegistry()
        self._node_reg = node_registry or NodeRegistry()
        self._agent_reg = agent_registry or AgentRegistry()
        self._provider_reg = provider_registry or ProviderRegistry()
        self._runtime = runtime_manager or RuntimeManager()

    @property
    def plugins(self) -> PluginRegistry:
        return self._plugin_reg

    @property
    def capabilities(self) -> CapabilityRegistry:
        return self._cap_reg

    # ── Discovery ─────────────────────────────────────────────────────

    def discover_from_manifest(self, manifest_dict: dict[str, Any]) -> Plugin | None:
        """Discover a plugin from a raw manifest dict. Returns Plugin or None on error."""
        manifest = PluginManifest.from_dict(manifest_dict)

        errors = manifest.validate()
        if errors:
            for err in errors:
                logger.error(f"Manifest validation error: {err}")
            return None

        # Compatibility check
        if not self._compat_checker.check(
            manifest.compatibility.min_version,
            manifest.compatibility.max_version_exclusive,
        ):
            logger.error(
                f"Plugin '{manifest.plugin_id}' is not compatible with "
                f"platform v{self._compat_checker.platform_version}"
            )
            return None

        # Build Plugin entity
        plugin = Plugin(
            plugin_id=manifest.plugin_id,
            name=manifest.name,
            version=manifest.version,
            description=manifest.description,
            author=manifest.author,
            license=manifest.license,
            homepage=manifest.homepage,
            entrypoint=manifest.entrypoint,
            runtime_type=manifest.runtime.type,
            python_version=manifest.runtime.python,
            min_platform_version=manifest.compatibility.min_version,
            max_platform_version=manifest.compatibility.max_version_exclusive,
            state=PluginState.VALIDATED,
        )

        # Parse capabilities
        for mc in manifest.capabilities:
            plugin.capabilities.append(
                Capability(
                    capability_type=mc.type,
                    capability_id=mc.id,
                    name=mc.id,
                    version=manifest.version,
                    plugin_id=plugin.plugin_id,
                )
            )

        return plugin

    # ── Installation ──────────────────────────────────────────────────

    async def install(self, plugin: Plugin) -> bool:
        """Install a validated plugin — register and start."""
        if not plugin.can_transition_to(PluginState.INSTALLED):
            logger.error(f"Plugin '{plugin.plugin_id}' cannot be installed from {plugin.state}")
            return False

        self._plugin_reg.register(plugin)
        plugin.state = PluginState.INSTALLED

        # Register capabilities
        for cap in plugin.capabilities:
            try:
                self._cap_reg.register(cap)
            except Exception as e:
                logger.error(f"Failed to register capability: {e}")
                return False

        logger.info(f"Plugin '{plugin.plugin_id}' installed successfully")
        return True

    async def enable(self, plugin_id: str) -> bool:
        """Enable an installed plugin and start its runtime."""
        plugin = self._plugin_reg.get(plugin_id)
        if not plugin:
            return False

        if not self._plugin_reg.update_state(plugin_id, PluginState.ENABLED):
            return False

        # Start runtime
        from backend.plugins.runtime.runtime_manager import RuntimeConfig, RuntimeType

        rt_type = RuntimeType.IN_PROCESS
        if plugin.runtime_type == "subprocess":
            rt_type = RuntimeType.SUBPROCESS
        elif plugin.runtime_type == "remote":
            rt_type = RuntimeType.REMOTE

        self._runtime.register(plugin_id, RuntimeConfig(
            runtime_type=rt_type,
            entrypoint=plugin.entrypoint,
        ))

        instance = await self._runtime.start(plugin_id)
        if instance:
            self._plugin_reg.update_state(plugin_id, PluginState.RUNNING)
        else:
            self._plugin_reg.update_state(plugin_id, PluginState.DEGRADED)

        return True

    async def disable(self, plugin_id: str) -> bool:
        """Disable a plugin — stop runtime and unregister capabilities."""
        await self._runtime.stop(plugin_id)
        self._cap_reg.unregister_all_for_plugin(plugin_id)
        self._plugin_reg.update_state(plugin_id, PluginState.DISABLED)
        return True

    async def uninstall(self, plugin_id: str) -> bool:
        """Completely uninstall a plugin."""
        await self.disable(plugin_id)
        self._cap_reg.unregister_all_for_plugin(plugin_id)
        self._plugin_reg.unregister(plugin_id)
        logger.info(f"Plugin '{plugin_id}' uninstalled")
        return True

    # ── Health ────────────────────────────────────────────────────────

    def get_stats(self) -> dict[str, Any]:
        return {
            "plugins": self._plugin_reg.stats(),
            "capabilities": self._cap_reg.stats(),
        }
