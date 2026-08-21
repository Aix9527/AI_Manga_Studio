import hashlib

import json

from pathlib import Path


from ..domain.ids import create_id


from ..storage.media_models import (
ExportPackageRecord
)



class ExportEvidenceService:



    def sha256(
        self,
        path
    ):


        h=hashlib.sha256()


        with open(
            path,
            "rb"
        ) as f:


            h.update(
                f.read()
            )


        return h.hexdigest()



    def create(
        self,
        db,
        project_id,
        output,
        metadata
    ):


        record=ExportPackageRecord(

            id=create_id(
                "export"
            ),

            project_id=project_id,

            format="mp4",

            resolution=
            metadata.get(
                "resolution",
                ""
            ),

            path=output,

            status="completed"

        )


        db.add(
            record
        )

        db.commit()



        return {


        "export_id":
        record.id,


        "sha256":
        self.sha256(
            output
        )

        }
