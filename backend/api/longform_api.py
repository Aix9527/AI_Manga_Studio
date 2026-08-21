from fastapi import APIRouter


from backend.core.longform.scheduler import (
SeasonScheduler
)

from backend.core.longform.forecast import (
ResourceForecast
)

from backend.core.longform.stress import (
StressTester
)


router=APIRouter()



@router.post(
"/schedule"
)
def schedule(body:dict):


    return SeasonScheduler().build_plan(

        body["episodes"],

        body["shots"]

    )





@router.post(
"/forecast"
)
def forecast(body:dict):


    return ResourceForecast().estimate(

        body["episodes"],

        body["shots"],

        body.get(
            "duration",
            1
        )

    )





@router.post(
"/stress"
)
def stress(body:dict):


    return StressTester().simulate(

        body["episodes"],

        body["shots"]

    )
