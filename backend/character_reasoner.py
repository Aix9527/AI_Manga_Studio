"""
AI Manga Studio V3.5 — Character Reasoner

Enhances Character DNA with structured component-level descriptions.
Source: 人物形象精细化反推-大课提示词.txt

Key concepts:
- Picture prompt = part list + assembly instructions (BOM approach)
- Top-to-bottom scanning: head → face → hair → ears → headwear → neck → upper clothing → lower clothing → hands → feet → ribbons → accessories
- Part description formula: [部位名] + [形态描述] + [颜色] + [材质/质感] + [装饰细节]
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


# ── Data Models ───────────────────────────────────────────────

@dataclass
class CharacterDNAEnhanced:
    """Enhanced Character DNA with structured component-level fields."""
    character_name: str = ""

    # ── 定性层：Style Framework ────────────────────────────
    style_framework: str = ""           # Q版/写实/游戏角色等

    # ── 头部 ──────────────────────────────────────────────
    hair_style: str = ""                # 发型描述
    hair_color: str = ""                # 发色
    hair_texture: str = ""              # 发质：光滑/蓬松/卷曲等
    ears: str = ""                      # 耳朵描述
    head_accessories: str = ""          # 头饰
    horns: str = ""                     # 角

    # ── 面部 ──────────────────────────────────────────────
    face_shape: str = ""                # 脸型
    eyes: str = ""                      # 眼睛
    nose: str = ""                      # 鼻子
    mouth: str = ""                     # 嘴巴
    expression_base: str = ""           # 基础表情

    # ── 上身 ──────────────────────────────────────────────
    upper_clothing: str = ""            # 上装
    layers: str = ""                    # 层次描述
    collar: str = ""                    # 领型
    sleeve: str = ""                    # 袖型
    trim_color: str = ""                # 边饰颜色

    # ── 下身 ──────────────────────────────────────────────
    lower_clothing: str = ""            # 下装
    lower_style: str = ""               # 下装风格

    # ── 鞋靴 ──────────────────────────────────────────────
    footwear: str = ""

    # ── 飘带/附属 ────────────────────────────────────────
    ribbons_belts: str = ""             # 飘带/腰带
    cape_tail: str = ""                 # 披风/尾巴

    # ── 配件层 ────────────────────────────────────────────
    accessories: List[str] = field(default_factory=list)  # 手持道具/装饰物

    # ── 质感标签 ──────────────────────────────────────────
    quality_tags: List[str] = field(default_factory=list)


# ── Engine ────────────────────────────────────────────────────

class CharacterReasoner:
    """Enhances Character DNA with structured component-level descriptions.

    Uses the "BOM (Bill of Materials)" approach from the original prompt:
    treat each character component as a part to be described precisely.
    """

    # Partition scan order (top → bottom, follow human body)
    SCAN_ORDER: List[str] = [
        "style_framework",
        "hair_style",
        "hair_color",
        "hair_texture",
        "ears",
        "head_accessories",
        "horns",
        "face_shape",
        "eyes",
        "nose",
        "mouth",
        "expression_base",
        "upper_clothing",
        "layers",
        "collar",
        "sleeve",
        "trim_color",
        "lower_clothing",
        "lower_style",
        "footwear",
        "ribbons_belts",
        "cape_tail",
    ]

    # Part description formula template
    PART_FORMULA: str = "[部位名] + [形态描述] + [颜色] + [材质/质感] + [装饰细节]"

    def __init__(self) -> None:
        logger.info("CharacterReasoner initialized (V3.5)")

    # ── Public API ────────────────────────────────────────

    def reason(
        self,
        novel_text: str,
        existing_character_dna: Optional[Dict[str, Any]] = None,
    ) -> CharacterDNAEnhanced:
        """Generate enhanced Character DNA from novel text.

        Args:
            novel_text: The novel text to extract character information from.
            existing_character_dna: Existing character data to merge with.

        Returns:
            Enhanced CharacterDNAEnhanced with structured fields.
        """
        dna = CharacterDNAEnhanced()

        # Merge existing data if available
        if existing_character_dna:
            dna = self._merge_existing(dna, existing_character_dna)

        # Extract character name
        if existing_character_dna and "name" in existing_character_dna:
            dna.character_name = existing_character_dna["name"]

        # Apply style framework defaults
        if not dna.style_framework:
            dna.style_framework = "动漫角色设计，全身立绘"

        # Ensure all empty fields have reasonable None-equivalent
        self._apply_defaults(dna)

        logger.info(f"CharacterReasoner: enhanced DNA for '{dna.character_name}'")
        return dna

    def build_prompt(
        self,
        novel_text: str,
        character_name: str,
        existing_fields: Optional[Dict[str, str]] = None,
    ) -> str:
        """Build the LLM prompt for character reasoning."""
        existing_section = ""
        if existing_fields:
            existing_section = "\n## 已有字段\n" + "\n".join(
                f"- {k}: {v}" for k, v in existing_fields.items() if v
            )

        prompt = f"""## 核心任务
