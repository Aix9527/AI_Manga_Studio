"""CosyVoice 3 · 角色演员系统（GPT 设计）"""
from pathlib import Path

from ...domain.ids import create_id

from .voice_provider import VoiceProvider


class CosyVoice3Provider(
    VoiceProvider
):
    """
    主角对白 / 连续剧角色配音

    角色风格（《归墟觉醒·天倾》）：
    - suwan:      calm / analytical     冷静分析
    - fangjueming: pressure / dominant  压迫式对白
    - chenye:     deep / mysterious     神秘低沉
    - zhaoyiming: technical / nervous   技术员语气
    """

    name = "cosyvoice3"


    CHARACTER_STYLES={

        "suwan":{
            "style":"calm analytical",
            "desc":"冷静分析"
        },

        "fangjueming":{
            "style":"pressure dominant",
            "desc":"压迫式对白"
        },

        "chenye":{
            "style":"deep mysterious",
            "desc":"神秘低沉"
        },

        "zhaoyiming":{
            "style":"technical nervous",
            "desc":"技术员语气"
        }

    }


    def generate(
        self,
        request
    ):


        style=self.CHARACTER_STYLES.get(
            request.character_id,
            {
                "style":
                "neutral"
            }
        )["style"]


        if request.style:

            style=request.style


        output=f"outputs/voice/{request.character_id}_{create_id('seg')}.wav"

        Path(
            output
        ).parent.mkdir(
            parents=True,
            exist_ok=True
        )


        # 实际环境调用 CosyVoice 3 CLI/API
        Path(output).touch()


        return {

        "provider":
        self.name,

        "audio_path":
        output,

        "character_id":
        request.character_id,

        "emotion":
        request.emotion,

        "style":
        style,

        "speed":
        request.speed,

        "sample_rate":
        request.sample_rate,

        "duration":
        round(
            len(request.text) * 0.05 / request.speed,
            2
        )

        }


    def clone(
        self,
        request
    ):


        return {

        "voice_asset":
        request.character_id,

        "reference_audio":
        request.reference_audio,

        "language":
        request.language,

        "provider":
        self.name

        }


    def health(self):


        return {

        "provider":
        self.name,

        "available":
        True,

        "role":
        "character_actor"

        }
