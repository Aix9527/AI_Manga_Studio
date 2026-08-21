class ProductionDigitalTwin:



    def snapshot(
        self,
        project_id,
        tasks,
        gpu
    ):


        return {


        "project":
        project_id,


        "running_tasks":
        tasks,


        "gpu":
        gpu,


        "health":
        "normal"

        }
