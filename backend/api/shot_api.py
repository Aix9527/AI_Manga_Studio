from fastapi import APIRouter

from backend.core.storage.database import SessionLocal
from backend.core.storage.models import (
    ShotRecord,
    ProductionRunRecord,
    QualityEvaluationRecord,
    PromptRecipeRecord
)


router=APIRouter()



@router.get("")
def list_shots():

    db=SessionLocal()


    rows=(
        db.query(
            ShotRecord
        )
        .all()
    )


    result=[]


    for s in rows:

        result.append(
            {
                "id":s.id,
                "name":s.name,
                "status":s.status
            }
        )


    db.close()


    return result


@router.get("/{shot_id}")
def shot_detail(
    shot_id:str
):

    db=SessionLocal()


    shot=(
        db.query(
            ShotRecord
        )
        .filter_by(
            id=shot_id
        )
        .first()
    )


    if not shot:

        db.close()

        return {
            "error":"shot not found"
        }



    run=(
        db.query(
            ProductionRunRecord
        )
        .filter_by(
            shot_id=shot.id
        )
        .first()
    )


    qc=(
        db.query(
            QualityEvaluationRecord
        )
        .filter_by(
            shot_id=shot.id
        )
        .first()
    )


    prompt=(
        db.query(
            PromptRecipeRecord
        )
        .filter_by(
            shot_id=shot.id
        )
        .first()
    )



    result={

        "shot":{

            "id":shot.id,

            "name":shot.name,

            "status":shot.status

        },

        "production":

        {

            "seed":
                run.seed if run else "",

            "cfg":
                run.cfg if run else "",

            "steps":
                run.steps if run else "",

            "motion_profile":
                run.motion_profile if run else ""

        },


        "quality":

        {

            "score":
                qc.score if qc else "",

            "result":
                qc.result if qc else ""

        },


        "prompt":

        {

            "text":
                prompt.prompt_text if prompt else ""

        }

    }


    db.close()


    return result
