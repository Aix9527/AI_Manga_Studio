"""IndexTTS2 · 电影旁白系统（GPT 设计）"""
from pathlib import Path

from ...domain.ids import create_id

from .voice_provider import VoiceProvider


class IndexTTS2Provider(
    VoiceProvider
):
    """
    影视级旁白 + 情绪控制

    适用：预告片旁白、片头、世界观介绍、史诗感 narration
    """

    name = "indextts2"


    NARRATION_STYLES={

        "documentary":{
            "style":"documentary",
            "desc":"世界观介绍"
        },

        "epic":{
            "style":"epic",
            "desc":"史诗 narration"
        },

        "trailer":{
            "style":"trailer",
            "desc":"预告片旁白"
        },

        "opening":{
            "style":"opening",
            "desc":"片头开场"
        }

    }


    def generate(
        self,
        request
    ):


        style=request.style or "documentary"


        output=f"outputs/voice/narration_{create_id('seg')}.wav"

        Path(
            output
        ).parent.mkdir(
            parents=True,
            exist_ok=True
        )


        # 实际环境调用 IndexTTS2 CLI/API
        Path(output).touch()


        return {

        "provider":
        self.name,

        "audio_path":
        output,

        "style":
        style,

        "emotion":
        request.emotion,

        "speed":
        request.speed,

        "duration":
        round(
            len(request.text) * 0.055 / request.speed,
            2
        )

        }


    def clone(
        self,
        request
    ):


        # IndexTTS2 不提供独立克隆；交由 CosyVoice3 clone
        return {

        "provider":
        self.name,

        "supported":
        False,

        "fallback":
        "cosyvoice3"

        }


    def health(self):


        return {

        "provider":
        self.name,

        "available":
        True,

        "role":
        "narration"

        }
