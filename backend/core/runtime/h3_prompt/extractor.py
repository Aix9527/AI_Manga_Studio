"""场景特征提取器（GPT 设计）

小说场景文本 → {action, emotion, environment, camera, tone}
"""
import re


# 动作词
ACTION_WORDS=[

    "抓住",
    "推",
    "打",
    "追",
    "冲",
    "奔跑",
    "爆炸",
    "觉醒",
    "拔出",
    "挥",
    "砸",
    "翻",
    "踢",
    "逃",
    "拥抱",
    "点头",
    "摇头",
    "转身",
    "跪下",
    "举起",
    "放下"

]

# 对白词
DIALOGUE_WORDS=[

    "说道",
    "说",
    "问",
    "回答",
    "低声",
    "低语",
    "怒吼",
    "喊",
    "质问",
    "回答",
    "道歉",
    "承诺",
    "警告",
    "台词",
    "对话"

]

# 情绪词
EMOTION_MAP={

    "冷静": "calm",
    "愤怒": "anger",
    "恐惧": "fear",
    "害怕": "fear",
    "紧张": "tension",
    "压力": "pressure",
    "压迫": "pressure",
    "悲伤": "sadness",
    "哭": "sadness",
    "泪": "sadness",
    "喜悦": "joy",
    "笑": "joy",
    "神秘": "mystery",
    "怀疑": "doubt",
    "决意": "determination",
    "坚定": "determination",
    "绝望": "despair",
    "希望": "hope",
    "惊讶": "surprise",
    "震惊": "shock"

}

# 环境词
ENVIRONMENT_MAP={

    "实验室": "laboratory",
    "仓库": "warehouse",
    "夜晚": "night",
    "夜": "night",
    "雨": "rain",
    "雾": "fog",
    "废墟": "ruins",
    "森林": "forest",
    "沙漠": "desert",
    "街道": "street",
    "城市": "city",
    "屋顶": "rooftop",
    "车站": "station",
    "地铁": "subway",
    "天台": "rooftop",
    "医院": "hospital",
    "学校": "school",
    "家": "home",
    "房间": "room",
    "大厅": "hall",
    "博物馆": "museum",
    "赌场": "casino",
    "地下室": "basement",
    "地下": "underground",
    "黎明": "dawn",
    "黄昏": "dusk",
    "雪": "snow",
    "海": "sea",
    "天空": "sky",
    "太空": "space"

}

# 镜头词
CAMERA_MAP={

    "特写": "close_up",
    "近景": "close_up",
    "远景": "wide",
    "全景": "wide",
    "中景": "medium",
    "俯视": "high_angle",
    "仰视": "low_angle",
    "跟拍": "tracking",
    "慢镜头": "slow_motion",
    "推": "push_in",
    "拉": "pull_out",
    "摇": "pan",
    "一镜到底": "one_take",
    "过肩": "over_shoulder",
    "手持": "handheld",
    "视角": "pov"

}


class SceneFeatureExtractor:
    """
    场景文本 → 结构化特征
    """


    def extract(
        self,
        scene_text
    ):


        text=scene_text


        action=[]

        for w in ACTION_WORDS:

            if w in text:

                action.append(
                    w
                )


        for w in DIALOGUE_WORDS:

            if w in text:

                action.append(
                    "dialogue"
                )

                break


        action=list(
            dict.fromkeys(
                action
            )
        )


        emotion=[]

        for kw, val in EMOTION_MAP.items():

            if kw in text:

                emotion.append(
                    val
                )


        emotion=list(
            dict.fromkeys(
                emotion
            )
        )


        environment=[]

        for kw, val in ENVIRONMENT_MAP.items():

            if kw in text:

                environment.append(
                    val
                )


        environment=list(
            dict.fromkeys(
                environment
            )
        )


        camera=[]

        for kw, val in CAMERA_MAP.items():

            if kw in text:

                camera.append(
                    val
                )


        camera=list(
            dict.fromkeys(
                camera
            )
        )


        # tone 推断（优先级：风格信号 > 动作 > 对白 > 商业 > 暗黑电影 > 默认电影）
        tone="cinematic"

        STRONG_ACTION_TONE=[

            "打斗",
            "战斗",
            "追逐",
            "狂奔",
            "爆炸",
            "撞击",
            "对抗",
            "变身",
            "特效",
            "转场",
            "觉醒",
            "符文",
            "碎片",
            "标题",
            "爆发"

        ]

        if "二次元" in text or "动画" in text or "anime" in text.lower() or "纸片人" in text:

            tone="anime"

        elif any(
            kw in text
            for kw in STRONG_ACTION_TONE
        ):

            tone="vfx"

        elif any(
            kw in text
            for kw in DIALOGUE_WORDS
        ):

            tone="dialogue"

        elif "广告" in text or "产品" in text:

            tone="commercial"

        elif environment and any(
            e in ("night", "underground", "ruins", "basement")
            for e in environment
        ):

            tone="dark_cinematic"


        return {

        "action":
        action,

        "emotion":
        emotion,

        "environment":
        environment,

        "camera":
        camera,

        "tone":
        tone

        }
