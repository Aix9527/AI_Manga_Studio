import requests


from .base import ProviderAdapter



class ComfyUIProvider(
    ProviderAdapter
):


    name="comfyui"



    def __init__(
        self,
        url="http://127.0.0.1:8188"
    ):

        self.url=url



    def validate(
        self,
        request
    ):


        return {

        "available":True,

        "endpoint":self.url

        }



    def estimate(
        self,
        request
    ):


        return {

        "vram_gb":
        request.get(
            "vram_required",
            12
        )

        }



    def generate(
        self,
        request
    ):


        response=requests.post(

            self.url+"/prompt",

            json=request

        )


        return response.json()
