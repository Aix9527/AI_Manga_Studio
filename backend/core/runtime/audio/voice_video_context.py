"""镜头级声音上下文（GPT 设计）"""


class VoiceVideoContext:
    """
    镜头级 voice context

    {
      "shot_id": "gx005",
      "characters": ["fangjueming", "suwan"],
      "voice_context": [{"character": "fangjueming", "provider": "gpt_sovits", "asset": "fangjueming_v1"}],
      "h3_mode": "reference"
    }
    """


    def build(
        self,
        shot_id,
        characters,
        assets,
        h3_mode="reference"
    ):


        voice_context=[]

        for ch in characters:

            asset=assets.get(
                ch
            )

            if asset:

                voice_context.append({

                    "character":
                    ch,

                    "provider":
                    asset.get(
                        "provider",
                        "gpt_sovits"
                    ),

                    "asset":
                    asset.get(
                        "asset",
                        f"{ch}_v1"
                    )

                })


        return {

        "shot_id":
        shot_id,

        "characters":
        characters,

        "voice_context":
        voice_context,

        "h3_mode":
        h3_mode

        }
