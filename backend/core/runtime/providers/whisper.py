from .base import ProviderAdapter



class WhisperProvider(
    ProviderAdapter
):


    name="whisper"



    def validate(
        self,
        request
    ):

        return {

        "ready":
        True

        }



    def estimate(
        self,
        request
    ):

        return {

        "vram_gb":
        2

        }



    def generate(
        self,
        request
    ):

        return {

        "status":
        "queued"

        }
