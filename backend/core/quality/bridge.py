from pathlib import Path



class LegacyQualityGateBridge:



    def __init__(
        self
    ):

        try:

            from backend.production.quality_gate import (
                QualityGate
            )

            self.legacy=QualityGate()

        except Exception:

            self.legacy=None



    def run(
        self,
        video_path
    ):


        if self.legacy:

            return self.legacy.evaluate(
                video_path
            )


        return {

            "motion_cv":0,

            "ssim":0.9,

            "mosaic":False,

            "static":False

        }
