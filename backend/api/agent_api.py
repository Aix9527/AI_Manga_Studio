from fastapi import APIRouter


from backend.core.storage.database import SessionLocal


from backend.core.runtime.agent.executor import (
AgentExecutor
)



router=APIRouter()



@router.post("/execute")
def execute(
    body:dict
):


    db=SessionLocal()


    executor=AgentExecutor(
        db
    )


    run_id=executor.execute(

        body["skill_id"],

        body.get(
            "task_id",
            ""
        ),

        body.get(
            "input",
            {}
        ),

        {

        "model":
        body.get(
            "model",
            ""
        ),

        "workflow":
        body.get(
            "workflow",
            ""
        ),

        "result":
        "completed"

        }

    )


    db.close()


    return {

        "run_id":
        run_id,

        "status":
        "completed"

    }
