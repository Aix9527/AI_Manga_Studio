"""H3 Director Context Engine API（GPT 设计）

POST /api/core/h3/director/package     每镜 Reference Package
POST /api/core/h3/director/compose     组装提示词 + 注入上下文（DNA/续接/参考锁定）
POST /api/core/h3/director/scene       注册 Scene Visual DNA
POST /api/core/h3/director/end-shot    记录镜头结束状态（Shot Continuity Chain）
GET  /api/core/h3/director/memory      场景记忆列表
"""
from fastapi import APIRouter

import os

from backend.core.runtime.h3_director.context_builder import (
    context_builder,
    director_prompt
)

from backend.core.runtime.h3_director.scene_memory import (
    scene_memory
)

from backend.core.runtime.h3_director.shot_chain import (
    shot_chain
)

from backend.core.runtime.h3_director.context_schema import (
    SceneVisualDNA
)

from backend.core.runtime.h3_director.frame_control import (
    frame_controller
)

from backend.core.runtime.h3_director.omni_mapper import (
    omni_mapper
)

from backend.core.runtime.h3_director.shot_expansion import (
    shot_expander
)

from backend.core.runtime.h3_prompt.matcher import (
    H3PromptMatcher
)

from backend.core.runtime.h3_prompt.composer import (
    H3PromptComposer
)


router=APIRouter()

matcher=H3PromptMatcher()

composer=H3PromptComposer()


@router.post("/package")
def build_package(
    body:dict
):
    """
    每镜 Reference Package：
    {shot_id, characters?, expressions?, locations?, props?, register_scene?}
    """


    return context_builder.build(
        body["shot_id"],
        body.get(
            "characters"
        ),
        body.get(
            "expressions"
        ),
        body.get(
            "locations"
        ),
        body.get(
            "props"
        ),
        body.get(
            "register_scene"
        )
    )


@router.post("/compose")
def director_compose(
    body:dict
):
    """
    组装 H3 提示词并注入上下文：
    {shot_id, scene, characters?, expressions?, locations?, props?, register_scene?, dialogue?, ...}
    """


    package=context_builder.build(
        body["shot_id"],
        body.get(
            "characters"
        ),
        body.get(
            "expressions"
        ),
        body.get(
            "locations"
        ),
        body.get(
            "props"
        ),
        body.get(
            "register_scene"
        )
    )


    matched=matcher.match(
        body["scene"],
        body.get(
            "aspect_ratio",
            "16:9"
        )
    )


    composed=composer.compose(
        matched["template"],
        body["scene"],
        body.get(
            "character"
        ),
        body.get(
            "setting"
        ),
        body.get(
            "emotion"
        ),
        body.get(
            "dialogue"
        ),
        body.get(
            "voice_reference"
        ),
        body.get(
            "on_screen_text"
        ),
        body.get(
            "duration_s"
        ),
        body.get(
            "aspect_ratio"
        )
    )


    enhanced=director_prompt.enhance(
        composed["prompt"],
        package
    )


    # H3-13A.1：ShotChain v2 接入
    # 模式判定：body.continuity 显式指定；否则按前一镜推断
    mode=body.get(
        "continuity",
        ""
    )

    prev_state=shot_chain.previous_state(
        body["shot_id"]
    )

    if not mode:

        if prev_state:

            prev_mode=prev_state.get(
                "mode",
                "tail_chain"
            )

            mode=(
                "transition"
                if prev_mode == "transition"
                else "tail_chain"
            )

        else:

            mode="scene_lock"

    prev_tail=shot_chain.to_reference(
        body["shot_id"]
    ) if mode != "transition" else ""


    package["continuity"]={
        "mode": mode,
        "previous_shot": prev_state.get("shot_id") if prev_state else None,
        "previous_tail_frame": prev_tail,
    }


    if prev_tail:

        package.setdefault(
            "ref_images",
            []
        ).append(
            {
                "type": "tail_frame",
                "id": f"prev_{prev_state.get('shot_id')}",
                "ref": prev_tail,
                "source": "image" if os.path.exists(
                    os.path.join(
                        os.getcwd(),
                        prev_tail
                    )
                ) else "prompt",
            }
        )


    return {

    "shot_id":
    body["shot_id"],

    "template_id":
    composed["template_id"],

    "template_title":
    composed["template_title"],

    "match_score":
    matched["score"],

    "workflow":
    composed["workflow"],

    "prompt":
    enhanced,

    "reference_package":
    package

    }


@router.post("/scene")
def register_scene(
    body:dict
):


    dna=SceneVisualDNA(

        location_id=body["location_id"],

        name=body.get(
            "name",
            ""
        ),

        architecture=body.get(
            "architecture",
            []
        ),

        lighting=body.get(
            "lighting",
            []
        ),

        color=body.get(
            "color",
            []
        ),

        camera=body.get(
            "camera",
            ""
        ),

        fixed_objects=body.get(
            "fixed_objects",
            []
        ),

        description=body.get(
            "description",
            ""
        )

    )


    scene_memory.upsert(
        dna
    )


    return {

    "ok":
    True,

    "scene":
    dna.__dict__

    }


@router.post("/end-shot")
def end_shot(
    body:dict
):


    state=shot_chain.record_end(
        body["shot_id"],
        body.get(
            "character_pose",
            ""
        ),
        body.get(
            "camera_position",
            ""
        ),
        body.get(
            "lighting_state",
            ""
        ),
        body.get(
            "note",
            ""
        )
    )


    return state


@router.get("/memory")
def memory_list():


    return scene_memory.list()


@router.post("/frame-plan")
def frame_plan(
    body:dict
):
    """
    首尾帧策略（P2）：
    {shot_id, location_id?, time_of_day?, prev_location?, prev_time?}
    """


    return frame_controller.plan(
        body["shot_id"],
        body.get(
            "location_id"
        ),
        body.get(
            "time_of_day"
        ),
        body.get(
            "prev_location"
        ),
        body.get(
            "prev_time"
        )
    )


@router.post("/frame-advance")
def frame_advance(
    body:dict
):
    """
    记录镜头尾帧（P2 续接）：
    {shot_id, last_frame_path, location?, time_of_day?}
    """


    return frame_controller.advance(
        body["shot_id"],
        body["last_frame_path"],
        body.get(
            "location"
        ),
        body.get(
            "time_of_day"
        )
    )


@router.post("/omni")
def omni_assign(
    body:dict
):
    """
    Omni Reference 自动分配（P3）：
    {shot_id, characters?, expressions?, locations?, props?, last_frame?, ref_videos?, ref_audios?}
    """


    return omni_mapper.assign(
        body["shot_id"],
        body.get(
            "characters"
        ),
        body.get(
            "expressions"
        ),
        body.get(
            "locations"
        ),
        body.get(
            "props"
        ),
        body.get(
            "last_frame"
        ),
        body.get(
            "ref_videos"
        ),
        body.get(
            "ref_audios"
        )
    )


@router.post("/expand")
def shot_expand(
    body:dict
):
    """
    Shot Expansion（P4）：
    {shot_id, scene, characters?, locations?, sub_duration_s?, character?, setting?, emotion?, dialogue?, voice_reference?, on_screen_text?}
    """


    return shot_expander.expand(
        body["shot_id"],
        body["scene"],
        body.get(
            "characters"
        ),
        body.get(
            "locations"
        ),
        body.get(
            "sub_duration_s",
            5
        ),
        **{
            k: v
            for k, v in body.items()
            if k in (
                "character",
                "setting",
                "emotion",
                "dialogue",
                "voice_reference",
                "on_screen_text",
                "aspect_ratio"
            )
        }
    )
