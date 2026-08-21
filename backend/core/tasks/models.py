from dataclasses import dataclass, field

from datetime import datetime

from ..domain.ids import create_id



class TaskPriority:

    P0=0

    P1=1

    P2=2

    P3=3



@dataclass
class Task:


    id:str = field(
        default_factory=lambda:
        create_id("task")
    )


    project_id:str=""

    shot_id:str=""


    stage:int=0


    priority:int=TaskPriority.P2


    status:str="queued"


    progress:int=0


    error:str=""


    retry_count:int=0


    created_at:str=field(

        default_factory=lambda:

        datetime.now().isoformat()

    )
