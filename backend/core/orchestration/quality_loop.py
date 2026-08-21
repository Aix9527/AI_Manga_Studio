from ..quality.executor import QualityExecutor

from .retry import RetryPolicy



class QualityRetryLoop:



    def __init__(
        self,
        db
    ):

        self.db=db

        self.retry=RetryPolicy()



    def process(
        self,
        task,
        video_path
    ):


        result=QualityExecutor(
            self.db
        ).run(

            task.asset_id,

            task.shot_id,

            video_path

        )


        if result["result"]=="FAIL":


            if self.retry.can_retry(
                task.failure_count
            ):


                task.status="retry"

                task.failure_count+=1


            else:

                task.status="manual_review"



            self.db.commit()



        else:

            task.status="completed"

            self.db.commit()



        return result
