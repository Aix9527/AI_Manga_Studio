"""
Plugin Version — Semantic versioning and compatibility checking (Part 18)

Handles version parsing, comparison, and compatibility constraint
validation between plugins and the platform.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import total_ordering


@total_ordering
@dataclass
class PluginVersion:
    """Semantic version: MAJOR.MINOR.PATCH with optional pre-release."""

    major: int
    minor: int
    patch: int
    pre_release: str = ""

    @classmethod
    def parse(cls, version_str: str) -> PluginVersion:
        """Parse a version string like '1.4.2' or '1.4.2-beta.1'."""
        pre = ""
        base = version_str.strip()

        if "-" in base:
            base, pre = base.split("-", 1)

        parts = base.split(".")
        if len(parts) != 3:
            raise ValueError(f"Invalid semantic version: '{version_str}'")

        return cls(
            major=int(parts[0]),
            minor=int(parts[1]),
            patch=int(parts[2]),
            pre_release=pre,
        )

    def is_compatible_with(self, min_version: str, max_exclusive: str) -> bool:
        """Check if this version satisfies [min_version, max_version_exclusive)."""
        if min_version:
            if self < PluginVersion.parse(min_version):
                return False
        if max_exclusive:
            if self >= PluginVersion.parse(max_exclusive):
                return False
        return True

    def is_stable(self) -> bool:
        """Stable versions have no pre-release tag."""
        return not self.pre_release

    def bump_major(self) -> PluginVersion:
        """Bump major version: incompatible changes."""
        return PluginVersion(self.major + 1, 0, 0)

    def bump_minor(self) -> PluginVersion:
        """Bump minor version: backward-compatible new features."""
        return PluginVersion(self.major, self.minor + 1, 0)

    def bump_patch(self) -> PluginVersion:
        """Bump patch version: backward-compatible fixes."""
        return PluginVersion(self.major, self.minor, self.patch + 1)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, PluginVersion):
            return NotImplemented
        return (self.major, self.minor, self.patch, self.pre_release) == (
            other.major, other.minor, other.patch, other.pre_release,
        )

    def __lt__(self, other: PluginVersion) -> bool:
        if (self.major, self.minor, self.patch) != (other.major, other.minor, other.patch):
            return (self.major, self.minor, self.patch) < (other.major, other.minor, other.patch)

        # pre-release versions come before release
        if not self.pre_release and other.pre_release:
            return False
        if self.pre_release and not other.pre_release:
            return True
        return self.pre_release < other.pre_release

    def __str__(self) -> str:
        base = f"{self.major}.{self.minor}.{self.patch}"
        if self.pre_release:
            return f"{base}-{self.pre_release}"
        return base

    def __repr__(self) -> str:
        return f"PluginVersion({self})"


class CompatibilityChecker:
    """Checks plugin compatibility with the platform version."""

    def __init__(self, platform_version: str) -> None:
        self._platform = PluginVersion.parse(platform_version)

    def check(self, min_version: str, max_version_exclusive: str) -> bool:
        """Check if platform version is in [min, max_exclusive)."""
        return self._platform.is_compatible_with(min_version, max_version_exclusive)

    @property
    def platform_version(self) -> PluginVersion:
        return self._platform
