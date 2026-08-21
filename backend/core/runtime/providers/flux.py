from .comfyui import ComfyUIProvider



class FluxProvider(
    ComfyUIProvider
):


    name="flux"



    def validate(
        self,
        request
    ):


        return {

        "model":
        "flux",

        "ready":
        True

        }
