from .base import ProviderAdapter



class CosyVoiceProvider(
    ProviderAdapter
):


    name="cosyvoice"



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
        4

        }



    def generate(
        self,
        request
    ):

        return {

        "status":
        "queued"

        }
