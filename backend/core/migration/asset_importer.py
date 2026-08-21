from pathlib import Path

from ..domain.ids import (
    create_id,
    sha256_file
)

from ..storage.models import AssetRecord

from ..storage.asset_repository import AssetRepository



class AssetImporter:


    def __init__(self, db):

        self.db=db

        self.repo=AssetRepository(db)



    def import_file(
        self,
        project_id,
        project_root,
        file:Path
    ):


        digest=sha256_file(
            str(file)
        )


        relative=str(
            file.relative_to(
                project_root
            )
        )


        asset=(
            self.db.query(
                AssetRecord
            )
            .filter_by(
                project_id=project_id,
                relative_path=relative
            )
            .first()
        )


        if not asset:


            asset=AssetRecord(

                id=create_id(
                    "asset"
                ),

                project_id=project_id,

                asset_type=file.suffix.lower(),

                name=file.name,

                relative_path=relative
            )


            self.db.add(asset)

            self.db.commit()



        version=self.repo.create_asset_version(

            asset.id,

            str(file),

            digest

        )


        return asset,version
