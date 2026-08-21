import json


from ..domain.ids import create_id


from ..storage.creative_models import (
    ChangeProposalRecord
)



class ChangeProposalService:



    def __init__(
        self,
        db
    ):

        self.db=db




    def create(
        self,
        project_id,
        target_type,
        target_id,
        operation,
        diff
    ):


        obj=ChangeProposalRecord(

            id=create_id(
                "proposal"
            ),

            project_id=project_id,

            target_type=target_type,

            target_id=target_id,

            operation=operation,

            diff_json=json.dumps(
                diff,
                ensure_ascii=False
            )

        )


        self.db.add(
            obj
        )


        self.db.commit()


        return obj.id




    def approve(
        self,
        proposal_id
    ):


        obj=(

            self.db.query(
                ChangeProposalRecord
            )

            .filter_by(
                id=proposal_id
            )

            .first()

        )


        if obj:

            obj.status="approved"

            self.db.commit()



        return obj
