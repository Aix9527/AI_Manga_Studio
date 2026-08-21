class VRAMPredictor:



    MODEL_COST={

        "wan22_i2v_5b":
        12,

        "minimax_h3_fl2va":
        14,

        "minimax_h3_ref2va":
        14,

        "flux":
        8,

        "cosyvoice":
        4,

        "whisper":
        3

    }



    def estimate(
        self,
        model:str,
        resolution:str,
        duration:int
    ):


        base=self.MODEL_COST.get(
            model,
            8
        )


        if resolution=="1080p":

            base*=1.25



        return {


            "required_vram_gb":
            round(
                base,
                2
            ),


            "safe":
            base <= 14,


            "duration":
            duration

        }
