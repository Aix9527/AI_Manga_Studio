"""Shot Expansion（GPT 设计 P4）

一个 12s 镜头 → 3 × 5s Sub Shot（A 进入 / B 表演 / C 表情收尾）
→ 各自生成 H3 提示词 → FFmpeg 拼接

不硬拉 frames（显存/质量下降），用子镜头分段 + 拼接
"""
from .context_builder import (
    ContextBuilder,
    director_prompt
)

from .shot_chain import (
    ShotChain
)

from backend.core.runtime.h3_prompt.matcher import (
    H3PromptMatcher
)

from backend.core.runtime.h3_prompt.composer import (
    H3PromptComposer
)


# 子镜头结构模板（12s → 3 × 5s）
SUB_SHOT_BEATS={

    "A":{

        "name":
        "enter",

        "label":
        "进入/开场",

        "instruction":
        "开场：角色进入场景或镜头建立环境"

    },

    "B":{

        "name":
        "action",

        "label":
        "表演/主体",

        "instruction":
        "主体：核心动作与对白展开"

    },

    "C":{

        "name":
        "emotion",

        "label":
        "情绪/收尾",

        "instruction":
        "收尾：情绪特写与镜头定格，为下一镜留衔接点"

    }

}


class ShotExpander:

    def __init__(self):

        self.matcher=H3PromptMatcher()

        self.composer=H3PromptComposer()

        self.chain=ShotChain()


    def expand(
        self,
        shot_id,
        scene,
        characters=None,
        locations=None,
        sub_duration_s=5,
        **compose_kwargs
    ):
        """
        单镜头 → 3 子镜头提示词 + FFmpeg 拼接命令
        """

        subs=[]

        prev=self.chain.previous_state(
            shot_id
        )

        for key, beat in SUB_SHOT_BEATS.items():

            sub_scene=(
                beat["instruction"]
                + "。"
                + scene
            )

            if prev and key == "A":

                sub_scene += (
                    "。续接上一镜："
                    + (prev.get("character_pose") or "")
                )


            matched=self.matcher.match(
                sub_scene,
                compose_kwargs.get(
                    "aspect_ratio",
                    "16:9"
                )
            )


            composed=self.composer.compose(
                matched["template"],
                sub_scene,
                compose_kwargs.get(
                    "character"
                ),
                compose_kwargs.get(
                    "setting"
                ),
                compose_kwargs.get(
                    "emotion"
                ),
                compose_kwargs.get(
                    "dialogue"
                ),
                compose_kwargs.get(
                    "voice_reference"
                ),
                compose_kwargs.get(
                    "on_screen_text"
                ),
                sub_duration_s,
                compose_kwargs.get(
                    "aspect_ratio"
                )
            )


            subs.append({

            "sub":
            key,

            "beat":
            beat["name"],

            "label":
            beat["label"],

            "duration_s":
            sub_duration_s,

            "prompt":
            composed["prompt"],

            "template_id":
            composed["template_id"]

            })


        # FFmpeg 拼接命令（concat 协议）
        concat_cmd=(

            "ffmpeg -y "
            + " ".join(
                f"-i sub_{key.lower()}.mp4"
                for key in SUB_SHOT_BEATS
            )
            + " -filter_complex "
            + "".join(
                f"[{i}:v][{i}:a]"
                for i in range(
                    len(SUB_SHOT_BEATS)
                )
            )
            + f"concat=n={len(SUB_SHOT_BEATS)}:v=1:a=1[outv][outa] -map [outv] -map [outa] {shot_id}_expanded.mp4"

        )


        return {

        "shot_id":
        shot_id,

        "strategy":
        "shot_expansion_3x5s",

        "total_duration_s":
        sub_duration_s * len(
            SUB_SHOT_BEATS
        ),

        "sub_shots":
        subs,

        "ffmpeg_concat":
        concat_cmd

        }


shot_expander=ShotExpander()
