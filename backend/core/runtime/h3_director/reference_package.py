"""Reference Package Builder（GPT 设计 P0）

每镜自动生成：
{
  "shot_id": "gx003",
  "ref_images": [{"type": "character", "id": "suwan_v3", "ref": "...", "source": "image|prompt"}, ...],
  "scene_dna": {...},
  "previous_shot_state": {...}
}

→ 映射 H3 Omni Reference ref_images[]
"""
from .context_schema import (
    ReferencePackage
)

from .reference_selector import (
    ReferenceSelector
)


class ReferencePackageBuilder:

    def __init__(self, selector=None):

        self.selector=selector or ReferenceSelector()


    def build(
        self,
        shot_id,
        characters=None,
        expressions=None,
        locations=None,
        props=None,
        scene_dna=None,
        previous_shot_state=None
    ):


        items=self.selector.select(
            characters,
            expressions,
            locations,
            props
        )


        # 图片类（H3 ref_images 只接受图；prompt 类用于提示词注入）
        ref_images=[

            i.__dict__

            for i in items

            if i.source == "image"

        ]


        prompt_refs=[

            i.__dict__

            for i in items

            if i.source == "prompt"

        ]


        package=ReferencePackage(

            shot_id=shot_id,

            ref_images=ref_images,

            ref_videos=[],

            ref_audios=[],

            scene_dna=scene_dna or {},

            previous_shot_state=previous_shot_state or {}

        )


        return {

        "shot_id":
        shot_id,

        "ref_images":
        ref_images,

        "ref_videos":
        [],

        "ref_audios":
        [],

        "prompt_references":
        prompt_refs,

        "scene_dna":
        scene_dna or {},

        "previous_shot_state":
        previous_shot_state or {},

        "omni_usage":{

            "ref_images_slots":
            len(ref_images),

            "max_ref_images":
            9,

            "ref_videos_slots":
            0,

            "max_ref_videos":
            3,

            "ref_audios_slots":
            0,

            "max_ref_audios":
            3

        }

        }


reference_package_builder=ReferencePackageBuilder()
