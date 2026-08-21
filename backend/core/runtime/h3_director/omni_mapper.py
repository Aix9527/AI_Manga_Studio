"""Omni Reference 自动分配（GPT 设计 P3）

H3 Omni Reference：9 图 + 3 视频 + 3 音频 槽位自动分配

ref_images（固定 5 基位 + 4 扩展）：
  1 角色身份  2 服装  3 场景  4 关键道具  5 上一镜结束帧  6-9 表情/扩展参考

ref_videos（3）：
  动作参考 / 镜头运动参考 / 表演参考

ref_audios（3）：
  角色声音 / 情绪 / 节奏
"""
from .reference_selector import (
    ReferenceSelector
)

from .scene_memory import (
    SceneMemory
)


SLOT_PLAN={

    "ref_images":[

        {"slot": 1, "type": "character_identity"},
        {"slot": 2, "type": "character_costume"},
        {"slot": 3, "type": "location"},
        {"slot": 4, "type": "prop"},
        {"slot": 5, "type": "last_frame"},
        {"slot": 6, "type": "expression", "optional": True},
        {"slot": 7, "type": "expression", "optional": True},
        {"slot": 8, "type": "location_alt", "optional": True},
        {"slot": 9, "type": "action", "optional": True}

    ],

    "ref_videos":[

        "action_reference",
        "camera_motion_reference",
        "performance_reference"

    ],

    "ref_audios":[

        "character_voice",
        "emotion_voice",
        "rhythm_voice"

    ]

}


class OmniMapper:

    def __init__(self):

        self.selector=ReferenceSelector()


    def assign(
        self,
        shot_id,
        characters=None,
        expressions=None,
        locations=None,
        props=None,
        last_frame=None,
        ref_videos=None,
        ref_audios=None
    ):

        items=self.selector.select(
            characters,
            expressions,
            locations,
            props
        )


        by_type={}

        for it in items:

            by_type.setdefault(
                it.type,
                []
            ).append(
                it
            )


        ref_images=[]

        used_by_type={}

        for slot in SLOT_PLAN["ref_images"]:

            t=slot["type"]

            map_key={

                "character_identity": "character",
                "character_costume": "costume",
                "last_frame": "last_frame",
                "location_alt": "location",
                "action": "action"

            }.get(t, t)


            pool=by_type.get(
                map_key
            )


            item=None

            if t == "last_frame" and last_frame:

                item={

                "type":
                "last_frame",

                "id":
                f"{shot_id}_prev_tail",

                "ref":
                last_frame,

                "source":
                "image",

                "priority":
                5

                }

            elif pool:

                idx=used_by_type.get(
                    map_key,
                    0
                )

                if idx < len(
                    pool
                ):

                    item=pool[idx].__dict__

                    used_by_type[map_key]=idx + 1


            if item:

                item["slot"]=slot["slot"]

                ref_images.append(
                    item
                )


        videos=[]

        for idx, vt in enumerate(
            SLOT_PLAN["ref_videos"]
        ):

            src=(ref_videos or {}).get(
                vt
            )

            videos.append({

            "slot":
            idx + 1,

            "type":
            vt,

            "ref":
            src or "",

            "source":
            "video" if src else "empty"

            })


        audios=[]

        for idx, at in enumerate(
            SLOT_PLAN["ref_audios"]
        ):

            src=(ref_audios or {}).get(
                at
            )

            audios.append({

            "slot":
            idx + 1,

            "type":
            at,

            "ref":
            src or "",

            "source":
            "audio" if src else "empty"

            })


        return {

        "shot_id":
        shot_id,

        "ref_images":
        ref_images,

        "ref_videos":
        videos,

        "ref_audios":
        audios,

        "slots_used":{

            "images":
            len(
                [r for r in ref_images if r.get("source") in ("image", "video")]
            ),

            "videos":
            len(
                [v for v in videos if v.get("source") == "video"]
            ),

            "audios":
            len(
                [a for a in audios if a.get("source") == "audio"]
            )

        },

        "max_capacity":{

            "images":
            9,

            "videos":
            3,

            "audios":
            3

        }

        }


omni_mapper=OmniMapper()
