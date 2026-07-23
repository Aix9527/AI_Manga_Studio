
"""Narrative module public API."""

from dataclasses import dataclass

from backend.modules.narrative.domain.story import StoryDocument
from backend.modules.narrative.infrastructure.repository import SqlAlchemyNarrativeRepository
from backend.shared.ids import IdGenerator
from backend.shared.time import Clock


@dataclass(slots=True)
class NarrativeModuleApi:
    narrative_repo: SqlAlchemyNarrativeRepository
    id_generator: IdGenerator
    clock: Clock

    @property
    def _narrative_repo(self) -> SqlAlchemyNarrativeRepository:
        return self.narrative_repo

    async def import_story(self, project_id: str, title: str, content: str) -> StoryDocument:
        now = self.clock.now()
        story = StoryDocument(
            story_id=self.id_generator.new("story"),
            project_id=project_id,
            title=title,
            content=content,
            created_at=now,
            updated_at=now,
        )
        await self.narrative_repo.add_story(story)
        return story
