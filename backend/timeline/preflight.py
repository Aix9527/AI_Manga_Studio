from __future__ import annotations

from backend.timeline.models import TimelinePreflight


def preflight_draft() -> TimelinePreflight:
    """Task 2 bootstrap hook; structural checks are added with edit operations."""
    return TimelinePreflight()
