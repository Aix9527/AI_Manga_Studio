"""H3 Audio Reference Bridge（GPT 设计）"""
from .audio_reference import (
    AudioReferenceBuilder
)

from .voice_video_context import (
    VoiceVideoContext
)


class H3AudioBridge:
    """
    角色声音资产 → H3 REF2VA 参考音频 → 表演一致

    桥接 Voice Production OS 与 H3 视频后端：
    - 输入：镜头级 voice context + H3 provider request
    - 输出：注入 ref_audios 的 H3 reference prompt 构建请求
    """


    def __init__(self):

        self.ref_builder=AudioReferenceBuilder()

        self.context=VoiceVideoContext()


    def build_shot_context(
        self,
        shot_id,
        characters,
        assets,
        h3_mode="reference"
    ):


        return self.context.build(
            shot_id,
            characters,
            assets,
            h3_mode
        )


    def build_reference_request(
        self,
        shot_id,
        characters,
        assets,
        shot=None,
        profile="production",
        orientation="landscape",
        params=None
    ):


        shot_ctx=self.build_shot_context(
            shot_id,
            characters,
            assets
        )


        refs=self.ref_builder.build(
            shot_ctx["voice_context"],
            shot
        )


        request={

        "workflow":
        "reference",

        "profile":
        profile,

        "orientation":
        orientation,

        "params":
        params or {},

        "filename_prefix":
        f"AI_Manga_Studio/H3/{shot_id}"

        }


        request.update(
            refs
        )


        return {

        "shot_context":
        shot_ctx,

        "h3_request":
        request,

        "reference_inputs":
        refs

        }
