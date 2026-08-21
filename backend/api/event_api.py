from fastapi import APIRouter
from fastapi.responses import StreamingResponse

import time


router=APIRouter()



@router.get("/stream")
def stream():


    def generator():

        while True:

            yield (
                "data: heartbeat\n\n"
            )

            time.sleep(5)



    return StreamingResponse(
        generator(),
        media_type="text/event-stream"
    )
