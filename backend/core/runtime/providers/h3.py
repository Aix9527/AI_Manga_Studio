import json

from pathlib import Path

from .comfyui import ComfyUIProvider



class H3Provider(
    ComfyUIProvider
):
    """
    MiniMax H3 第二视频后端

    - standard: FL2VA 文生视频 / 首帧图生 / 首尾帧约束
    - reference: REF2VA 图片 / 视频 / 音频多模态参考

    质量档位：
    - preview:    4 步 · 768x432 / 432x768
    - production: 6 步 · 1024x576 / 576x1024
    - hero:       8 步 · 1344x768 / 768x1344

    失败时由 ModelRouter 回退 wan22/dialogue。
    """


    name="h3"


    TEMPLATE_ROOT=Path(
        "backend/production/workflows/h3"
    )


    PROFILES={

        "preview":{

            "steps":4,

            "landscape":[768,432],

            "portrait":[432,768],

            "purpose":
            "构图、动作方向、Prompt 检查"

        },

        "production":{

            "steps":6,

            "landscape":[1024,576],

            "portrait":[576,1024],

            "purpose":
            "默认批量生产"

        },

        "hero":{

            "steps":8,

            "landscape":[1344,768],

            "portrait":[768,1344],

            "purpose":
            "近景、对白、表情、手部、剧情重点镜头"

        }

    }


    DEFAULTS={

        "fps":24,

        "frames":124,

        "sampler":"euler",

        "scheduler":"simple",

        "denoise":1.0,

        "lora_strength":1.0,

        "shift_video":12.0,

        "shift_audio":3.0,

        "low_vram":False,

        "seed":20260809

    }



    def _load_template(
        self,
        workflow
    ):


        path=self.TEMPLATE_ROOT / f"{workflow}.json"


        return json.loads(
            path.read_text(
                encoding="utf-8"
            )
        )



    def validate(
        self,
        request
    ):


        workflow=request.get(
            "workflow",
            "standard"
        )


        if workflow not in (
            "standard",
            "reference"
        ):

            return {

            "model":
            "minimax_h3",

            "workflow":
            workflow,

            "ready":
            False,

            "reason":
            "unknown workflow"

            }


        profile=request.get(
            "profile",
            "production"
        )


        return {

        "model":
        "minimax_h3",

        "workflow":
        workflow,

        "profile":
        profile,

        "ready":
        True,

        "fallback":
        "wan22/dialogue"

        }



    def build_prompt(
        self,
        request
    ):


        workflow=request.get(
            "workflow",
            "standard"
        )


        template=self._load_template(
            workflow
        )


        prompt=json.loads(
            json.dumps(
                template["workflow"]
            )
        )


        bindings=template["bindings"]


        profile_name=request.get(
            "profile",
            "production"
        )


        profile=self.PROFILES.get(
            profile_name,
            self.PROFILES["production"]
        )


        orientation=request.get(
            "orientation",
            "landscape"
        )


        if orientation == "portrait":

            width, height=profile["portrait"]

        else:

            width, height=profile["landscape"]


        values=dict(
            self.DEFAULTS
        )

        values.update(
            request.get(
                "params",
                {}
            )
        )


        # 顶层请求字段合并（first_frame / ref_images 等）
        for key in (
            "prompt",
            "first_frame",
            "last_frame",
            "ref_images",
            "ref_video",
            "ref_audios",
            "ref_image_size"
        ):

            if (
                key in request
                and key not in values
            ):

                values[key]=request[key]


        values["width"]=request.get(
            "width",
            width
        )

        values["height"]=request.get(
            "height",
            height
        )

        values["steps"]=request.get(
            "steps",
            profile["steps"]
        )

        values["profile"]=profile_name


        # 列表型绑定：ref_images / ref_audios（先填充加载节点，再组装引用列表）
        if workflow == "reference":

            prompt[
                "15"
            ]["inputs"]["ref_images"]=[]

            prompt[
                "15"
            ]["inputs"]["ref_videos"]=[]

            prompt[
                "15"
            ]["inputs"]["ref_video_audios"]=[]

            prompt[
                "15"
            ]["inputs"]["ref_audios"]=[]


            # ref_images → LoadImage 7-10
            images=values.get(
                "ref_images",
                []
            ) or []

            slots=bindings["ref_images"]

            active=[]

            for i, item in enumerate(images):

                if i >= len(slots):

                    break

                node_id, out=slots[i]

                prompt[node_id][
                    "inputs"
                ]["image"]=item

                active.append(
                    [node_id, int(out)]
                )

            prompt["15"]["inputs"]["ref_images"]=active

            # 未使用的 LoadImage 节点移除（避免空 image 触发目录读取）
            for i in range(
                len(images),
                len(slots)
            ):

                prompt.pop(
                    slots[i][0],
                    None
                )


            # ref_video → LoadVideo 11 + GetVideoComponents 12
            ref_video=values.get(
                "ref_video",
                ""
            )

            if ref_video:

                prompt["11"]["inputs"]["video"]=ref_video

                prompt["15"]["inputs"]["ref_videos"]=[

                    ["12", 0]

                ]

                prompt["15"]["inputs"]["ref_video_audios"]=[

                    ["12", 1]

                ]

            else:

                # 无参考视频：移除 LoadVideo / GetVideoComponents
                prompt.pop(
                    "11",
                    None
                )

                prompt.pop(
                    "12",
                    None
                )


            # ref_audios → LoadAudio 13-14
            audios=values.get(
                "ref_audios",
                []
            ) or []

            slots=bindings["ref_audios"]

            active=[]

            for i, item in enumerate(audios):

                if i >= len(slots):

                    break

                node_id, out=slots[i]

                prompt[node_id][
                    "inputs"
                ]["audio"]=item

                active.append(
                    [node_id, int(out)]
                )

            prompt["15"]["inputs"]["ref_audios"]=active

            for i in range(
                len(audios),
                len(slots)
            ):

                prompt.pop(
                    slots[i][0],
                    None
                )


        # 单值绑定
        for key, slot in bindings.items():

            if key in (
                "ref_images",
                "ref_videos",
                "ref_video_audios",
                "ref_audios",
                "ref_video"
            ):

                continue


            if key not in values:

                continue


            node, field=slot


            if field in prompt[node]["inputs"]:

                prompt[node][
                    "inputs"
                ][field]=values[key]


        # 未使用的输入：移除 LoadImage 节点与引用（避免空 image 触发目录读取）
        if workflow == "standard":

            if values.get(
                "first_frame"
            ):

                prompt["7"]["inputs"]["image"]=values[
                    "first_frame"
                ]

            else:

                prompt.pop(
                    "7",
                    None
                )

                prompt["9"]["inputs"].pop(
                    "first_frame",
                    None
                )

            if values.get(
                "last_frame"
            ):

                prompt["8"]["inputs"]["image"]=values[
                    "last_frame"
                ]

            else:

                prompt.pop(
                    "8",
                    None
                )

                prompt["9"]["inputs"].pop(
                    "last_frame",
                    None
                )


        if workflow == "reference":

            # 无参考输入时清理节点 15 列表（保留空列表）
            prompt["15"]["inputs"].setdefault(
                "ref_images",
                []
            )

            prompt["15"]["inputs"].setdefault(
                "ref_videos",
                []
            )

            prompt["15"]["inputs"].setdefault(
                "ref_video_audios",
                []
            )

            prompt["15"]["inputs"].setdefault(
                "ref_audios",
                []
            )


        # H3-13A：audio=false → 动态移除音频节点（纯视频输出）
        if request.get(
            "audio",
            True
        ) is False:

            removed: set = set()

            # 1) 删除 VAEDecodeAudio 节点
            for nid, node in list(
                prompt.items()
            ):

                if node.get(
                    "class_type"
                ) == "VAEDecodeAudio":

                    prompt.pop(
                        nid,
                        None
                    )

                    removed.add(
                        nid
                    )

            # 2) CreateVideo 移除 audio 输入
            for nid, node in prompt.items():

                if node.get(
                    "class_type"
                ) == "CreateVideo":

                    node["inputs"].pop(
                        "audio",
                        None
                    )

            # 3) audio VAE loader 保留（reference workflow 的 audio_vae 为必填输入），
            #    仅删除解码输出节点即可切断音频流

            # 4) 清理指向已删节点的悬空引用（如 audio_vae 输入）
            if removed:

                for nid, node in prompt.items():

                    if not isinstance(
                        node.get(
                            "inputs"
                        ),
                        dict
                    ):

                        continue

                    for field, value in list(
                        node["inputs"].items()
                    ):

                        if (
                            isinstance(
                                value,
                                list
                            )
                            and len(value) == 2
                            and str(
                                value[0]
                            ) in removed
                        ):

                            node["inputs"].pop(
                                field,
                                None
                            )


        return {

        "provider":
        "h3",

        "workflow":
        workflow,

        "profile":
        profile_name,

        "prompt":
        prompt

        }
