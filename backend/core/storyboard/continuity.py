import json


from ..domain.ids import create_id


from ..storage.storyboard_models import (
    SceneContinuityRecord
)



class ContinuityService:



    def __init__(
        self,
        db
    ):

        self.db=db



    def update(
        self,
        scene_id,
        data
    ):


        obj=(

            self.db.query(
                SceneContinuityRecord
            )

            .filter_by(
                scene_id=scene_id
            )

            .first()

        )


        if not obj:


            obj=SceneContinuityRecord(

                id=create_id(
                    "continuity"
                ),

                scene_id=scene_id

            )


            self.db.add(
                obj
            )



        obj.time_state=data.get(
            "time",
            ""
        )


        obj.location_state=data.get(
            "location",
            ""
        )


        obj.weather=data.get(
            "weather",
            ""
        )


        obj.lighting=data.get(
            "lighting",
            ""
        )


        obj.character_state_json=json.dumps(
            data.get(
                "characters",
                {}
            )
        )


        self.db.commit()


        return obj.id
