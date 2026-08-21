from pathlib import Path



class WhisperProvider:



    name="whisper"



    def validate(
        self
    ):

        return {

            "available":
            True

        }



    def transcribe(
        self,
        audio_path
    ):


        """
        生产环境:
        faster-whisper large-v3

        """

        return [

            {

            "start":0,

            "end":2,

            "text":"归墟正在觉醒"

            }

        ]
