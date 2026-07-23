"""
Plugin Manifest — YAML manifest parsing and validation (Part 18)

Parses plugin.yaml files into structured PluginManifest objects.
Validates schema, version ranges, and required fields.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class CompatibilityConstraint:
    """Version compatibility range for platform."""
    min_version: str = ""
    max_version_exclusive: str = ""


@dataclass
class RuntimeSpec:
    """Runtime requirements specification."""
    type: str = "in_process"  # in_process | subprocess | remote
    language: str = "python"
    python: str = ">=3.11"


@dataclass
class HealthPolicy:
    """Plugin health check configuration."""
    timeout_seconds: float = 10.0
    heartbeat_interval_seconds: float = 30.0


@dataclass
class ManifestCapability:
    """Capability declaration from manifest."""
    type: str = ""
    id: str = ""


@dataclass
class ManifestPermissions:
    """Permissions block from manifest."""
    required: list[str] = field(default_factory=list)
    optional: list[str] = field(default_factory=list)


@dataclass
class ManifestDependencies:
    """Dependencies block from manifest."""
    plugins: list[str] = field(default_factory=list)
    python: list[str] = field(default_factory=list)


@dataclass
class PluginManifest:
    """Parsed plugin manifest — the source of truth for plugin metadata."""

    schema_version: str = "1.0"
    plugin_id: str = ""
    name: str = ""
    version: str = ""
    description: str = ""
    author: str = ""
    license: str = ""
    homepage: str = ""
    entrypoint: str = ""

    compatibility: CompatibilityConstraint = field(default_factory=CompatibilityConstraint)
    runtime: RuntimeSpec = field(default_factory=RuntimeSpec)
    capabilities: list[ManifestCapability] = field(default_factory=list)
    permissions: ManifestPermissions = field(default_factory=ManifestPermissions)
    configuration: dict[str, str] = field(default_factory=dict)
    dependencies: ManifestDependencies = field(default_factory=ManifestDependencies)
    migrations: dict[str, str] = field(default_factory=dict)
    health: HealthPolicy = field(default_factory=HealthPolicy)

    raw: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PluginManifest:
        """Parse a manifest dictionary into a PluginManifest object."""
        plugin_raw = data.get("plugin", {})

        compat_raw = data.get("compatibility", {}).get("ai_manga_studio", {})
        runtime_raw = data.get("runtime", {})
        permissions_raw = data.get("permissions", {})
        deps_raw = data.get("dependencies", {})
        health_raw = data.get("health", {})

        capabilities = [
            ManifestCapability(type=c.get("type", ""), id=c.get("id", ""))
            for c in data.get("capabilities", [])
        ]

        return cls(
            schema_version=data.get("schema_version", "1.0"),
            plugin_id=plugin_raw.get("id", ""),
            name=plugin_raw.get("name", ""),
            version=plugin_raw.get("version", ""),
            description=plugin_raw.get("description", ""),
            author=plugin_raw.get("author", ""),
            license=plugin_raw.get("license", ""),
            homepage=plugin_raw.get("homepage", ""),
            entrypoint=plugin_raw.get("entrypoint", ""),
            compatibility=CompatibilityConstraint(
                min_version=compat_raw.get("min_version", ""),
                max_version_exclusive=compat_raw.get("max_version_exclusive", ""),
            ),
            runtime=RuntimeSpec(
                type=runtime_raw.get("type", "in_process"),
                language=runtime_raw.get("language", "python"),
                python=runtime_raw.get("python", ">=3.11"),
            ),
            capabilities=capabilities,
            permissions=ManifestPermissions(
                required=permissions_raw.get("required", []),
                optional=permissions_raw.get("optional", []),
            ),
            configuration=data.get("configuration", {}),
            dependencies=ManifestDependencies(
                plugins=deps_raw.get("plugins", []),
                python=deps_raw.get("python", []),
            ),
            migrations=data.get("migrations", {}),
            health=HealthPolicy(
                timeout_seconds=health_raw.get("timeout_seconds", 10),
                heartbeat_interval_seconds=health_raw.get("heartbeat_interval_seconds", 30),
            ),
            raw=data,
        )

    def validate(self) -> list[str]:
        """Validate required fields. Returns list of error messages."""
        errors: list[str] = []
        if not self.plugin_id:
            errors.append("Missing required field: plugin.id")
        if not self.name:
            errors.append("Missing required field: plugin.name")
        if not self.version:
            errors.append("Missing required field: plugin.version")
        if not self.entrypoint:
            errors.append("Missing required field: plugin.entrypoint")
        if self.plugin_id and not self._is_valid_id(self.plugin_id):
            errors.append(
                f"Invalid plugin ID format: '{self.plugin_id}'. "
                "Must use reverse domain notation (e.g. com.example.my-plugin)"
            )
        return errors

    @staticmethod
    def _is_valid_id(plugin_id: str) -> bool:
        """Check if plugin_id follows reverse domain convention."""
        parts = plugin_id.split(".")
        return len(parts) >= 2 and all(parts)
