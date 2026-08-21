"""Voice Production OS · 路由与回退（GPT 设计）"""
from .cosyvoice3 import CosyVoice3Provider
from .indextts2 import IndexTTS2Provider
from .gpt_sovits import GPTSoVITSProvider
from .voice_provider import VoiceProvider


class VoiceRouter:
    """
    三引擎分层路由

    scene.type:
      dialogue  → cosyvoice3
      narration → indextts2
      character.voice_asset exists → gpt_sovits

    优先级：P0 Character Consistency > P1 Emotion > P2 Speed > P3 Cost
    """


    def __init__(
        self,
        gpt_sovits=None
    ):

        self.gpt_sovits=gpt_sovits or GPTSoVITSProvider()


    def select(
        self,
        scene_type="dialogue",
        character_id=None
    ):


        if scene_type == "narration":

            return {

            "provider":
            "indextts2",

            "role":
            "narration",

            "confidence":
            0.95,

            "fallback":[
                "cosyvoice3",
                "cosyvoice"
            ]

            }


        # dialogue / 其他
        if (
            character_id
            and self.gpt_sovits.has_asset(
                character_id
            )
        ):

            return {

            "provider":
            "gpt_sovits",

            "role":
            "voice_identity",

            "confidence":
            0.9,

            "fallback":[
                "cosyvoice3",
                "cosyvoice"
            ]

            }


        return {

        "provider":
        "cosyvoice3",

        "role":
        "character_actor",

        "confidence":
        0.92,

        "fallback":[
            "gpt_sovits",
            "cosyvoice"
        ]

        }


    def resolve(
        self,
        scene_type="dialogue",
        character_id=None
    ):


        route=self.select(
            scene_type,
            character_id
        )


        return route
