"""
Alerts — Alerting and notification infrastructure (Part 19)

Defines alert rules, notification channels, and alert management.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


class AlertSeverity(str, Enum):
    CRITICAL = "critical"
    WARNING = "warning"
    INFO = "info"


class AlertState(str, Enum):
    FIRING = "firing"
    RESOLVED = "resolved"
    ACKNOWLEDGED = "acknowledged"


@dataclass
class Alert:
    """A system alert."""
    alert_id: str
    name: str
    description: str = ""
    severity: AlertSeverity = AlertSeverity.WARNING
    state: AlertState = AlertState.FIRING
    source: str = ""
    fired_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    resolved_at: str = ""
    labels: dict[str, str] = field(default_factory=dict)
    annotations: dict[str, str] = field(default_factory=dict)

    def resolve(self) -> None:
        self.state = AlertState.RESOLVED
        self.resolved_at = datetime.now(timezone.utc).isoformat()


class AlertManager:
    """Manages alert lifecycle and notification dispatch."""

    def __init__(self) -> None:
        self._alerts: dict[str, Alert] = {}
        self._channels: list[NotificationChannel] = []

    def register_channel(self, channel: NotificationChannel) -> None:
        self._channels.append(channel)

    async def fire(
        self,
        name: str,
        description: str = "",
        severity: AlertSeverity = AlertSeverity.WARNING,
        **labels: str,
    ) -> Alert:
        import uuid
        alert = Alert(
            alert_id=str(uuid.uuid4()),
            name=name,
            description=description,
            severity=severity,
            labels=labels,
        )
        self._alerts[alert.alert_id] = alert

        for channel in self._channels:
            if channel.should_notify(alert):
                await channel.send(alert)

        return alert

    async def resolve(self, alert_id: str) -> bool:
        alert = self._alerts.get(alert_id)
        if not alert:
            return False
        alert.resolve()
        return True

    def list_firing(self) -> list[Alert]:
        return [a for a in self._alerts.values() if a.state == AlertState.FIRING]


class NotificationChannel:
    """Abstract notification channel."""

    def should_notify(self, alert: Alert) -> bool:
        """Whether this channel should receive this alert."""
        return True

    async def send(self, alert: Alert) -> None:
        """Send the alert notification."""
        raise NotImplementedError


class LogChannel(NotificationChannel):
    """Log alerts to console."""

    async def send(self, alert: Alert) -> None:
        import logging
        logger = logging.getLogger("alerts")
        logger.warning(f"[{alert.severity.value}] {alert.name}: {alert.description}")
