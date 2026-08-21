"""Voice Production OS · 引擎注册表（GPT 设计）"""
from .cosyvoice3 import CosyVoice3Provider
from .indextts2 import IndexTTS2Provider
from .gpt_sovits import GPTSoVITSProvider
from .voice_provider import VoiceProvider
from .voice_router import VoiceRouter


VOICE_PROVIDERS={

    "cosyvoice3":
    CosyVoice3Provider(),

    "indextts2":
    IndexTTS2Provider(),

    "gpt_sovits":
    GPTSoVITSProvider()

}


def get_provider(
    name
):


    return VOICE_PROVIDERS.get(
        name
    )


def list_providers():


    return {

        name: provider.health()

        for name, provider in VOICE_PROVIDERS.items()

    }


voice_router=VoiceRouter()
