"""首尾帧控制（GPT 设计 P2）

Keyframe A + Prompt + Keyframe B → H3 first/last frame

对接现有 ChainManager（backend/video/chain_manager.py）：
- 同空间连续镜头 → last_frame 模式（start_image = 上一镜尾帧）
- 换场景 → keyframe / reset
"""
from backend.video.chain_manager import (
    ChainManager,
    ChainLink,
    KeyframeMemory
)

from .context_schema import (
    ReferenceItem
)


class FrameController:

    def __init__(self):

        self.chain=ChainManager()


    def plan(
        self,
        shot_id,
        location_id=None,
        time_of_day=None,
        prev_location=None,
        prev_time=None
    ):
        """
        首尾帧策略：
        same space → last_frame（start_image=上一镜尾帧，end 自由）
        换场景     → keyframe（新关键帧起，可指定 end_frame 目标帧）
        """

        if (
            prev_location
            and prev_location == location_id
            and prev_time
            and prev_time == time_of_day
        ):

            last=self.chain.memory.last()

            mode="last_frame"

            start_image=last.get(
                "last_frame",
                ""
            )

            note="tail_chain"

        else:

            mode="keyframe"

            start_image=""

            note="scene_break" if prev_location else "first_shot"


        link=ChainLink(

            shot_id=shot_id,

            mode=mode,

            start_image=start_image,

            note=note

        )


        return {

        "shot_id":
        shot_id,

        "mode":
        link.mode,

        "start_image":
        link.start_image,

        "end_frame":{

            "required":
            mode == "keyframe",

            "strategy":
            "generate_storyboard_keyframe"

        },

        "note":
        link.note

        }


    def advance(
        self,
        shot_id,
        last_frame_path,
        location=None,
        time_of_day=None
    ):

        self.chain.advance(
            shot_id,
            last_frame_path,
            {

                "location":
                location,

                "time_of_day":
                time_of_day

            }
        )


        return {

        "ok":
        True,

        "shot_id":
        shot_id,

        "last_frame":
        last_frame_path

        }


frame_controller=FrameController()
