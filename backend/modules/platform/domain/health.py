"""Platform domain models."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class HealthStatus:
    healthy: bool
    components: dict[str, str]
    environment: str
