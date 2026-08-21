from .comfyui import ComfyUIProvider



class WanProvider(
    ComfyUIProvider
):


    name="wan"



    def validate(
        self,
        request
    ):


        return {

        "model":
        "wan2.2",

        "ready":
        True

        }
