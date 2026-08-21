from fastapi import APIRouter

from fastapi.responses import StreamingResponse

import json


from backend.core.tasks.queue import task_queue

from backend.core.tasks.event_bus import event_bus



router=APIRouter()



@router.post("")

def create_task(
    body:dict
):


    return task_queue.create(

        project_id=
        body.get(
            "project_id",
            ""
        ),

        shot_id=
        body.get(
            "shot_id",
            ""
        ),

        stage=
        body.get(
            "stage",
            0
        ),

        priority=
        body.get(
            "priority",
            2
        )

    ).__dict__




@router.get("")

def list_tasks():

    return [

        t.__dict__

        for t in task_queue.list()

    ]





@router.post("/{task_id}/{action}")
def control_task(
    task_id:str,
    action:str
):


    task=task_queue.control(

        task_id,

        action

    )


    if not task:

        return {
            "error":
            "task not found"
        }


    return task.__dict__



@router.get("/stream")

def stream():


    async def generator():


        async for event in event_bus.stream():


            yield (

                "data: "

                +

                json.dumps(
                    event,
                    ensure_ascii=False
                )

                +

                "\n\n"

            )


    return StreamingResponse(

        generator(),

        media_type=
        "text/event-stream"

    )
