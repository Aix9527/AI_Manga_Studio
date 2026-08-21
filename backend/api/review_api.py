from fastapi import APIRouter

from backend.core.storage.database import SessionLocal

from backend.core.storage.models import (
    QualityEvaluationRecord,
    DefectRecord
)

from backend.core.domain.ids import create_id



router=APIRouter()



@router.get("/quality")
def quality_list():


    db=SessionLocal()


    rows=(
        db.query(
            QualityEvaluationRecord
        )
        .all()
    )


    result=[

        {

        "id":q.id,

        "shot_id":q.shot_id,

        "score":q.score,

        "result":q.result

        }

        for q in rows

    ]


    db.close()


    return result





@router.post("/defects")
def create_defect(
    body:dict
):


    db=SessionLocal()


    defect=DefectRecord(

        id=create_id(
            "defect"
        ),

        shot_id=
        body.get(
            "shot_id",
            ""
        ),

        category=
        body.get(
            "category",
            ""
        ),

        description=
        body.get(
            "description",
            ""
        )

    )


    db.add(defect)

    db.commit()

    db.close()


    return {

        "status":
        "created"

    }
