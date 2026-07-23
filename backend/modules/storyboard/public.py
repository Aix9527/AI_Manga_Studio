
"""Storyboard module public API."""

from dataclasses import dataclass
from typing import Optional

from backend.modules.characters.infrastructure.repository import SqlAlchemyCharacterRepository
from backend.modules.storyboard.domain.storyboard import Shot, StoryboardScene
from backend.modules.storyboard.infrastructure.repository import SqlAlchemyStoryboardRepository
from backend.shared.ids import IdGenerator
from backend.shared.time import Clock


@dataclass(slots=True)
class StoryboardModuleApi:
    storyboard_repo: SqlAlchemyStoryboardRepository
    character_repo: SqlAlchemyCharacterRepository
    id_generator: IdGenerator
    clock: Clock

    @property
    def _storyboard_repo(self) -> SqlAlchemyStoryboardRepository:
        return self.storyboard_repo

    async def create_scene(self, project_id: str, sequence_number: int, title: str, description: str, narrative_scene_id: Optional[str]) -> StoryboardScene:
        now = self.clock.now()
        scene = StoryboardScene(
            scene_id=self.id_generator.new("sscene"), project_id=project_id,
            narrative_scene_id=narrative_scene_id, sequence_number=sequence_number,
            title=title, description=description, created_at=now, updated_at=now,
        )
        await self.storyboard_repo.add_scene(scene)
        return scene

    async def create_shot(self, scene_id: str, project_id: str, shot_number: int, description: str, framing: str, camera_angle: str) -> Shot:
        now = self.clock.now()
        shot = Shot(
            shot_id=self.id_generator.new("shot"), scene_id=scene_id, project_id=project_id,
            shot_number=shot_number, description=description, framing=framing,
            camera_angle=camera_angle, created_at=now, updated_at=now,
        )
        await self.storyboard_repo.add_shot(shot)
        return shot
