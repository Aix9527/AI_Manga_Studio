from .metrics import VideoMetrics

from .evaluator import QualityEvaluator

from .defect import DefectService

from .repair import RepairPlanner



class QualityExecutor:



    def __init__(
        self,
        db
    ):

        self.db=db

        self.metrics=VideoMetrics()



    def run(
        self,
        asset_id,
        shot_id,
        video_path
    ):


        metrics=self.metrics.calculate(
            video_path
        )


        evaluation=QualityEvaluator(
            self.db
        ).evaluate(

            asset_id,

            shot_id,

            "video_temporal",

            metrics

        )


        if evaluation.result=="FAIL":


            defect_id=DefectService(
                self.db
            ).create(

                shot_id,

                "video_quality",

                str(metrics),

                "high"

            )


            repair=RepairPlanner().create_repair_task(

                type(
                    "Defect",
                    (),
                    {
                    "shot_id":shot_id,
                    "category":"video_quality"
                    }

                )()

            )


            return {

                "result":
                "FAIL",

                "defect_id":
                defect_id,

                "repair":
                repair

            }


        return {

            "result":
            "PASS",

            "score":
            evaluation.score

        }
