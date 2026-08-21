"""音频参考装配（GPT 设计）"""


class AudioReferenceBuilder:
    """
    构建 H3 REF2VA 的 ref_audios / ref_images / ref_videos 输入

    角色声音资产 → {"ref_audios": [{"character_id": ..., "audio": ...}]}
    """


    def build_ref_audios(
        self,
        voice_context
    ):


        """

        voice_context: [{"character": "fangjueming", "provider": "gpt_sovits", "asset": "fangjueming_v1"}]

        → [{"character_id": "fangjueming", "audio": "outputs/voice_assets/fangjueming_v1/reference.wav"}]

        """

        refs=[]

        for ctx in voice_context:

            asset=ctx.get(
                "asset",
                ""
            )

            if not asset:

                continue


            refs.append({

                "character_id":
                ctx["character"],

                "audio":
                f"outputs/voice_assets/{asset}/reference.wav"

            })


        return refs


    def build_ref_images(
        self,
        shot
    ):


        """

        shot: {"ref_images": ["char_a.png", "char_b.png"]}

        """

        return shot.get(
            "ref_images",
            []
        )


    def build_ref_video(
        self,
        shot
    ):


        return shot.get(
            "ref_video",
            ""
        )


    def build(
        self,
        voice_context,
        shot=None
    ):


        result={}


        ref_audios=self.build_ref_audios(
            voice_context
        )

        if ref_audios:

            result["ref_audios"]=ref_audios


        shot=shot or {}


        images=self.build_ref_images(
            shot
        )

        if images:

            result["ref_images"]=images


        video=self.build_ref_video(
            shot
        )

        if video:

            result["ref_video"]=video


        return result
