from fastapi import APIRouter


from backend.core.longform.batch_scheduler import (
SceneBatchScheduler
)


from backend.core.longform.vram_predictor import (
VRAMPredictor
)


from backend.core.longform.recovery_test import (
RecoveryStressTester,
FailureMode
)



router=APIRouter()



@router.post(
"/batch/schedule"
)
def batch_schedule(
    body:dict
):


    return SceneBatchScheduler().schedule_episode(

        body["episode"],

        body["scenes"]

    )





@router.post(
"/vram/predict"
)
def vram_predict(
    body:dict
):


    return VRAMPredictor().estimate(

        body["model"],

        body["resolution"],

        body["duration"]

    )





@router.post(
"/recovery/test"
)
def recovery_test(
    body:dict
):


    return RecoveryStressTester().simulate(

        FailureMode(
            body["failure"]
        )

    )
