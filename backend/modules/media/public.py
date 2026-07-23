
"""Media module public API."""

from dataclasses import dataclass

from backend.modules.media.infrastructure.repository import SqlAlchemyAssetRepository
from backend.shared.ids import IdGenerator
from backend.shared.time import Clock


@dataclass(slots=True)
class MediaModuleApi:
    asset_repo: SqlAlchemyAssetRepository
    id_generator: IdGenerator
    clock: Clock

    @property
    def _asset_repo(self) -> SqlAlchemyAssetRepository:
        return self.asset_repo
