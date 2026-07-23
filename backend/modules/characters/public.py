
"""Characters module public API."""

from dataclasses import dataclass

from backend.modules.characters.domain.character import Character
from backend.modules.characters.infrastructure.repository import SqlAlchemyCharacterRepository
from backend.shared.ids import IdGenerator
from backend.shared.time import Clock


@dataclass(slots=True)
class CharactersModuleApi:
    character_repo: SqlAlchemyCharacterRepository
    id_generator: IdGenerator
    clock: Clock

    @property
    def _character_repo(self) -> SqlAlchemyCharacterRepository:
        return self.character_repo

    async def create(self, project_id: str, name: str, role: str, personality: str) -> Character:
        now = self.clock.now()
        character = Character(
            character_id=self.id_generator.new("char"),
            project_id=project_id, name=name, role=role, personality=personality,
            created_at=now, updated_at=now,
        )
        await self.character_repo.add(character)
        return character
