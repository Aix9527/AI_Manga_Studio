from fastapi import APIRouter


from backend.core.storage.database import SessionLocal


from backend.core.quality.evaluator import (
QualityEvaluator
)


from backend.core.quality.defect import (
DefectService
)


from backend.core.quality.executor import (
QualityExecutor
)



router=APIRouter()



@router.post("/run")
def run_quality(
    body:dict
):


    db=SessionLocal()


    result=QualityExecutor(
        db
    ).run(

        body["asset_id"],

        body["shot_id"],

        body["video_path"]

    )


    db.close()


    return result



@router.post("/evaluate")
def evaluate(
    body:dict
):


    db=SessionLocal()


    result=QualityEvaluator(
        db
    ).evaluate(

        body.get(
            "asset_id"
        ),

        body.get(
            "shot_id"
        ),

        body.get(
            "gate",
            "video_temporal"
        ),

        body.get(
            "metrics",
            {}
        )

    )


    result_id=result.id

    result_score=result.score

    result_result=result.result

    db.close()


    return {

        "id":
        result_id,

        "score":
        result_score,

        "result":
        result_result

    }





@router.post("/defect")
def defect(
    body:dict
):


    db=SessionLocal()


    did=DefectService(
        db
    ).create(

        body["shot_id"],

        body["category"],

        body["message"]

    )


    db.close()


    return {

        "defect_id":
        did

    }