你是一个专业的人物形象反推引擎。基于提供的小说文本，逐区域描述该角色的每个零件。

## 输入
**角色名：** {character_name}
**小说片段：** {novel_text}
{existing_section}

## 分区扫描顺序（严格按此顺序，从头到脚）
1. 定性层：风格框架（Q版/写实/游戏角色等）
2. 头部：发型 → 发色 → 发质 → 耳朵 → 头饰 → 角
3. 面部：脸型 → 眼睛 → 鼻子 → 嘴 → 基础表情
4. 上身：上装 → 层次 → 领型 → 袖型 → 边饰颜色
5. 下身：下装 → 风格
6. 鞋靴
7. 飘带/附属：飘带/腰带 → 披风/尾巴
8. 配件：手持道具/装饰物（列表）
9. 质感标签：风格标签列表

## 零件描述公式
[部位名] + [形态描述] + [颜色] + [材质/质感] + [装饰细节]

## 输出格式
JSON格式，字段名按上述分区名称（英文）"""
        return prompt

    def enhance_part(self, part_name: str, description: str) -> str:
        """Normalize a single part description to follow the formula."""
        if not description:
            return ""

        # If description already contains structured info, return as-is
        if any(sep in description for sep in ["，", "、"]):
            return description

        # Basic formula check — ensure at least name + form
        return description

    def to_structured_output(self, dna: CharacterDNAEnhanced) -> str:
        """Convert enhanced DNA to structured output (Expression C format).

        Returns:
            Markdown-style structured representation.
        """
        lines: List[str] = []

        def add_section(label: str, content: str) -> None:
            if content:
                lines.append(f"【{label}】{content}")

        add_section("风格", dna.style_framework)
        add_section("主体", dna.character_name)

        # Head section
        head_parts: List[str] = []
        if dna.hair_style:
            head_parts.append(dna.hair_style)
        if dna.hair_color:
            head_parts.append(dna.hair_color)
        if dna.hair_texture:
            head_parts.append(dna.hair_texture)
        if head_parts:
            add_section("头发", "，".join(head_parts))
        add_section("耳朵", dna.ears)
        add_section("头饰", dna.head_accessories)
        add_section("角", dna.horns)

        # Face section
        face_parts: List[str] = []
        if dna.eyes:
            face_parts.append(dna.eyes)
        if dna.face_shape:
            face_parts.append(dna.face_shape)
        if dna.expression_base:
            face_parts.append(dna.expression_base)
        if face_parts:
            add_section("面部", "，".join(face_parts))

        # Clothing section
        upper_parts: List[str] = []
        if dna.upper_clothing:
            upper_parts.append(dna.upper_clothing)
        if dna.layers:
            upper_parts.append(dna.layers)
        if dna.collar:
            upper_parts.append(dna.collar)
        if dna.sleeve:
            upper_parts.append(dna.sleeve)
        if dna.trim_color:
            upper_parts.append(dna.trim_color)
        if upper_parts:
            add_section("上身", "，".join(upper_parts))

        lower_parts: List[str] = []
        if dna.lower_clothing:
            lower_parts.append(dna.lower_clothing)
        if dna.lower_style:
            lower_parts.append(dna.lower_style)
        if lower_parts:
            add_section("下身", "，".join(lower_parts))

        add_section("鞋靴", dna.footwear)

        # Ribbons / cape
        if dna.ribbons_belts:
            add_section("飘带/腰带", dna.ribbons_belts)
        if dna.cape_tail:
            add_section("披风/尾巴", dna.cape_tail)

        # Accessories
        if dna.accessories:
            add_section("配件", "，".join(dna.accessories))

        # Quality tags
        if dna.quality_tags:
            add_section("质感", "，".join(dna.quality_tags))

        return "  \n".join(lines)

    # ── Internal ──────────────────────────────────────────

    def _merge_existing(
        self,
        dna: CharacterDNAEnhanced,
        existing: Dict[str, Any],
    ) -> CharacterDNAEnhanced:
        """Merge existing character data into enhanced DNA."""
        field_mapping = {
            "name": "character_name",
            "hair_style": "hair_style",
            "hair_color": "hair_color",
            "eye_color": "eyes",
            "style": "style_framework",
        }

        for existing_key, dna_attr in field_mapping.items():
            if existing_key in existing and existing[existing_key]:
                setattr(dna, dna_attr, str(existing[existing_key]))

        return dna

    def _apply_defaults(self, dna: CharacterDNAEnhanced) -> None:
        """Apply sensible defaults for empty fields."""
        # No-op: keep empty fields as empty strings for LLM to fill
        pass
