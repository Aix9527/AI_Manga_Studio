
"""Media asset repository implementation."""

import json

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from backend.modules.media.domain.asset import Asset, AssetVersion
from backend.modules.media.infrastructure.models import AssetModel, AssetVersionModel
from backend.shared.errors import NotFoundError


class SqlAlchemyAssetRepository:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def add(self, asset: Asset) -> None:
        model = AssetModel(
            id=asset.asset_id, project_id=asset.project_id, name=asset.name,
            mime_type=asset.mime_type, file_size=asset.file_size,
            tags_json=json.dumps(asset.tags, ensure_ascii=False),
            current_version_id=asset.current_version_id,
            created_at=asset.created_at, updated_at=asset.updated_at, revision=asset.revision,
        )
        async with self._session_factory() as session:
            session.add(model)
            await session.commit()

    async def get(self, asset_id: str) -> Asset:
        async with self._session_factory() as session:
            result = await session.execute(select(AssetModel).where(AssetModel.id == asset_id))
            m = result.scalar_one_or_none()
            if m is None:
                raise NotFoundError("Asset", asset_id)
            return Asset(asset_id=m.id, project_id=m.project_id, name=m.name, mime_type=m.mime_type,
                         file_size=m.file_size, tags=json.loads(m.tags_json),
                         current_version_id=m.current_version_id,
                         created_at=m.created_at, updated_at=m.updated_at, revision=m.revision)

    async def list_by_project(self, project_id: str) -> list[Asset]:
        async with self._session_factory() as session:
            result = await session.execute(
                select(AssetModel).where(AssetModel.project_id == project_id).order_by(AssetModel.created_at.desc())
            )
            models = result.scalars().all()
            return [Asset(asset_id=m.id, project_id=m.project_id, name=m.name, mime_type=m.mime_type,
                          file_size=m.file_size, tags=json.loads(m.tags_json),
                          current_version_id=m.current_version_id,
                          created_at=m.created_at, updated_at=m.updated_at, revision=m.revision) for m in models]

    async def add_version(self, version: AssetVersion) -> None:
        model = AssetVersionModel(
            id=version.version_id, asset_id=version.asset_id, version_number=version.version_number,
            content_hash=version.content_hash, relative_path=version.relative_path,
            mime_type=version.mime_type, file_size=version.file_size,
            metadata_json=version.metadata_json, provenance_json=version.provenance_json,
            created_at=version.created_at, updated_at=version.created_at, revision=1,
        )
        async with self._session_factory() as session:
            session.add(model)
            await session.commit()

    async def list_versions(self, asset_id: str) -> list[AssetVersion]:
        async with self._session_factory() as session:
            result = await session.execute(
                select(AssetVersionModel)
                .where(AssetVersionModel.asset_id == asset_id)
                .order_by(AssetVersionModel.version_number.desc())
            )
            models = result.scalars().all()
            return [AssetVersion(version_id=m.id, asset_id=m.asset_id, version_number=m.version_number,
                                 content_hash=m.content_hash, relative_path=m.relative_path,
                                 mime_type=m.mime_type, file_size=m.file_size,
                                 metadata_json=m.metadata_json, provenance_json=m.provenance_json,
                                 created_at=m.created_at) for m in models]

    async def get_latest_version(self, asset_id: str) -> AssetVersion | None:
        async with self._session_factory() as session:
            result = await session.execute(
                select(AssetVersionModel)
                .where(AssetVersionModel.asset_id == asset_id)
                .order_by(AssetVersionModel.version_number.desc())
                .limit(1)
            )
            m = result.scalar_one_or_none()
            if m is None:
                return None
            return AssetVersion(version_id=m.id, asset_id=m.asset_id, version_number=m.version_number,
                                content_hash=m.content_hash, relative_path=m.relative_path,
                                mime_type=m.mime_type, file_size=m.file_size,
                                metadata_json=m.metadata_json, provenance_json=m.provenance_json,
                                created_at=m.created_at)
