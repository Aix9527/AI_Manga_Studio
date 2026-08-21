from fastapi import APIRouter


from backend.core.storage.database import SessionLocal


from backend.core.orchestration.checkpoint import (
CheckpointService
)


router=APIRouter()



@router.post("/checkpoint")
def checkpoint(
    body:dict
):


    db=SessionLocal()


    service=CheckpointService(
        db
    )


    cid=service.save(

        body["task_id"],

        body["stage"],

        body.get(
            "state",
            {}
        )

    )


    db.close()


    return {

    "checkpoint_id":
    cid

    }
