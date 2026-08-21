class AudioMixer:



    def build_filter(
        self,
        dialogue,
        music,
        sfx
    ):


        inputs=[]


        if dialogue:
            inputs.append(
                "[0:a]"
            )

        if music:
            inputs.append(
                "[1:a]"
            )

        if sfx:
            inputs.append(
                "[2:a]"
            )



        return (

            "".join(inputs)

            +

            "amix=inputs=3:duration=longest"

        )
