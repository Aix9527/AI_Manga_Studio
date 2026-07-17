"""
AI Manga Studio V3.5 — Dialogue Optimizer

Analyzes dialogue lines and outputs 8-dim emotion vectors + TTS parameters.
Source: 配音推理(1).txt

Key rules:
- 8-dim emotion vector: [joy, anger, sad, fear, disgust, depression, surprise, calm]
- Mutual exclusion: if calm > 0.8, others must < 0.2
- Unknown characters → "旁白"
- Output format: line_no===char_name===[v1,v2,v3,v4,v5,v6,v7,v8]+++
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# ── Constants ─────────────────────────────────────────────────

EMOTION_LABELS: Tuple[str, ...] = (
    "高兴", "生气", "伤心", "害怕", "厌恶", "低落", "惊喜", "平静"
)

NARRATOR_ROLE: str = "旁白"


# ── Data Models ───────────────────────────────────────────────

@dataclass
class DialogueLine:
    """Single dialogue line with emotion and TTS parameters."""
    line_no: int = 0
    character: str = NARRATOR_ROLE
    text: str = ""

    # 8-dim emotion vector
    emotion_vector: List[float] = field(default_factory=lambda: [0.0] * 8)

    # TTS parameters
    tts_params: Dict[str, float] = field(default_factory=lambda: {
        "speed": 1.0,
        "pitch": 1.0,
        "volume": 1.0,
        "pause_before": 0.0,
        "pause_after": 0.5,
    })

    def to_formatted_string(self) -> str:
        """Format as per original specification: line_no===角色名===[向量]+++"""
        vec_str = ",".join(f"{v:.1f}" for v in self.emotion_vector)
        return f"{self.line_no}==={self.character}===[{vec_str}]+++"


# ── Engine ────────────────────────────────────────────────────

class DialogueOptimizer:
    """Analyzes script lines and generates emotion vectors + TTS parameters.

    Designed for CosyVoice integration via emotion-guided speech synthesis.
    """

    # Emotion → TTS parameter presets
    EMOTION_TTS_MAP: Dict[str, Dict[str, float]] = {
        "高兴": {"speed": 1.2, "pitch": 1.1, "volume": 1.1, "pause_before": 0.1, "pause_after": 0.3},
        "生气": {"speed": 1.3, "pitch": 1.2, "volume": 1.3, "pause_before": 0.0, "pause_after": 0.2},
        "伤心": {"speed": 0.8, "pitch": 0.9, "volume": 0.8, "pause_before": 0.3, "pause_after": 0.8},
        "害怕": {"speed": 1.1, "pitch": 0.9, "volume": 0.7, "pause_before": 0.2, "pause_after": 0.5},
        "厌恶": {"speed": 1.0, "pitch": 0.9, "volume": 0.8, "pause_before": 0.1, "pause_after": 0.4},
        "低落": {"speed": 0.7, "pitch": 0.8, "volume": 0.6, "pause_before": 0.5, "pause_after": 1.0},
        "惊喜": {"speed": 1.3, "pitch": 1.2, "volume": 1.2, "pause_before": 0.0, "pause_after": 0.3},
        "平静": {"speed": 1.0, "pitch": 1.0, "volume": 1.0, "pause_before": 0.2, "pause_after": 0.5},
    }

    def __init__(self) -> None:
        logger.info("DialogueOptimizer initialized (V3.5)")

    # ── Public API ────────────────────────────────────────

    def optimize(
        self,
        script_lines: List[str],
        character_list: List[str],
    ) -> List[DialogueLine]:
        """Optimize dialogue lines with emotion vectors and TTS parameters.

        Args:
            script_lines: List of dialogue strings.
            character_list: List of known character names.

        Returns:
            List of DialogueLine with emotion + TTS data.
        """
        results: List[DialogueLine] = []

        for i, line in enumerate(script_lines):
            dl = DialogueLine(
                line_no=i + 1,
                text=line,
            )

            # Identify character
            dl.character = self._identify_character(line, character_list)

            # Infer emotion vector
            dl.emotion_vector = self._infer_emotion(line)

            # Enforce mutual exclusion: calm > 0.8 → others < 0.2
            dl.emotion_vector = self._enforce_mutual_exclusion(dl.emotion_vector)

            # Map to TTS parameters
            dl.tts_params = self._map_to_tts_params(dl.emotion_vector)

            results.append(dl)

        logger.info(f"DialogueOptimizer: optimized {len(results)} dialogue lines")
        return results

    def format_output(self, lines: List[DialogueLine]) -> str:
        """Format all optimized lines as per the original specification."""
        header = "_::~OUTPUT_START::~_"
        footer = "_::~OUTPUT_END::~_"
        body = "\n".join(dl.to_formatted_string() for dl in lines)
        return f"{header}\n{body}\n{footer}"

    def build_prompt(
        self,
        script_lines: List[str],
        character_list: List[str],
    ) -> str:
        """Build the LLM prompt for dialogue emotion analysis."""
        char_info = "\n".join(f"- {c}" for c in character_list) if character_list else "- (none)"
        lines_text = "\n".join(script_lines)

        prompt = f"""# Role
