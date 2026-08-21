from fastapi import APIRouter


from backend.core.validation.dag_stress import (
DAGStressValidator
)


from backend.core.validation.stability_runner import (
StabilityRunner
)


from backend.core.validation.recovery_validator import (
RecoveryValidator
)


from backend.core.validation.migration_validator import (
MigrationValidator
)


from backend.core.validation.browser_acceptance import (
BrowserAcceptanceValidator
)


from backend.core.validation.release_gate import (
ReleaseGate
)



router=APIRouter()



@router.post(
"/dag/stress"
)
def dag(body:dict):


    return DAGStressValidator().build(

        body.get(
            "episodes",
            100
        ),

        body.get(
            "shots",
            10
        )

    )




@router.post(
"/stability"
)
def stability(body:dict):


    return StabilityRunner().run(

        body.get(
            "hours",
            20
        )

    )





@router.post(
"/recovery"
)
def recovery(body:dict):


    return RecoveryValidator().test(

        body["failure"]

    )





@router.post(
"/migration"
)
def migration(body:dict):


    return MigrationValidator().validate(

        body["database"],

        body["assets"]

    )





@router.get(
"/browser"
)
def browser():

    return BrowserAcceptanceValidator().run()




@router.post(
"/release"
)
def release(body:dict):


    return ReleaseGate().evaluate(

        body["checks"]

    )
