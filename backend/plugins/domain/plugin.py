"""
Plugin Domain — Plugin entity, manifest, version, permission, capability (Part 18)

Core domain objects for the plugin system. Every plugin is described by a
PluginManifest (YAML), validated against version constraints, granted
permissions, and exposes capabilities through registries.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


class PluginState(str, Enum):
    """Plugin lifecycle states."""
    DISCOVERED = "discovered"
    VALIDATED = "validated"
    INSTALLED = "installed"
    CONFIGURED = "configured"
    ENABLED = "enabled"
    RUNNING = "running"
    DEGRADED = "degraded"
    DISABLED = "disabled"
    UNINSTALLED = "uninstalled"


class PluginType(str, Enum):
    """Eight plugin extension categories."""
    AGENT = "agent"
    PROVIDER = "provider"
    WORKFLOW_NODE = "workflow_node"
    MEDIA_PROCESSOR = "media_processor"
    EXPORTER = "exporter"
    IMPORTER = "importer"
    UI = "ui"
    AUTOMATION_HOOK = "automation_hook"


@dataclass
class Plugin:
    """Core plugin entity — the aggregate root for the plugin bounded context."""

    plugin_id: str
    name: str
    version: str
    description: str = ""
    author: str = ""
    license: str = ""
    homepage: str = ""
    entrypoint: str = ""

    state: PluginState = PluginState.DISCOVERED
    installed_at: datetime | None = None
    enabled_at: datetime | None = None
    disabled_at: datetime | None = None

    manifest_hash: str = ""
    capabilities: list[Capability] = field(default_factory=list)
    permissions: list[PluginPermission] = field(default_factory=list)
    config_schema: dict[str, Any] = field(default_factory=dict)
    dependencies: list[str] = field(default_factory=list)
    migrations_path: str = ""
    health_config: dict[str, Any] = field(default_factory=dict)

    runtime_type: str = "in_process"
    python_version: str = ">=3.11"
    min_platform_version: str = ""
    max_platform_version: str = ""

    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def is_running(self) -> bool:
        return self.state in (PluginState.RUNNING, PluginState.ENABLED)

    @property
    def plugin_type(self) -> PluginType | None:
        """Infer primary type from first capability."""
        if self.capabilities:
            try:
                return PluginType(self.capabilities[0].capability_type)
            except ValueError:
                return None
        return None

    def compute_manifest_hash(self, manifest_dict: dict[str, Any]) -> str:
        """Compute deterministic hash of the manifest for integrity verification."""
        raw = __import__("json").dumps(manifest_dict, sort_keys=True)
        return hashlib.sha256(raw.encode()).hexdigest()

    def can_transition_to(self, target: PluginState) -> bool:
        """Validate state transitions."""
        transitions: dict[PluginState, set[PluginState]] = {
            PluginState.DISCOVERED: {PluginState.VALIDATED},
            PluginState.VALIDATED: {PluginState.INSTALLED},
            PluginState.INSTALLED: {PluginState.CONFIGURED, PluginState.UNINSTALLED},
            PluginState.CONFIGURED: {PluginState.ENABLED, PluginState.DISABLED},
            PluginState.ENABLED: {PluginState.RUNNING, PluginState.DISABLED},
            PluginState.RUNNING: {PluginState.DEGRADED, PluginState.DISABLED},
            PluginState.DEGRADED: {PluginState.RUNNING, PluginState.DISABLED},
            PluginState.DISABLED: {PluginState.ENABLED, PluginState.UNINSTALLED},
            PluginState.UNINSTALLED: set(),
        }
        return target in transitions.get(self.state, set())


@dataclass
class Capability:
    """A declared capability exposed by a plugin."""

    capability_type: str
    capability_id: str
    name: str
    version: str
    input_schema: dict[str, Any] | None = None
    output_schema: dict[str, Any] | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    plugin_id: str = ""


@dataclass
class PluginPermission:
    """A permission required by a plugin."""

    permission_id: str
    level: str = "required"  # required | optional
    description: str = ""
    granted: bool = False
    grant_reason: str = ""


# ── PluginVersion (SemVer) ────────────────────────────────────────────

import re


@dataclass
class PluginVersion:
    """SemVer-compatible version with compatibility checking."""
    major: int = 1
    minor: int = 0
    patch: int = 0
    prerelease: str = ""

    @classmethod
    def parse(cls, version_str: str) -> "PluginVersion":
        match = re.match(r"(\d+)\.(\d+)\.(\d+)(?:-(.+))?", version_str.strip())
        if not match:
            raise ValueError(f"Invalid version string: {version_str}")
        return cls(
            major=int(match.group(1)),
            minor=int(match.group(2)),
            patch=int(match.group(3)),
            prerelease=match.group(4) or "",
        )

    def __str__(self) -> str:
        base = f"{self.major}.{self.minor}.{self.patch}"
        return f"{base}-{self.prerelease}" if self.prerelease else base

    def is_compatible_with(self, other: "PluginVersion") -> bool:
        return self.major == other.major and self.minor >= other.minor

    def __lt__(self, other: "PluginVersion") -> bool:
        return (self.major, self.minor, self.patch) < (other.major, other.minor, other.patch)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, PluginVersion):
            return NotImplemented
        return (self.major, self.minor, self.patch, self.prerelease) == (
            other.major, other.minor, other.patch, other.prerelease)


# ── PluginManifest ────────────────────────────────────────────────────

@dataclass
class PluginManifest:
    """Parseable plugin manifest (YAML/JSON serializable)."""
    plugin_id: str = ""
    name: str = ""
    version: str = "1.0.0"
    description: str = ""
    author: str = ""
    author_email: str = ""
    homepage: str = ""
    license: str = "MIT"

    capabilities: list[str] = field(default_factory=list)
    permissions: list[str] = field(default_factory=list)

    dependencies: dict[str, str] = field(default_factory=dict)
    platform_min_version: str = "0.9.0"
    platform_max_version: str = ""

    entry_point: str = ""
    icon_path: str = ""
    tags: list[str] = field(default_factory=list)

    install_requires: list[str] = field(default_factory=list)

    def validate(self) -> list[str]:
        issues = []
        if not self.plugin_id:
            issues.append("plugin_id is required")
        if not self.name:
            issues.append("name is required")
        if not self.entry_point:
            issues.append("entry_point is required")
        return issues

    def to_plugin_entity(self) -> Plugin:
        """Convert manifest to Plugin aggregate root."""
        return Plugin(
            plugin_id=self.plugin_id,
            name=self.name,
            version=self.version,
            description=self.description,
            author=self.author,
            license=self.license,
            homepage=self.homepage,
            entrypoint=self.entry_point,
            dependencies=list(self.dependencies.keys()),
            capabilities=[
                Capability(capability_type=c, capability_id=f"{self.plugin_id}.{c}", name=c, version=self.version)
                for c in self.capabilities
            ],
            permissions=[
                PluginPermission(permission_id=p) for p in self.permissions
            ],
            min_platform_version=self.platform_min_version,
            max_platform_version=self.platform_max_version,
        )


# ── PluginLifecycle (base class with hooks) ───────────────────────────

class PluginLifecycle:
    """
    Base class with lifecycle hook methods for plugin implementations.

    Hooks (called in order):
        on_install() → on_activate() → on_start() → ... → on_pause() → on_deactivate() → on_uninstall()
    """

    manifest: PluginManifest | None = None

    async def on_install(self) -> None:
        """Called when plugin is first installed."""
        pass

    async def on_activate(self) -> None:
        """Called when plugin is activated (enabled)."""
        pass

    async def on_start(self) -> None:
        """Called when the platform starts with this plugin active."""
        pass

    async def on_pause(self) -> None:
        """Called when plugin is temporarily paused."""
        pass

    async def on_deactivate(self) -> None:
        """Called when plugin is deactivated (disabled)."""
        pass

    async def on_uninstall(self) -> None:
        """Called when plugin is uninstalled."""
        pass

    async def on_upgrade(
        self, from_version: PluginVersion, to_version: PluginVersion
    ) -> None:
        """Called during plugin upgrade with version context."""
        pass

    async def migrate_data(
        self, from_version: PluginVersion, to_version: PluginVersion
    ) -> None:
        """Handle data migration when upgrading."""
        pass

    def get_capability_objects(self) -> dict[str, Any]:
        """Return capability objects for registration. Override as needed."""
        return {}
