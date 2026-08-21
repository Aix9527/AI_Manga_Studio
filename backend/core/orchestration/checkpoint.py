import json


from ..domain.ids import create_id


from ..storage.orchestration_models import (
CheckpointRecord
)



class CheckpointService:



    def __init__(
        self,
        db
    ):

        self.db=db



    def save(
        self,
        task_id,
        stage,
        state
    ):


        item=CheckpointRecord(

            id=create_id(
                "checkpoint"
            ),

            task_id=task_id,

            stage=stage,

            state_json=json.dumps(
                state,
                ensure_ascii=False
            ),

            completed=1

        )


        self.db.add(item)

        self.db.commit()


        return item.id



    def latest(
        self,
        task_id
    ):


        return (

            self.db.query(
                CheckpointRecord
            )

            .filter_by(
                task_id=task_id
            )

            .order_by(
                CheckpointRecord.stage.desc()
            )

            .first()

        )
