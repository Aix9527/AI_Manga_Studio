from __future__ import annotations

from datetime import datetime



class ProductionTwinService:
    """
    Production Digital Twin

    反映：

    - 当前集数进度
    - 镜头完成率
    - GPU 状态
    - 存储状态
    - QC 状态
    - 队列状态

    """


    def calculate_progress(
        self,
        episodes
    ):


        if not episodes:

            return 0


        completed = sum(

            1

            for episode in episodes

            if episode.get(
                "status"
            )
            ==
            "completed"

        )


        return round(

            completed /
            len(episodes)
            *
            100,

            2

        )




    def snapshot(
        self,
        project_id: str,
        episodes: list,
        tasks: list,
        gpu_state: dict,
        storage_state: dict,
        quality_state: dict
    ):


        return {


            "project_id":

            project_id,


            "production":

            {


                "episodes":

                len(episodes),


                "progress":

                self.calculate_progress(
                    episodes
                ),


                "tasks":

                len(tasks)

            },


            "gpu":

            gpu_state,


            "storage":

            storage_state,


            "quality":

            quality_state,


            "health":

            self.health_check(

                gpu_state,

                quality_state

            ),


            "updated_at":

            datetime.utcnow()
            .isoformat()

        }




    def health_check(
        self,
        gpu_state,
        quality_state
    ):


        if gpu_state.get(
            "oom"
        ):

            return "warning"


        if quality_state.get(
            "failed",
            0
        ) > 10:

            return "warning"


        return "normal"
