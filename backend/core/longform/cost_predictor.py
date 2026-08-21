from dataclasses import dataclass



@dataclass
class ProductionEstimate:

    episodes:int

    total_shots:int

    gpu_hours:float

    storage_gb:float

    estimated_days:float

    retry_cost_hours:float

    estimated_cost:float



class DynamicCostPredictor:
    """
    长剧动态成本预测

    输入：

    episodes
    shots_per_episode
    retry_rate
    gpu_price


    输出：

    GPU时间
    存储
    周期
    成本

    """


    def __init__(self):

        self.video_gpu_hour = 0.5

        self.video_storage_gb = 0.3




    def predict(
        self,
        episodes:int,
        shots_per_episode:int,
        retry_rate:float = 0.1,
        gpu_hour_price:float = 0
    ):


        total_shots = (

            episodes *
            shots_per_episode

        )


        base_gpu_hours = (

            total_shots *
            self.video_gpu_hour

        )


        retry_hours = (

            base_gpu_hours *
            retry_rate

        )


        total_gpu = (

            base_gpu_hours +
            retry_hours

        )


        storage = (

            total_shots *
            self.video_storage_gb

        )


        days = (

            total_gpu /
            24

        )



        cost = (

            total_gpu *
            gpu_hour_price

        )



        result = ProductionEstimate(

            episodes=episodes,

            total_shots=total_shots,

            gpu_hours=round(
                total_gpu,
                2
            ),

            storage_gb=round(
                storage,
                2
            ),

            estimated_days=round(
                days,
                2
            ),

            retry_cost_hours=round(
                retry_hours,
                2
            ),

            estimated_cost=round(
                cost,
                2
            )

        )


        return result.__dict__
