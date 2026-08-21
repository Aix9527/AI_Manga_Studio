from ..domain.ids import create_id



class RepairPlanner:



    def create_repair_task(
        self,
        defect
    ):


        return {

            "task_id":
            create_id(
                "repair"
            ),

            "shot_id":
            defect.shot_id,

            "reason":
            defect.category,

            "priority":
            "P1"

        }
