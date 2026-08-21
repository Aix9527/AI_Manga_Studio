"""World Analyzer Agent (Phase 13.2, GPT spec).

Consumes novel text and produces a World Bible (era / technology /
civilization / power_system / physics_rules / visual_style / color_language)
which is persisted through the World data layer (13.1).
"""

from __future__ import annotations

import re
from typing import Optional

from backend.world.service import WorldService

ERA_PATTERNS = [
    (r"未来|星域|机甲|星际|赛博|科幻|AI", "未来科幻"),
    (r"现代|都市|校园|职场|都市", "现代都市"),
    (r"古代|王朝|江湖|仙侠|修真|武侠|古风", "东方古风"),
    (r"末日|废土|丧尸|灾变|荒原", "末世废土"),
]

TECH_PATTERNS = [
    (r"机甲|战舰|人工智能|义体|量子", "高端科技"),
    (r"法宝|灵气|阵法|丹药|神通", "修炼体系"),
    (r"异能|觉醒|超能力|基因", "异能科技"),
    (r"蒸汽|机械|齿轮", "蒸汽工业"),
]

POWER_PATTERNS = [
    (r"量子|能量|异能|灵力|真气|血脉|封印|系统", "特殊力量体系"),
    (r"内力|武技|剑法|功法", "武道体系"),
    (r"科技|武器|机甲|战舰", "科技武力"),
]

STYLE_PATTERNS = [
    (r"赛博|霓虹|废土|机甲", "赛博朋克"),
    (r"仙侠|修真|古风|水墨", "东方奇幻"),
    (r"暗黑|血腥|恐怖", "暗黑风格"),
    (r"唯美|治愈|清新", "治愈清新"),
]

COLOR_PATTERNS = [
    (r"霓虹|冷色|蓝色|银灰", "冷蓝+霓虹"),
    (r"暖色|金色|黄昏|橘红", "暖金"),
    (r"水墨|素白|青灰", "水墨素雅"),
    (r"血红|暗红|黑金", "暗红黑金"),
]


def _match(text: str, patterns: list[tuple[str, str]], default: str = "") -> str:
    for pattern, label in patterns:
        if re.search(pattern, text):
            return label
    return default


class WorldAnalyzerAgent:
    def __init__(self, world_service: WorldService | None = None):
        self.world = world_service or WorldService()

    def analyze(self, project_id: str, novel_text: str, name: str = "") -> dict:
        """Extract world fields and persist a World Bible (v1 data layer)."""
        era = _match(novel_text, ERA_PATTERNS, default="未知纪元")
        technology = _match(novel_text, TECH_PATTERNS, default="待定")
        power_system = _match(novel_text, POWER_PATTERNS, default="待定")
        style = _match(novel_text, STYLE_PATTERNS, default="写实")
        color = _match(novel_text, COLOR_PATTERNS, default="中性")
        physics_rules = []
        if re.search(r"时间回溯|穿越|重生", novel_text):
            physics_rules.append("禁止时间回溯（叙事规则）")
        if re.search(r"禁|封印|限制", novel_text):
            physics_rules.append("力量体系存在封印限制")
        world = self.world.create_world(
            project_id,
            name=name or "世界观",
            era=era,
            technology=technology,
            power_system=power_system,
            visual_style=style,
            color_language=color,
            physics_rules=physics_rules,
        )
        self.world.note_environment(
            project_id, kind="world_analysis",
            content=f"era={era}; power={power_system}; style={style}",
            source="world_analyzer",
        )
        return world.to_dict()
