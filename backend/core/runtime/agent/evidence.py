import json


from ...domain.ids import create_id


from ...storage.runtime_models import (
    ProductionEvidenceRecord
)



class EvidenceRecorder:



    def __init__(
        self,
        db
    ):

        self.db=db



    def record(
        self,
        run_id,
        evidence_type,
        data
    ):


        item=ProductionEvidenceRecord(

            id=create_id(
                "evidence"
            ),

            run_id=run_id,

            evidence_type=evidence_type,

            content_json=json.dumps(
                data,
                ensure_ascii=False
            )

        )


        self.db.add(item)

        self.db.commit()


        return item.id
