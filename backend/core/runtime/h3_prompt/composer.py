"""H3 提示词组装器（GPT 设计）

模板 + 场景 → 12s 三分段分镜 + H3 Workflow Request
"""
import re


class H3PromptComposer:
    """
    输出：
    {
      "workflow": "h3/reference",
      "prompt": "...",          # 逐秒分镜完整提示词
      "camera": {...},
      "lighting": {...},
      "audio": {"voice_reference": ...},
      "constraints": [...]
    }
    """


    def _segments(
        self,
        duration_s
    ):


        if duration_s <= 4:

            return [
                (0, duration_s)
            ]


        seg=4

        segs=[]

        start=0

        while start < duration_s:

            end=min(
                start + seg,
                duration_s
            )

            segs.append(
                (start, end)
            )

            start=end


        return segs


    def _build_scene_block(
        self,
        scene,
        character=None,
        setting=None,
        emotion=None
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

        if emotion:

            parts.append(
                "Emotion: " + emotion
            )

        parts.append(
            "Scene: " + scene
        )


        return "\n".join(
            parts
        )


    def compose(
        self,
        template,
        scene,
        character=None,
        setting=None,
        emotion=None,
        dialogue=None,
        voice_reference=None,
        on_screen_text=None,
        duration_s=None,
        aspect_ratio=None
    ):


        duration_s=duration_s or template.get(
            "duration_s",
            15
        )

        aspect_ratio=aspect_ratio or template.get(
            "aspect_ratio",
            "16:9"
        )


        base=template["prompt"]


        scene_block=self._build_scene_block(
            scene,
            character,
            setting,
            emotion
        )


        # 替换 SCENE 块
        m=re.search(
            r"SCENE[\s\S]*?(?=SHOT BREAKDOWN|CAMERA|$)",
            base
        )

        if m:

            base=(
                base[:m.start()]
                + "SCENE\n"
                + scene_block
                + base[m.end():]
            )


        # 对白注入
        if dialogue:

            d=re.search(
                r"AUDIO[\s\S]*?(?=AVOID|$)",
                base
            )

            if d:

                base=(
                    base[:d.end()]
                    + "\nDialogue: "
                    + dialogue
                    + base[d.end():]
                )


        # 文字约束
        if on_screen_text:

            base += "\n\nON-SCREEN TEXT (must be spelled exactly):\n" + on_screen_text


        # 12s 三分段分镜
        segs=self._segments(
            duration_s
        )

        timeline="\n".join(

            [
                f"{s}-{e}s — {scene[:120]}"
                + (f" | {dialogue[:80]}" if dialogue else "")
                for s, e in segs
            ]

        )


        header=(
            f"Duration: {duration_s} seconds | Aspect ratio: {aspect_ratio} | Style: {template.get('style_hint') or 'cinematic'}"
        )


        prompt=(
            header
            + "\n\n"
            + base
            + "\n\nSHOT TIMELINE\n"
            + timeline
        )


        workflow=(
            "h3/reference"
            if template.get(
                "workflow"
            ) == "reference"
            else "h3/standard"
        )


        constraints=template.get(
            "constraints",
            {}
        )


        result={

        "workflow":
        workflow,

        "prompt":
        prompt,

        "template_id":
        template["id"],

        "template_title":
        template["title"],

        "category":
        template["category"],

        "camera":
        {

            "type":
            constraints.get(
                "camera",
                []
            )[0]
            if constraints.get(
                "camera"
            )
            else "dynamic",

            "duration":
            duration_s

        },

        "lighting":
        {

            "style":
            constraints.get(
                "lighting",
                []
            )[0]
            if constraints.get(
                "lighting"
            )
            else "cinematic"

        },

        "audio":
        {

            "voice_reference":
            voice_reference

        },

        "constraints":
        constraints.get(
            "forbidden",
            []
        ) + [

            "keep face identity",

            "no watermark"

        ]

        }


        return result
