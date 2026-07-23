
"""Storyboard repository implementation."""


from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from backend.modules.storyboard.domain.storyboard import Shot, ShotCharacterBinding, StoryboardScene
from backend.modules.storyboard.infrastructure.models import ShotCharacterModel, ShotModel, StoryboardSceneModel
from backend.shared.errors import NotFoundError


class SqlAlchemyStoryboardRepository:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def add_scene(self, scene: StoryboardScene) -> None:
        model = StoryboardSceneModel(
            id=scene.scene_id, project_id=scene.project_id,
            narrative_scene_id=scene.narrative_scene_id, sequence_number=scene.sequence_number,
            title=scene.title, description=scene.description,
            created_at=scene.created_at, updated_at=scene.updated_at, revision=scene.revision,
        )
        async with self._session_factory() as session:
            session.add(model)
            await session.commit()

    async def get_scene(self, scene_id: str) -> StoryboardScene:
        async with self._session_factory() as session:
            result = await session.execute(select(StoryboardSceneModel).where(StoryboardSceneModel.id == scene_id))
            m = result.scalar_one_or_none()
            if m is None:
                raise NotFoundError("StoryboardScene", scene_id)
            return StoryboardScene(scene_id=m.id, project_id=m.project_id, narrative_scene_id=m.narrative_scene_id,
                                   sequence_number=m.sequence_number, title=m.title, description=m.description,
                                   created_at=m.created_at, updated_at=m.updated_at, revision=m.revision)

    async def list_scenes_by_project(self, project_id: str) -> list[StoryboardScene]:
        async with self._session_factory() as session:
            result = await session.execute(
                select(StoryboardSceneModel).where(StoryboardSceneModel.project_id == project_id).order_by(StoryboardSceneModel.sequence_number)
            )
            models = result.scalars().all()
            return [StoryboardScene(scene_id=m.id, project_id=m.project_id, narrative_scene_id=m.narrative_scene_id,
                                    sequence_number=m.sequence_number, title=m.title, description=m.description,
                                    created_at=m.created_at, updated_at=m.updated_at, revision=m.revision) for m in models]

    async def add_shot(self, shot: Shot) -> None:
        model = ShotModel(
            id=shot.shot_id, scene_id=shot.scene_id, project_id=shot.project_id,
            shot_number=shot.shot_number, description=shot.description,
            framing=shot.framing, camera_angle=shot.camera_angle, camera_motion=shot.camera_motion,
            duration_seconds=shot.duration_seconds, dialog=shot.dialog,
            frozen_snapshot_json=shot.frozen_snapshot_json,
            created_at=shot.created_at, updated_at=shot.updated_at, revision=shot.revision,
        )
        async with self._session_factory() as session:
            session.add(model)
            await session.commit()

    async def list_shots_by_scene(self, scene_id: str) -> list[Shot]:
        async with self._session_factory() as session:
            result = await session.execute(
                select(ShotModel).where(ShotModel.scene_id == scene_id).order_by(ShotModel.shot_number)
            )
            models = result.scalars().all()
            return [Shot(shot_id=m.id, scene_id=m.scene_id, project_id=m.project_id, shot_number=m.shot_number,
                         description=m.description, framing=m.framing, camera_angle=m.camera_angle,
                         camera_motion=m.camera_motion, duration_seconds=m.duration_seconds, dialog=m.dialog,
                         frozen_snapshot_json=m.frozen_snapshot_json,
                         created_at=m.created_at, updated_at=m.updated_at, revision=m.revision) for m in models]

    async def bind_character(self, binding: ShotCharacterBinding) -> None:
        model = ShotCharacterModel(
            shot_id=binding.shot_id, character_id=binding.character_id,
            pose=binding.pose, expression=binding.expression,
            position=binding.position, scale=binding.scale,
        )
        async with self._session_factory() as session:
            session.add(model)
            await session.commit()

    async def list_shot_characters(self, shot_id: str) -> list[ShotCharacterBinding]:
        async with self._session_factory() as session:
            result = await session.execute(
                select(ShotCharacterModel).where(ShotCharacterModel.shot_id == shot_id)
            )
            models = result.scalars().all()
            return [ShotCharacterBinding(shot_id=m.shot_id, character_id=m.character_id,
                                         pose=m.pose, expression=m.expression,
                                         position=m.position, scale=m.scale) for m in models]
