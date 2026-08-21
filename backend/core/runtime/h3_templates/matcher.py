"""小说场景 → H3 模板匹配引擎"""
import re

from .registry import (
    H3PromptTemplateRegistry
)


# 场景类型 → 模板类别 规则（关键词命中计分）
CATEGORY_RULES={

    "dialogue_sound":[

        "对白",
        "说",
        "道",
        "问",
        "答",
        "对话",
        "质问",
        "怒吼",
        "低声",
        "耳语",
        "电话",
        "台词"

    ],

    "character_performance":[

        "角色",
        "特写",
        "表情",
        "表演",
        "舞",
        "走秀",
        "自拍",
        "偶像",
        "演唱会",
        "眼神"

    ],

    "animation_anime":[

        "二次元",
        "动画",
        "动漫",
        "赛璐璐",
        "q版",
        "chibi",
        "anime",
        "漫画",
        "卡通",
        "纸片"

    ],

    "cinematic":[

        "电影",
        "悬念",
        "悬疑",
        "情绪",
        "离别",
        "车站",
        "回忆",
        "史诗",
        "雨夜",
        "黎明",
        "黄昏",
        "伤感",
        "克制"

    ],

    "vfx_transitions":[

        "转场",
        "特效",
        "快切",
        "变形",
        "换装",
        "裂解",
        "分割",
        "蒙太奇",
        "循环",
        "无缝",
        "打斗",
        "战斗",
        "追逐",
        "爆炸",
        "撞击",
        "挥舞"

    ],

    "product_ads":[

        "广告",
        "产品",
        "口红",
        "香水",
        "美妆",
        "美食",
        "评测",
        "开箱",
        "护肤",
        "时装",
        "唇膏"

    ],

    "editing":[

        "vlog",
        "记录",
        "手持",
        "dv",
        "日常",
        "实拍",
        "自拍杆"

    ],

    "camera_motion":[

        "运镜",
        "镜头运动",
        "跟拍",
        "推拉",
        "摇移",
        "航拍",
        "一镜到底"

    ],

    "animal":[

        "动物",
        "宠物",
        "猫",
        "狗",
        "鸟"

    ]

}


class H3TemplateMatcher:
    """
    小说场景文本 → 最匹配模板

    流程：
    1. 提取场景特征（对白/动作/风格关键词）
    2. 场景类型 → 候选类别计分
    3. 类别内选 style_hint 最匹配模板
    """


    def __init__(self, registry=None):

        self.registry=registry or H3PromptTemplateRegistry()


    def detect_category(
        self,
        scene_text
    ):


        scores={}

        text=scene_text.lower()


        # 强动作词直接优先 vfx_transitions（避免与角色类平局）
        STRONG_ACTION=[
            "打斗",
            "战斗",
            "追逐",
            "爆炸",
            "撞击",
            "打斗",
            "高速",
            "激烈"
        ]

        if any(
            kw in text
            for kw in STRONG_ACTION
        ):

            scores["vfx_transitions"]=scores.get(
                "vfx_transitions",
                0
            ) + 3


        for cat, kws in CATEGORY_RULES.items():

            score=sum(

                1 for kw in kws

                if kw.lower() in text

            )

            if score:

                scores[cat]=scores.get(
                    cat,
                    0
                ) + score


        if not scores:

            return "cinematic"


        return max(
            scores,
            key=scores.get
        )


    def match(
        self,
        scene_text,
        category=None,
        style_hint=None
    ):


        cat=category or self.detect_category(
            scene_text
        )


        candidates=self.registry.list_templates(
            cat
        )


        if not candidates:

            candidates=self.registry.entries


        # style_hint 加权
        hint=(
            style_hint or ""
        ).lower()

        if hint:

            scored=[]

            for t in candidates:

                score=0.0

                s_hint=t["style_hint"].lower()

                if hint in s_hint:

                    score+=2.0

                for kw in hint.split():

                    if kw in s_hint:

                        score+=0.5

                scored.append(
                    (score, t)
                )

            best=max(
                scored,
                key=lambda x: x[0]
            )

            if best[0] > 0:

                return {

                "template":
                best[1],

                "category":
                cat,

                "score":
                round(
                    best[0],
                    2
                )

                }


        return {

        "template":
        candidates[0],

        "category":
        cat,

        "score":
        1.0

        }


matcher=H3TemplateMatcher()
