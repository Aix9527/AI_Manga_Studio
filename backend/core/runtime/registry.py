import json

from ..domain.ids import create_id

from ..storage.runtime_models import (
    ModelArtifactRecord,
    WorkflowVersionRecord
)



class ModelRegistry:


    def __init__(
        self,
        db
    ):

        self.db=db



    def register_model(
        self,
        data
    ):


        obj=ModelArtifactRecord(

            id=create_id(
                "model"
            ),

            name=data["name"],

            model_type=data["type"],

            provider=data["provider"],

            sha256=data.get(
                "sha256",
                ""
            ),

            path=data.get(
                "path",
                ""
            )

        )


        self.db.add(obj)

        self.db.commit()


        return obj.id




    def register_workflow(
        self,
        data
    ):


        obj=WorkflowVersionRecord(

            id=create_id(
                "workflow"
            ),

            name=data["name"],

            version=data.get(
                "version",
                "v1"
            ),

            provider=data["provider"],

            config_json=json.dumps(
                data.get(
                    "config",
                    {}
                )
            )

        )


        self.db.add(obj)

        self.db.commit()


        return obj.id
