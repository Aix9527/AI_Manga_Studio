from ..domain.ids import create_id


from ..storage.models import (
    DefectRecord
)



class DefectService:



    def __init__(
        self,
        db
    ):

        self.db=db



    def create(
        self,
        shot_id,
        category,
        message,
        severity="medium"
    ):


        obj=DefectRecord(

            id=create_id(
                "defect"
            ),

            shot_id=shot_id,

            category=category,

            severity=severity,

            message=message

        )


        self.db.add(
            obj
        )


        self.db.commit()


        return obj.id
