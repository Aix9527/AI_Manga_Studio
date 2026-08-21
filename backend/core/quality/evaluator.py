import json

from datetime import datetime


from ..domain.ids import create_id


from ..storage.models import (
    QualityEvaluationRecord
)



class QualityEvaluator:



    def __init__(
        self,
        db
    ):

        self.db=db




    def evaluate(
        self,
        asset_id,
        shot_id,
        gate,
        metrics
    ):


        score=self.calculate_score(
            metrics
        )


        result=(

            "PASS"

            if score >= 80

            else

            "FAIL"

        )



        obj=QualityEvaluationRecord(

            id=create_id(
                "quality"
            ),

            asset_id=asset_id,

            shot_id=shot_id,

            gate=gate,

            score=score,

            result=result,

            evidence_json=json.dumps(
                metrics,
                ensure_ascii=False
            ),

            created_at=datetime.now()
            .isoformat()

        )


        self.db.add(
            obj
        )

        self.db.commit()



        return obj




    def calculate_score(
        self,
        metrics
    ):


        weights={


        "motion_cv":0.3,

        "ssim":0.3,

        "mosaic":0.2,

        "static":0.2

        }



        score=100



        if metrics.get(
            "mosaic",
            False
        ):

            score-=40



        if metrics.get(
            "static",
            False
        ):

            score-=20



        motion=metrics.get(
            "motion_cv",
            0
        )


        if motion>0.65:

            score-=20



        ssim=metrics.get(
            "ssim",
            1
        )


        if ssim<0.83:

            score-=20



        return max(
            0,
            score
        )