你是一位资深的配音导演和文本情感分析专家。精准分析剧本台词。

# 情绪向量定义 (0.0 - 1.0)
1. 高兴 (Joy)
2. 生气 (Anger)
3. 伤心 (Sadness)
4. 害怕 (Fear)
5. 厌恶 (Disgust)
6. 低落 (Depression)
7. 惊喜 (Surprise)
8. 平静 (Calm)

打分原则：
- 互斥性检查：如果"平静" > 0.8，其他情绪应 < 0.2
- 允许混合情绪
- 未知角色归为"旁白"

# 角色数据
{char_info}

# 待分析台词
{lines_text}

# 输出格式
行号===角色名===[v1,v2,v3,v4,v5,v6,v7,v8]+++"""
        return prompt

    # ── Internal methods ──────────────────────────────────

    def _identify_character(self, line: str, character_list: List[str]) -> str:
        """Identify the speaking character from the dialogue line.

        Uses prefix patterns like "角色名：" or "角色名说：".
        Unknown characters default to NARRATOR_ROLE.
        """
        # Check for "角色名：" pattern
        for char in sorted(character_list, key=len, reverse=True):  # Longest first
            if line.startswith(f"{char}：") or line.startswith(f"{char}:"):
                return char
            if f"{char}说" in line[:10]:
                return char
            # Check for "角色名 -" pattern (from storyboard)
            if f"{char} -" in line[:20]:
                return char
            if f"{char}-" in line[:20]:
                return char

        return NARRATOR_ROLE

    def _infer_emotion(self, text: str) -> List[float]:
        """Heuristic emotion inference based on keyword matching.

        In production, this would use a fine-tuned emotion classifier LLM.
        """
        vector = [0.0] * 8

        # Keyword → (emotion_index, intensity_bump) mappings
        emotion_keywords = {
            "高兴": (0, ["笑", "哈哈", "开心", "喜悦", "太好了", "庆祝", "欢呼"]),
            "生气": (1, ["怒", "混蛋", "可恶", "该死", "住口", "放肆", "混蛋"]),
            "伤心": (2, ["哭", "呜呜", "难过", "悲伤", "遗憾", "后悔", "泪"]),
            "害怕": (3, ["怕", "恐怖", "不要", "救命", "救命", "逃"]),
            "厌恶": (4, ["恶心", "脏", "讨厌", "烦", "滚"]),
            "低落": (5, ["绝望", "放弃", "算了", "无所谓", "完了"]),
            "惊喜": (6, ["什么", "居然", "天啊", "难以置信", "真的吗"]),
            "平静": (7, []),
        }

        # Scan for emotion keywords
        matched = [False] * 8
        for emotion, (idx, keywords) in emotion_keywords.items():
            for kw in keywords:
                if kw in text:
                    vector[idx] += 0.3
                    matched[idx] = True

        # If nothing matched, default to calm
        if not any(matched):
            vector[7] = 0.9
        else:
            # Cap and normalize
            for i in range(8):
                vector[i] = min(1.0, vector[i])

            # Default calm level
            vector[7] = 0.1

        return vector

    def _enforce_mutual_exclusion(self, vector: List[float]) -> List[float]:
        """Enforce the rule: if calm > 0.8, all others < 0.2."""
        calm_idx = 7
        if vector[calm_idx] > 0.8:
            for i in range(len(vector)):
                if i != calm_idx:
                    vector[i] = min(vector[i], 0.2)
        return vector

    def _map_to_tts_params(self, emotion_vector: List[float]) -> Dict[str, float]:
        """Map emotion vector to TTS parameters.

        Uses the dominant emotion's preset, blended with secondary emotions.
        """
        if not emotion_vector or len(emotion_vector) < 8:
            return {
                "speed": 1.0,
                "pitch": 1.0,
                "volume": 1.0,
                "pause_before": 0.1,
                "pause_after": 0.5,
            }

        # Find dominant emotion
        max_val = max(emotion_vector)
        if max_val < 0.3:
            return dict(self.EMOTION_TTS_MAP["平静"])

        max_idx = emotion_vector.index(max_val)
        dominant_label = EMOTION_LABELS[max_idx]

        # Get base TTS params from dominant emotion
        base = self.EMOTION_TTS_MAP.get(dominant_label, self.EMOTION_TTS_MAP["平静"])

        return dict(base)
