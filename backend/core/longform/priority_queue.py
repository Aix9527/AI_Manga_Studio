from enum import IntEnum



class LongformPriority(IntEnum):

    P0=0

    P1=1

    P2=2

    P3=3




class LongformQueue:



    def create_task(
        self,
        shot_group,
        priority=LongformPriority.P2
    ):


        return {


            "task_id":
            f"lf_task_{shot_group.id}",


            "priority":
            int(priority),


            "group":
            shot_group.id,


            "status":
            "queued"

        }
