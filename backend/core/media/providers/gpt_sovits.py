"""GPT-SoVITS · 角色 IP 声音资产库（GPT 设计）"""
from pathlib import Path

from ...domain.ids import create_id

from .voice_provider import VoiceProvider


class GPTSoVITSProvider(
    VoiceProvider
):
    """
    角色声音永久资产

    30 秒声音样本 → 训练 → Character Voice Asset → 100 集复用
    """

    name = "gpt_sovits"


    ASSET_ROOT=Path(
        "outputs/voice_assets"
    )


    def _asset_dir(
        self,
        character_id
    ):

        return self.ASSET_ROOT / f"{character_id}_v1"


    def has_asset(
        self,
        character_id
    ):

        return (
            self._asset_dir(
                character_id
            ) / "metadata.yaml"
        ).exists()


    def generate(
        self,
        request
    ):


        if not self.has_asset(
            request.character_id
        ):

            return {

            "provider":
            self.name,

            "available":
            False,

            "reason":
            "no_voice_asset",

            "fallback":
            "cosyvoice3"

            }


        output=f"outputs/voice/{request.character_id}_asset_{create_id('seg')}.wav"

        Path(
            output
        ).parent.mkdir(
            parents=True,
            exist_ok=True
        )


        # 实际环境调用 GPT-SoVITS 推理
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

        "speed":
        request.speed,

        "voice_asset":
        f"{request.character_id}_v1"

        }


    def clone(
        self,
        request
    ):


        asset_dir=self._asset_dir(
            request.character_id
        )

        asset_dir.mkdir(
            parents=True,
            exist_ok=True
        )


        # 30 秒样本落地 → 训练占位（实际环境执行 GPT-SoVITS 训练）
        ref=asset_dir / "reference.wav"

        sample_path=Path(
            request.reference_audio
        )

        sample_path.parent.mkdir(
            parents=True,
            exist_ok=True
        )

        sample_path.touch()

        ref.touch()


        meta=asset_dir / "metadata.yaml"

        meta.write_text(
            "\n".join(
                [
                    "character_id: "
                    + request.character_id,
                    "provider: gpt_sovits",
                    "language: "
                    + request.language,
                    "reference: "
                    + request.reference_audio,
                    "status: training_ready",
                ]
            ),
            encoding="utf-8"
        )


        return {

        "voice_asset":
        f"{request.character_id}_v1",

        "asset_dir":
        str(
            asset_dir
        ),

        "status":
        "training_ready",

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
        "voice_identity"

        }
