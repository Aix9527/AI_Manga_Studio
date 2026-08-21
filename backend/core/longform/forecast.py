class ResourceForecast:



    def estimate(
        self,
        episodes,
        shots,
        avg_video_minutes
    ):


        total_shots = (
            episodes *
            shots
        )


        return {


        "shots":
        total_shots,


        "gpu_hours":
        total_shots *
        0.5,


        "storage_gb":
        total_shots *
        0.3,


        "estimated_days":
        total_shots /
        50


        }
