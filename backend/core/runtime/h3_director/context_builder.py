"""Context Builder + Director Prompt（GPT 设计）

ContextBuilder：组装镜头完整上下文（Reference Package + Scene DNA + Continuity Chain）
DirectorPrompt：将上下文注入最终 H3 提示词（场景 DNA 固定描述 / 前镜状态续接 / 参考说明）
"""
from .reference_package import (
    ReferencePackageBuilder
)

from .scene_memory import (
    SceneMemory
)

from .shot_chain import (
    ShotChain
)

from .context_schema import (
    SceneVisualDNA
)


class ContextBuilder:

    def __init__(self):

        self.package_builder=ReferencePackageBuilder()

        self.memory=SceneMemory()

        self.chain=ShotChain()


    def build(
        self,
        shot_id,
        characters=None,
        expressions=None,
        locations=None,
        props=None,
        register_scene=None
    ):

        # 1. Scene DNA（有则记忆复用；无则注册）
        scene_dna={}

        if locations:

            dna=self.memory.get(
                locations[0]
            )

            if dna is None and register_scene:

                dna=register_scene

                self.memory.upsert(
                    dna
                )

            if dna:

                scene_dna=dna.__dict__


        # 2. 前镜状态
        prev_state=self.chain.previous_state(
            shot_id
        )


        # 3. Reference Package
        package=self.package_builder.build(
            shot_id,
            characters,
            expressions,
            locations,
            props,
            scene_dna,
            prev_state
        )


        return package


context_builder=ContextBuilder()


class DirectorPrompt:
    """
    注入三段上下文到 H3 提示词：
    [REFERENCE LOCK]    参考图锁定（角色/场景/道具一致性）
    [SCENE VISUAL DNA]  场景固定视觉描述
    [CONTINUITY]        前镜状态续接
    """


    def enhance(
        self,
        prompt,
        package
    ):


        blocks=[]


        # 参考锁定
        ref_images=package.get(
            "ref_images",
            []
        )

        if ref_images:

            lines=[

                "[REFERENCE LOCK] Use these reference images as exact identity:"

            ]

            for r in ref_images:

                lines.append(

                    f"- {r.get('type')} {r.get('id')} ({r.get('ref')}) must stay consistent in every frame"

                )

            blocks.append(
                "\n".join(
                    lines
                )
            )


        # 场景 DNA
        dna=package.get(
            "scene_dna",
            {}
        )

        if dna:

            lines=[]

            lines.append(
                "[SCENE VISUAL DNA] This location's visual identity is fixed:"
            )

            for key in (
                "name",
                "architecture",
                "lighting",
                "color",
                "camera",
                "fixed_objects"
            ):

                val=dna.get(
                    key
                )

                if val:

                    lines.append(
                        f"- {key}: {', '.join(val) if isinstance(val, list) else val}"
                    )

            blocks.append(
                "\n".join(
                    lines
                )
            )


        # 前镜续接
        prev=package.get(
            "previous_shot_state",
            {}
        )

        if prev:

            bits=[]

            if prev.get(
                "character_pose"
            ):

                bits.append(
                    "character keeps pose " + prev["character_pose"]
                )

            if prev.get(
                "camera_position"
            ):

                bits.append(
                    "camera continues from " + prev["camera_position"]
                )

            if bits:

                blocks.append(
                    "[CONTINUITY] " + "; ".join(
                        bits
                    )
                )


        if not blocks:

            return prompt


        return prompt + "\n\n" + "\n\n".join(
            blocks
        )


director_prompt=DirectorPrompt()
