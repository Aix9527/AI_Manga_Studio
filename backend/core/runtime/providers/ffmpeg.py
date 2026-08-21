from .base import ProviderAdapter



class FFmpegProvider(
    ProviderAdapter
):


    name="ffmpeg"



    def validate(
        self,
        request
    ):


        return {

        "binary":
        "ffmpeg",

        "ready":
        True

        }



    def estimate(
        self,
        request
    ):


        return {

        "vram_gb":
        0

        }



    def generate(
        self,
        request
    ):


        return {

        "status":
        "completed"

        }
