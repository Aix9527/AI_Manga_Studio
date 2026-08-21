from fastapi import APIRouter

from backend.core.storage.database import SessionLocal

from backend.core.storage.models import (
    ProductionRunRecord,
    QualityEvaluationRecord
)


router=APIRouter()



@router.get("/runs")
def production_runs():

    db=SessionLocal()


    rows=(
        db.query(
            ProductionRunRecord
        )
        .all()
    )


    result=[]


    for r in rows:

        result.append(
            {
                "id":r.id,
                "shot_id":r.shot_id,
                "seed":r.seed,
                "cfg":r.cfg,
                "steps":r.steps,
                "motion_profile":
                    r.motion_profile
            }
        )


    db.close()


    return result



@router.get("/quality")
def quality():

    db=SessionLocal()


    rows=(
        db.query(
            QualityEvaluationRecord
        )
        .all()
    )


    result=[

        {
            "shot_id":q.shot_id,
            "score":q.score,
            "result":q.result
        }

        for q in rows

    ]


    db.close()

    return result
