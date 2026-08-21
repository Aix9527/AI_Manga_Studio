"""H3 提示词组装器：模板 + 小说场景 → 逐秒分镜 H3 提示词"""
import re


class H3PromptAssembler:
    """
    基于匹配模板生成可用于 MiniMax H3 的完整提示词

    - 保留模板的逐段分镜结构（SCENE / SHOT BREAKDOWN / CAMERA / LIGHTING / AUDIO / AVOID）
    - 将 SCENE 段替换/增强为小说场景内容（{scene} / {character} / {setting}）
    - 对白注入 AUDIO 段
    - 可选注入文字约束（UI 文字）
    """


    def _build_scene_block(
        self,
        scene,
        character=None,
        setting=None
    ):


        parts=[]

        if character:

            parts.append(
                "Character: " + character
            )

        if setting:

            parts.append(
                "Setting: " + setting
            )

        parts.append(
            "Scene: " + scene
        )


        return "\n".join(parts)


    def assemble(
        self,
        template,
        scene,
        character=None,
        setting=None,
        dialogue=None,
        on_screen_text=None,
        duration_s=None,
        aspect_ratio=None
    ):


        prompt=template["prompt"]


        # 1. 替换 SCENE 块
        scene_block=self._build_scene_block(
            scene,
            character,
            setting
        )


        m=re.search(
            r"SCENE[\s\S]*?(?=SHOT BREAKDOWN|CAMERA|$)",
            prompt
        )

        if m:

            prompt=prompt[:m.start()] + "SCENE\n" + scene_block + prompt[m.end():]


        # 2. 对白注入 AUDIO
        if dialogue:

            d=re.search(
                r"AUDIO[\s\S]*?(?=AVOID|$)",
                prompt
            )

            if d:

                prompt=(
                    prompt[:d.end()]
                    + "\nDialogue: "
                    + dialogue
                    + prompt[d.end():]
                )


        # 3. 文字约束注入（文字准确性）
        if on_screen_text:

            prompt += "\n\nON-SCREEN TEXT (must be spelled exactly, no missing or wrong characters):\n" + on_screen_text


        # 4. 全局格式头（时长/比例/风格）
        style=template["style_hint"] or "cinematic"

        header=[

            f"Duration: {duration_s or template['duration_s']} seconds | Aspect ratio: {aspect_ratio or template['aspect_ratio']} | Style: {style}"

        ]


        return {

        "prompt":
        "\n\n".join(
            header + [prompt]
        ),

        "template_id":
        template["id"],

        "template_title":
        template["title"],

        "category":
        template["category"],

        "duration_s":
        duration_s or template["duration_s"],

        "aspect_ratio":
        aspect_ratio or template["aspect_ratio"]

        }


assembler=H3PromptAssembler()
