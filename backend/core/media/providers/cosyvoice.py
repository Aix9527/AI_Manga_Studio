from pathlib import Path

from ...domain.ids import create_id


class CosyVoiceProvider:


    name="cosyvoice"


    def validate(
        self
    ):


        return {

            "available":
            True

        }



    def estimate(
        self,
        text
    ):


        return {

            "seconds":
            len(text)*0.05

        }



    def generate(
        self,
        text,
        voice,
        output
    ):


        """
        实际环境调用 CosyVoice CLI/API。
        当前实现保留统一 Provider Contract。
        """

        Path(output).touch()


        return {


            "asset_id":
            create_id(
                "voice_asset"
            ),


            "path":
            output,


            "provider":
            self.name

        }
