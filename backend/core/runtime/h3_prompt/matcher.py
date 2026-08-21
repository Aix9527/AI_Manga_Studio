"""H3 模板加权匹配器（GPT 设计）

TemplateScore =
  0.35 category_match
+ 0.25 tag_match
+ 0.20 emotion_match
+ 0.10 camera_match
+ 0.10 aspect_match
"""
import json

import os

from .schema import (
    H3PromptTemplate
)

from .extractor import (
    SceneFeatureExtractor
)


PROMPTS_DIR=os.path.join(
    "backend",
    "production",
    "h3_prompts"
)

LIBRARY=os.path.join(
    PROMPTS_DIR,
    "library.json"
)

INDEX_FILE=os.path.join(
    PROMPTS_DIR,
    "templates_index.json"
)


# 场景 tone → 模板类别
TONE_CATEGORY={

    "anime":
    "animation_anime",

    "dialogue":
    "dialogue_sound",

    "commercial":
    "product_ads",

    "dark_cinematic":
    "cinematic",

    "cinematic":
    "cinematic",

    "vfx":
    "vfx_transitions",

    "performance":
    "character_performance",

    "camera":
    "camera_motion"

}

# 动作 → 类别
ACTION_CATEGORY={

    "dialogue":
    "dialogue_sound",

    "dance":
    "character_performance",

    "run":
    "vfx_transitions",

    "fight":
    "vfx_transitions",

    "transform":
    "vfx_transitions"

}


class H3PromptMatcher:
    """
    特征向量 → 加权模板匹配
    """


    def __init__(self, extractor=None):

        self.extractor=extractor or SceneFeatureExtractor()

        self._load()


    def _load(self):


        self.library=json.load(
            open(
                LIBRARY,
                encoding="utf-8"
            )
        )


        self.entries=self.library.get(
            "entries",
            []
        )


        self.index=json.load(
            open(
                INDEX_FILE,
                encoding="utf-8"
            )
        ) if os.path.exists(
            INDEX_FILE
        ) else {

        "category_index":
        {},

        "tag_index":
        {}

        }


    def category_candidates(
        self,
        features
    ):


        cands=set()

        tone=TONE_CATEGORY.get(
            features["tone"]
        )

        if tone:

            cands.add(
                tone
            )


        for a in features["action"]:

            if a in ACTION_CATEGORY:

                cands.add(
                    ACTION_CATEGORY[a]
                )


        return cands


    def _score(
        self,
        template,
        features,
        aspect_ratio
    ):


        score=0.0

        meta={
            "category": 0.0,
            "tag": 0.0,
            "emotion": 0.0,
            "camera": 0.0,
            "aspect": 0.0
        }


        # 0.35 category
        cands=self.category_candidates(
            features
        )

        if template["category"] in cands:

            meta["category"]=0.35


        # 0.25 tag
        tag_hits=set(
            template.get(
                "tags",
                []
            )
        ) & set(
            features["environment"]
            + features["emotion"]
            + features["action"]
            + [
                features["tone"]
            ]
        )

        meta["tag"]=min(
            0.25,
            0.08 * len(
                tag_hits
            )
        )


        # 0.20 emotion（style_hint 匹配情绪词 + 冲突惩罚）
        style=template.get(
            "style_hint",
            ""
        ).lower()

        emotion_hits=sum(

            1 for e in features["emotion"]

            if e in style or e in str(
                template.get(
                    "tags",
                    []
                )
            ).lower()

        )

        meta["emotion"]=min(
            0.20,
            0.10 * emotion_hits
        ) if emotion_hits else 0.0


        # 情绪冲突惩罚（如 calm 场景 vs thriller/action 模板）
        CONFLICT_STYLE=[

            "thriller",
            "action",
            "horror",
            "fight",
            "aggressive"

        ]

        CALM_EMOTIONS={

            "calm",
            "sadness",
            "hope",
            "determination"

        }

        if (
            CALM_EMOTIONS & set(
                features["emotion"]
            )
            and any(
                w in style
                for w in CONFLICT_STYLE
            )
        ):

            meta["emotion"] -= 0.20

            meta["category"] -= 0.35

            meta["category"]=max(
                0.0,
                meta["category"]
            )


        # 0.10 camera
        cam=features["camera"]

        if cam:

            cam_str=" ".join(
                cam
            )

            if "close_up" in cam_str and (
                "close" in style
                or "macro" in style
                or "特写" in str(
                    template.get(
                        "title"
                    )
                )
            ):

                meta["camera"]=0.10

            elif "tracking" in cam_str and "tracking" in style:

                meta["camera"]=0.10


        # 0.10 aspect
        if template.get(
            "aspect_ratio"
        ) == aspect_ratio:

            meta["aspect"]=0.10


        return sum(
            meta.values()
        ), meta


    def match(
        self,
        scene_text,
        aspect_ratio="16:9",
        features=None
    ):


        features=features or self.extractor.extract(
            scene_text
        )


        scored=[]

        for t in self.entries:

            s, meta=self._score(
                t,
                features,
                aspect_ratio
            )

            scored.append(
                (s, meta, t)
            )


        scored.sort(
            key=lambda x: x[0],
            reverse=True
        )


        best_s, best_meta, best_t=scored[0]


        return {

        "template":
        best_t,

        "score":
        round(
            best_s,
            2
        ),

        "score_breakdown":
        best_meta,

        "features":
        features

        }
