
"""Character repository implementation."""

import json

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from backend.modules.characters.domain.character import Character, CharacterVersion
from backend.modules.characters.infrastructure.models import CharacterModel, CharacterVersionModel
from backend.shared.errors import NotFoundError


class SqlAlchemyCharacterRepository:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def add(self, character: Character) -> None:
        model = CharacterModel(
            id=character.character_id, project_id=character.project_id, name=character.name,
            role=character.role, personality=character.personality, background=character.background,
            appearance_json=json.dumps(character.appearance, ensure_ascii=False),
            current_version_id=character.current_version_id, is_active=character.is_active,
            created_at=character.created_at, updated_at=character.updated_at, revision=character.revision,
        )
        async with self._session_factory() as session:
            session.add(model)
            await session.commit()

    async def get(self, character_id: str) -> Character:
        async with self._session_factory() as session:
            result = await session.execute(select(CharacterModel).where(CharacterModel.id == character_id))
            m = result.scalar_one_or_none()
            if m is None:
                raise NotFoundError("Character", character_id)
            return Character(character_id=m.id, project_id=m.project_id, name=m.name, role=m.role,
                             personality=m.personality, background=m.background,
                             appearance=json.loads(m.appearance_json),
                             current_version_id=m.current_version_id, is_active=m.is_active,
                             created_at=m.created_at, updated_at=m.updated_at, revision=m.revision)

    async def list_by_project(self, project_id: str) -> list[Character]:
        async with self._session_factory() as session:
            result = await session.execute(
                select(CharacterModel).where(CharacterModel.project_id == project_id).order_by(CharacterModel.created_at)
            )
            models = result.scalars().all()
            return [Character(character_id=m.id, project_id=m.project_id, name=m.name, role=m.role,
                              personality=m.personality, background=m.background,
                              appearance=json.loads(m.appearance_json),
                              current_version_id=m.current_version_id, is_active=m.is_active,
                              created_at=m.created_at, updated_at=m.updated_at, revision=m.revision) for m in models]

    async def add_version(self, version: CharacterVersion) -> None:
        model = CharacterVersionModel(
            id=version.version_id, character_id=version.character_id,
            version_number=version.version_number, snapshot_json=version.snapshot_json,
            change_description=version.change_description, created_at=version.created_at,
            updated_at=version.created_at, revision=1,
        )
        async with self._session_factory() as session:
            session.add(model)
            await session.commit()
