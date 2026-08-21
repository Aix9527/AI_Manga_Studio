"""Character timeline tracking across the narrative."""

from __future__ import annotations

from typing import Optional

from backend.story.models import Timeline, TimelineEvent


class TimelineManager:
    """Tracks character appearances and events across chapters."""

    def __init__(self):
        self.timelines: dict[str, Timeline] = {}

    def get_or_create(self, novel_id: str) -> Timeline:
        if novel_id not in self.timelines:
            self.timelines[novel_id] = Timeline(novel_id=novel_id)
        return self.timelines[novel_id]

    def add_event(
        self,
        novel_id: str,
        chapter_number: int,
        character_id: str,
        event_type: str,
        description: str,
        relative_time: str = "",
    ) -> TimelineEvent:
        timeline = self.get_or_create(novel_id)

        event = TimelineEvent(
            novel_id=novel_id,
            chapter_number=chapter_number,
            character_id=character_id,
            event_type=event_type,
            description=description,
            relative_time=relative_time or f"chapter {chapter_number}",
        )

        timeline.events.append(event)
        return event

    def get_character_timeline(self, novel_id: str, character_id: str) -> list[TimelineEvent]:
        """Get all events for a specific character, ordered by chapter."""
        timeline = self.timelines.get(novel_id)
        if not timeline:
            return []

        events = [e for e in timeline.events if e.character_id == character_id]
        return sorted(events, key=lambda e: e.chapter_number)

    def get_chapter_events(self, novel_id: str, chapter_number: int) -> list[TimelineEvent]:
        """Get all events for a specific chapter."""
        timeline = self.timelines.get(novel_id)
        if not timeline:
            return []

        return [e for e in timeline.events if e.chapter_number == chapter_number]

    def get_character_appearance_span(self, novel_id: str, character_id: str) -> dict:
        """Get first and last chapter appearance for a character."""
        events = self.get_character_timeline(novel_id, character_id)
        if not events:
            return {"first": None, "last": None, "total_events": 0}

        return {
            "first": events[0].chapter_number,
            "last": events[-1].chapter_number,
            "total_events": len(events),
        }

    def export_timeline(self, novel_id: str) -> dict:
        timeline = self.timelines.get(novel_id)
        if not timeline:
            return {}
        return timeline.to_dict()
