from fastapi import APIRouter


from backend.core.runtime.router import ModelRouter

from backend.core.runtime.workflow_registry import (
    WorkflowRegistry
)

from backend.core.runtime.scheduler import scheduler

from backend.core.runtime.providers.h3 import (
    H3Provider
)



router=APIRouter()



@router.post("/route")
def route(
    body:dict
):


    return ModelRouter().select(
        body
    )



@router.post("/h3/prompt")
def h3_prompt(
    body:dict
):


    return H3Provider().build_prompt(
        body
    )



@router.get("/h3/validate")
def h3_validate():


    return H3Provider().validate(
        {
            "workflow":
            "standard",

            "profile":
            "production"
        }
    )



@router.get("/workflows")
def workflows():


    return WorkflowRegistry().list()



@router.post("/vram/acquire")
def vram_acquire(
    body:dict
):


    ok=scheduler.acquire(

        body.get(
            "required",
            12
        )

    )


    return {

    "granted":
    ok

    }



@router.post("/vram/release")
def vram_release():


    scheduler.release()


    return {

    "released":
    True

    }
