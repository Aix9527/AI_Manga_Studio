"""
AI Manga Studio V3.5 — Shared Banned Words Registry

All engines reference this single source of truth for content filtering.
Extracted from the original prompt templates for consistent enforcement.
"""

from __future__ import annotations

from typing import FrozenSet

# ── BANNED_WORDS frozen set ───────────────────────────────────
# DO NOT modify this list without updating all engines' test suites.

BANNED_WORDS: FrozenSet[str] = frozenset({
    # Blood-related
    "血液飞溅",
    "喷血",
    "鲜血淋漓",
    "血池",
    "血祭",
    "断头血",
    "内脏出血",
    "血腥场面",
    "血债",
    "血洗",
    "血肉模糊",

    # Violence
    "分尸",
    "碎尸",
    "斩首",
    "砍头",
    "挖眼",
    "掏心",
    "剥皮",
    "凌迟",
    "虐杀",
    "酷刑",
    "断肢",
    "爆头",
    "穿刺",
    "撕咬",
    "骨裂",
    "脑浆",
    "内脏外露",
    "残肢断臂",

    # Mass violence
    "屠杀",
    "灭门",
    "焚尸",
    "鞭尸",
    "尸横遍野",

    # Nudity / vulgar
    "全裸",
    "半裸",
    "袒胸露背",
    "露脐",
    "露臀",
    "露私密部位",
    "一丝不挂",
    "裸体",
    "赤裸",
    "性感暴露",
    "挑逗性裸露",
    "低俗姿势",
    "暴露隐私部位",
    "酥胸半露",
    "衣不蔽体",

    # Pornography / sexual
    "色情",
    "淫秽",
    "嫖娼",
    "卖淫",
    "性交易",
    "一夜情",
    "通奸",
    "乱伦",
    "恋童",
    "兽交",
    "约炮",
    "撩骚",
    "打炮",
    "床上戏",
    "胸器",
    "美腿诱惑",
    "性感撩拨",
    "暧昧低俗",
    "艳舞",
    "脱衣舞",
    "乳房",
    "阴部",
    "阴茎",
    "臀部",
    "色情暗示",
    "艳情",
    "低俗互动",
    "性挑逗",
    "裸露祭祀",

    # Superstition / horror
    "血腥祭祀",
    "活人献祭",
    "血咒",
    "尸变",
    "僵尸吸血",
    "食人恶鬼",

    # Public order / morality
    "自残",
    "自杀",
    "暴力教唆",
    "聚众斗殴",
    "黑帮火拼",
    "恐怖袭击",
    "校园暴力",

    # Sensitive politics / religion
    "邪教仪式",
    "极端宗教",
    "分裂",
    "恐怖组织",
    "反动",
    "颠",
})


def contains_banned(text: str) -> bool:
    """Check if any banned word appears in the text."""
    return any(word in text for word in BANNED_WORDS)


def list_banned_found(text: str) -> list[str]:
    """Return list of banned words found in the text."""
    return [word for word in BANNED_WORDS if word in text]


def filter_banned(text: str, replacement: str = "***") -> str:
    """Replace all banned words with a placeholder."""
    result = text
    for word in BANNED_WORDS:
        if word in result:
            result = result.replace(word, replacement)
    return result
