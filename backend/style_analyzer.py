"""
AI Manga Studio Pro — 小说风格自动分析模块

功能：
  1. 小说风格分析 — 读取文本关键词，判断类型，映射到推荐视觉风格
  2. 人物风格分析 — 根据角色属性推荐视觉呈现参数
  3. 一键初始化 DNA — 自动分析小说 → 设置 StyleDNA → 注册 CharacterDNA → 注入参考图

用法：
  from backend.dna_system import DNAManager
  from backend.style_analyzer import StyleAnalyzer

  analyzer = StyleAnalyzer()
  dna_mgr = DNAManager(project_dir="projects/my_manga")

  # 一键初始化
  result = analyzer.analyze_and_init_dna("novel.txt", dna_mgr)
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from loguru import logger

from backend.dna_system import CharacterDNA, DNAManager, StyleDNA


# ============================================================
# Genre → Visual Style Mapping
# ============================================================

# Each genre keyword maps to a recommended visual style and confidence modifier
GENRE_STYLE_MAP: Dict[str, Tuple[str, float]] = {
    # 修仙 / 战神 / 神豪 / 重生 → 国漫风
    "修仙": ("国漫", 0.85),
    "修真": ("国漫", 0.85),
    "仙侠": ("国漫", 0.85),
    "战神": ("国漫", 0.80),
    "神豪": ("国漫", 0.75),
    "重生": ("国漫", 0.75),
    "炼丹": ("国漫", 0.70),
    "渡劫": ("国漫", 0.70),
    "凡间": ("国漫", 0.60),
    "修炼": ("国漫", 0.65),
    "宗门": ("国漫", 0.70),
    "修仙者": ("国漫", 0.80),
    "灵气": ("国漫", 0.70),

    # 校园 / 恋爱 / 冒险 / 魔法 / 热血 → 日漫风
    "校园": ("日漫", 0.85),
    "恋爱": ("日漫", 0.80),
    "冒险": ("日漫", 0.75),
    "魔法": ("日漫", 0.80),
    "热血": ("日漫", 0.85),
    "学园": ("日漫", 0.80),
    "高中": ("日漫", 0.65),
    "转校": ("日漫", 0.70),
    "羁绊": ("日漫", 0.70),
    "异世界": ("日漫", 0.80),
    "勇者": ("日漫", 0.75),
    "魔王": ("日漫", 0.75),

    # 总裁 / 豪门 / 都市 → 韩漫风
    "总裁": ("韩漫", 0.90),
    "豪门": ("韩漫", 0.85),
    "都市": ("韩漫", 0.80),
    "财阀": ("韩漫", 0.80),
    "秘书": ("韩漫", 0.65),
    "商战": ("韩漫", 0.70),
    "职场": ("韩漫", 0.65),
    "CEO": ("韩漫", 0.75),
    "霸道": ("韩漫", 0.70),

    # 科幻 / 战争 / 悬疑 / 犯罪 → 电影写实风
    "科幻": ("电影写实", 0.90),
    "战争": ("电影写实", 0.85),
    "悬疑": ("电影写实", 0.85),
    "犯罪": ("电影写实", 0.80),
    "末日": ("电影写实", 0.80),
    "丧尸": ("电影写实", 0.80),
    "星际": ("电影写实", 0.85),
    "特工": ("电影写实", 0.75),
    "推理": ("电影写实", 0.70),
    "警匪": ("电影写实", 0.80),
    "黑帮": ("电影写实", 0.75),

    # 儿童 / 童话 / 治愈 → 迪士尼动画风
    "儿童": ("迪士尼动画", 0.85),
    "童话": ("迪士尼动画", 0.90),
    "治愈": ("迪士尼动画", 0.75),
    "王子": ("迪士尼动画", 0.70),
    "公主": ("迪士尼动画", 0.80),
    "城堡": ("迪士尼动画", 0.70),

    # 神话 / RPG / 西幻 → 游戏CG风
    "神话": ("游戏CG", 0.85),
    "RPG": ("游戏CG", 0.80),
    "西幻": ("游戏CG", 0.85),
    "龙": ("游戏CG", 0.65),
    "骑士": ("游戏CG", 0.75),
    "精灵": ("游戏CG", 0.80),
    "矮人": ("游戏CG", 0.70),
    "地下城": ("游戏CG", 0.80),
    "游戏": ("游戏CG", 0.65),

    # 搞笑 / 解说 / → Q版漫画
    "搞笑": ("Q版漫画", 0.85),
    "解说": ("Q版漫画", 0.75),
    "吐槽": ("Q版漫画", 0.75),
    "沙雕": ("Q版漫画", 0.80),
    "日常": ("Q版漫画", 0.65),
    "四格": ("Q版漫画", 0.80),

    # 儿童 / 家庭 → Pixar 风格
    "家庭": ("Pixar", 0.80),
    "成长": ("Pixar", 0.70),
    "亲情": ("Pixar", 0.75),
    "家庭剧": ("Pixar", 0.80),
    "温馨": ("Pixar", 0.70),

    # 赘婿 → 国漫风
    "赘婿": ("国漫", 0.80),
    "废柴": ("国漫", 0.65),
    "逆袭": ("国漫", 0.60),
}


# ============================================================
# Gender → Visual Defaults
# ============================================================

GENDER_DEFAULTS: Dict[str, Dict[str, Any]] = {
    "male": {
        "hair_style": "short",
        "body_type": "athletic",
        "skin_tone": "fair",
    },
    "female": {
        "hair_style": "long",
        "body_type": "slim",
        "skin_tone": "fair",
    },
}

# Role → Appearance hints
ROLE_STYLE_HINTS: Dict[str, Dict[str, str]] = {
    "protagonist": {
        "hair_style": "distinctive",   # 主角发型通常有辨识度
        "hair_color": "black",
        "eye_color": "black",
    },
    "antagonist": {
        "hair_color": "dark",
        "eye_color": "sharp",
        "distinctive_features": "cold expression, sharp gaze",
    },
    "supporting": {
        "hair_style": "simple",
        "body_type": "average",
    },
}

# Identity → Clothing suggestions
IDENTITY_OUTFIT_MAP: Dict[str, str] = {
    "修仙": "白色长袍, 束发, 玉佩",
    "战神": "黑色战甲, 披风, 长剑",
    "总裁": "深色西装, 领带, 腕表",
    "学生": "校服, 书包, 运动鞋",
    "魔法师": "法师长袍, 魔杖, 斗篷",
    "武者": "练功服, 绑带, 拳套",
    "医生": "白大褂, 听诊器, 口罩",
    "警察": "警服, 警帽, 配枪",
    "杀手": "黑色紧身衣, 面罩, 匕首",
}


# ============================================================
# StyleAnalyzer
# ============================================================

@dataclass
class StyleAnalysisResult:
    """Result of novel style analysis."""
    detected_genres: Dict[str, float] = field(default_factory=dict)
    recommended_style: str = ""
    confidence: float = 0.0
    style_breakdown: Dict[str, float] = field(default_factory=dict)


@dataclass
class CharacterStyleResult:
    """Result of character style analysis."""
    name: str = ""
    gender: str = "unknown"
    hair_color: str = "black"
    hair_style: str = "long"
    eye_color: str = "black"
    skin_tone: str = "fair"
    body_type: str = "slim"
    height: str = "175cm"
    distinctive_features: str = ""
    default_outfit: str = ""
    expressions: Dict[str, str] = field(default_factory=dict)


class StyleAnalyzer:
    """Analyze novel text and character profiles to recommend
    visual styles and character appearance parameters."""

    # Characters to read for analysis (at least 5000)
    READ_CHARS: int = 5000

    # ----------------------------------------------------------
    # 1. Novel Style Analysis
    # ----------------------------------------------------------

    def analyze_novel_style(
        self,
        novel_path: str,
        read_chars: int = 0,
    ) -> StyleAnalysisResult:
        """Read novel text and determine the recommended visual style.

        Args:
            novel_path: Path to the novel .txt file.
            read_chars: Characters to read (0 = use default 5000).

        Returns:
            StyleAnalysisResult with detected genres and style recommendation.
        """
        chars = read_chars if read_chars > 0 else self.READ_CHARS
        text = self._load_novel_text(novel_path, chars)
        logger.info(
            f"StyleAnalyzer: Analyzing novel style from {len(text)} characters"
        )

        # Count keyword occurrences in text
        genre_scores: Dict[str, float] = {}
        for keyword, (style, confidence) in GENRE_STYLE_MAP.items():
            count = text.count(keyword)
            if count > 0:
                # Score = count * base confidence (normalized later)
                genre_scores[keyword] = count * confidence

        if not genre_scores:
            logger.warning("StyleAnalyzer: No genre keywords detected in text")
            return StyleAnalysisResult(
                detected_genres={},
                recommended_style="国漫",
                confidence=0.3,
            )

        # Aggregate by visual style
        style_scores: Dict[str, float] = {}
        for keyword, score in genre_scores.items():
            style_name, _ = GENRE_STYLE_MAP[keyword]
            style_scores[style_name] = style_scores.get(style_name, 0.0) + score

        # Pick top style
        best_style = max(style_scores, key=style_scores.get)
        total = sum(style_scores.values())
        confidence = style_scores[best_style] / total if total > 0 else 0.0

        # Round to 3 decimals
        confidence = round(min(confidence, 0.99), 3)

        logger.info(
            f"StyleAnalyzer: Recommended style='{best_style}' "
            f"confidence={confidence}, style_breakdown={style_scores}"
        )

        return StyleAnalysisResult(
            detected_genres=genre_scores,
            recommended_style=best_style,
            confidence=confidence,
            style_breakdown=style_scores,
        )

    # ----------------------------------------------------------
    # 2. Character Style Analysis
    # ----------------------------------------------------------

    def analyze_character_style(
        self,
        name: str,
        gender: str = "unknown",
        role: str = "",
        traits: Optional[List[str]] = None,
        identity_hints: Optional[List[str]] = None,
    ) -> CharacterStyleResult:
        """Analyze a character's attributes and recommend visual parameters.

        Args:
            name: Character name.
            gender: "male" / "female" / "unknown".
            role: "protagonist" / "antagonist" / "supporting".
            traits: Personality traits (e.g. ["冷静", "热血"]).
            identity_hints: Identity keywords from text (e.g. ["修仙", "门派"]).

        Returns:
            CharacterStyleResult with recommended visual parameters.
        """
        result = CharacterStyleResult(name=name, gender=gender)
        traits = traits or []
        identity_hints = identity_hints or []

        # Apply gender defaults
        if gender in GENDER_DEFAULTS:
            defaults = GENDER_DEFAULTS[gender]
            result.hair_style = defaults.get("hair_style", result.hair_style)
            result.body_type = defaults.get("body_type", result.body_type)
            result.skin_tone = defaults.get("skin_tone", result.skin_tone)

        # Apply role hints
        if role in ROLE_STYLE_HINTS:
            hints = ROLE_STYLE_HINTS[role]
            for field, value in hints.items():
                if hasattr(result, field) and value:
                    setattr(result, field, value)

        # Trait → visual hints
        trait_visual_map: Dict[str, Dict[str, str]] = {
            "冷酷": {"eye_color": "ice blue", "hair_color": "silver"},
            "热血": {"eye_color": "red", "hair_style": "spiky"},
            "温柔": {"eye_color": "warm brown", "hair_style": "soft"},
            "神秘": {"eye_color": "purple", "hair_color": "dark"},
            "活泼": {"eye_color": "bright green", "hair_style": "twin tails"},
            "沉稳": {"eye_color": "deep brown", "hair_style": "neat"},
            "高傲": {"eye_color": "gold", "hair_color": "blonde"},
            "天真": {"eye_color": "clear blue", "skin_tone": "fair"},
            "邪恶": {"eye_color": "crimson", "distinctive_features": "sinister smile"},
        }

        for trait in traits:
            if trait in trait_visual_map:
                hints = trait_visual_map[trait]
                for field, value in hints.items():
                    if hasattr(result, field) and not getattr(result, field):
                        setattr(result, field, value)
                    elif hasattr(result, field) and getattr(result, field) == GENDER_DEFAULTS.get(gender, {}).get(field, ""):
                        # Override default with trait-specific value
                        setattr(result, field, value)

        # Identity → outfit
        for hint in identity_hints:
            if hint in IDENTITY_OUTFIT_MAP:
                result.default_outfit = IDENTITY_OUTFIT_MAP[hint]
                break

        # Expression library (universal)
        result.expressions = {
            "neutral": "平静 直视",
            "happy": "微笑 弯眼",
            "angry": "皱眉 瞪眼",
            "sad": "垂眼 泪光",
            "surprised": "睁眼 张嘴",
            "serious": "眯眼 抿嘴",
        }

        # Height estimation
        if gender == "male":
            result.height = "180cm"
        elif gender == "female":
            result.height = "165cm"

        logger.info(
            f"StyleAnalyzer: Character '{name}' → "
            f"hair={result.hair_color} {result.hair_style}, "
            f"eyes={result.eye_color}, outfit='{result.default_outfit}'"
        )

        return result

    # ----------------------------------------------------------
    # 3. One-Click DNA Initialization
    # ----------------------------------------------------------

    def analyze_and_init_dna(
        self,
        novel_path: str,
        dna_manager: DNAManager,
        reference_images_dir: str = "",
        characters: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """Full pipeline: analyze novel → set StyleDNA → register characters → inject references.

        Args:
            novel_path: Path to the novel .txt file.
            dna_manager: An initialized DNAManager instance.
            reference_images_dir: Root directory with style reference image subdirectories.
            characters: Optional pre-extracted character profiles from AIDirector.
                        Each dict should contain: name, gender, role, traits, identity_hints.

        Returns:
            Summary dict with all analysis results.
        """
        logger.info("StyleAnalyzer: Starting one-click DNA initialization")

        # Step 1: Analyze novel style
        style_result = self.analyze_novel_style(novel_path)
        dna_manager.set_style(art_style=style_result.recommended_style)

        # Step 2: Inject reference images
        refs_imported: Dict[str, List[str]] = {}
        if reference_images_dir and Path(reference_images_dir).exists():
            refs_imported = dna_manager.import_style_references(reference_images_dir)

        # Step 3: Register characters
        characters_registered: List[str] = []
        if characters:
            for char_data in characters:
                char_name = char_data.get("name", "")
                if not char_name:
                    continue

                char_result = self.analyze_character_style(
                    name=char_name,
                    gender=char_data.get("gender", "unknown"),
                    role=char_data.get("role", ""),
                    traits=char_data.get("traits", []),
                    identity_hints=char_data.get("identity_hints", []),
                )

                # Build CharacterDNA kwargs from analysis result
                dna_kwargs: Dict[str, Any] = {
                    "name": char_result.name,
                    "gender": char_result.gender,
                    "hair_color": char_result.hair_color,
                    "hair_style": char_result.hair_style,
                    "eye_color": char_result.eye_color,
                    "skin_tone": char_result.skin_tone,
                    "body_type": char_result.body_type,
                    "height": char_result.height,
                    "distinctive_features": char_result.distinctive_features,
                    "default_outfit": char_result.default_outfit,
                    "expressions": char_result.expressions,
                }
                # Merge any extra fields from char_data
                for extra_key in ("seed", "lora_name", "lora_weight",
                                  "ipadapter_style", "ipadapter_weight",
                                  "voice_id", "voice_pitch", "voice_speed",
                                  "face_embedding_path"):
                    if extra_key in char_data:
                        dna_kwargs[extra_key] = char_data[extra_key]

                dna_manager.set_character(**dna_kwargs)
                characters_registered.append(char_name)

                logger.info(
                    f"StyleAnalyzer: Registered character '{char_name}' "
                    f"→ {dna_manager.get_character(char_name).dna_fingerprint()}"
                )

        # Save all DNA
        dna_manager.save_all()

        summary = {
            "novel_style": style_result.recommended_style,
            "style_confidence": style_result.confidence,
            "style_breakdown": style_result.style_breakdown,
            "styles_with_references": list(refs_imported.keys()),
            "total_reference_images": sum(len(v) for v in refs_imported.values()),
            "characters_registered": characters_registered,
            "total_characters": len(characters_registered),
        }

        logger.info(f"StyleAnalyzer: DNA initialization complete → {summary}")
        return summary

    # ----------------------------------------------------------
    # Helpers
    # ----------------------------------------------------------

    @staticmethod
    def _load_novel_text(path: str, max_chars: int) -> str:
        """Load the first max_chars characters of a novel file."""
        try:
            with open(path, "r", encoding="utf-8") as f:
                return f.read(max_chars)
        except (FileNotFoundError, UnicodeDecodeError) as e:
            logger.error(f"StyleAnalyzer: Failed to read novel: {e}")
            return ""

    def extract_character_profiles_from_director(
        self,
        director_result,
    ) -> List[Dict[str, Any]]:
        """Convert AIDirector's CharacterProfile list into the format
        expected by analyze_and_init_dna.

        Args:
            director_result: An AIDirector instance (after load_novel + parse).

        Returns:
            List of dicts with keys: name, gender, role, traits, identity_hints.
        """
        profiles: List[Dict[str, Any]] = []
        for char in director_result.characters:
            profile = {
                "name": char.name,
                "gender": char.gender,
                "role": char.role,
                "traits": char.traits,
                "identity_hints": char.appearance_hints,
            }
            profiles.append(profile)
        return profiles
