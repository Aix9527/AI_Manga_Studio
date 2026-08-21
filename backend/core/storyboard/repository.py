import json


from ..domain.ids import create_id


from ..storage.storyboard_models import (
    ShotBoardRecord,
    SceneContinuityRecord
)



class StoryboardRepository:



    def __init__(
        self,
        db
    ):

        self.db=db



    def create_board(
        self,
        shot_id,
        data
    ):


        board=ShotBoardRecord(

            id=create_id(
                "shotboard"
            ),

            shot_id=shot_id,

            shot_size=data.get(
                "shot_size",
                ""
            ),

            camera_move=data.get(
                "camera_move",
                ""
            ),

            composition_json=json.dumps(
                data.get(
                    "composition",
                    {}
                )
            ),

            action_json=json.dumps(
                data.get(
                    "action",
                    {}
                )
            ),

            prompt_text=data.get(
                "prompt",
                ""
            ),

            duration=data.get(
                "duration",
                5
            )

        )


        self.db.add(
            board
        )


        self.db.commit()


        return board.id



    def get_board(
        self,
        shot_id
    ):


        return (

            self.db.query(
                ShotBoardRecord
            )

            .filter_by(
                shot_id=shot_id
            )

            .first()

        )
