
"""Narrative repository implementation."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from backend.modules.narrative.domain.story import NarrativeScene, StoryDocument
from backend.modules.narrative.infrastructure.models import NarrativeSceneModel, StoryDocumentModel
from backend.shared.errors import NotFoundError


class SqlAlchemyNarrativeRepository:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def add_story(self, story: StoryDocument) -> None:
        model = StoryDocumentModel(
            id=story.story_id, project_id=story.project_id,
            title=story.title, content=story.content,
            created_at=story.created_at, updated_at=story.updated_at,
            revision=story.revision,
        )
        async with self._session_factory() as session:
            session.add(model)
            await session.commit()

    async def get_story(self, story_id: str) -> StoryDocument:
        async with self._session_factory() as session:
            result = await session.execute(select(StoryDocumentModel).where(StoryDocumentModel.id == story_id))
            m = result.scalar_one_or_none()
            if m is None:
                raise NotFoundError("StoryDocument", story_id)
            return StoryDocument(story_id=m.id, project_id=m.project_id, title=m.title, content=m.content,
                                 created_at=m.created_at, updated_at=m.updated_at, revision=m.revision)

    async def list_stories_by_project(self, project_id: str) -> list[StoryDocument]:
        async with self._session_factory() as session:
            result = await session.execute(
                select(StoryDocumentModel).where(StoryDocumentModel.project_id == project_id).order_by(StoryDocumentModel.created_at.desc())
            )
            models = result.scalars().all()
            return [StoryDocument(story_id=m.id, project_id=m.project_id, title=m.title, content=m.content,
                                  created_at=m.created_at, updated_at=m.updated_at, revision=m.revision) for m in models]

    async def add_scene(self, scene: NarrativeScene) -> None:
        model = NarrativeSceneModel(
            id=scene.scene_id, project_id=scene.project_id, story_id=scene.story_id,
            sequence_number=scene.sequence_number, title=scene.title,
            description=scene.description, location=scene.location,
            time_of_day=scene.time_of_day, mood=scene.mood,
            created_at=scene.created_at, updated_at=scene.updated_at, revision=scene.revision,
        )
        async with self._session_factory() as session:
            session.add(model)
            await session.commit()

    async def list_scenes_by_project(self, project_id: str) -> list[NarrativeScene]:
        async with self._session_factory() as session:
            result = await session.execute(
                select(NarrativeSceneModel)
                .where(NarrativeSceneModel.project_id == project_id)
                .order_by(NarrativeSceneModel.sequence_number)
            )
            models = result.scalars().all()
            return [NarrativeScene(scene_id=m.id, project_id=m.project_id, story_id=m.story_id,
                                   sequence_number=m.sequence_number, title=m.title,
                                   description=m.description, location=m.location,
                                   time_of_day=m.time_of_day, mood=m.mood,
                                   created_at=m.created_at, updated_at=m.updated_at, revision=m.revision) for m in models]
