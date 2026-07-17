"""
AI Manga Studio V3.5 — Storyboard Engine

Converts novel text into structured shot-by-shot storyboard JSON.
Source: AI分镜脚本生成器.txt + 最新6宫格.txt

Rules extracted from prompts:
- 14 shots per 1000 words (≤3% error allowed)
- Faithful to original text — no additions or deletions
- Shot continuity between segments
- Banned word filtering
- Character name unification
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from backend.banned_words import BANNED_WORDS, contains_banned, filter_banned

logger = logging.getLogger(__name__)

# ── Constants ─────────────────────────────────────────────────
SHOTS_PER_1K_WORDS: int = 14
SHOT_DURATION_SECONDS: float = 15.0
ALLOWED_SHOT_ERROR_RATIO: float = 0.03  # ≤3%


# ── Data Models ───────────────────────────────────────────────

@dataclass
class StoryboardShot:
    """Single storyboard shot entry."""
    shot_id: str                           # e.g. "sc1"
    scene_desc: str                        # Scene description (location/time/weather)
    camera_angle: str                      # Shot type: 中景/近景/特写/大特写/全景/双人中景
    character_action: str                  # Character actions in this shot
    dialogue: str = ""                     # Character dialogue
    duration: float = 15.0                 # Duration in seconds
    emotion_hint: str = ""                 # Emotional tone hint
    continuity_note: str = ""              # Continuity note linking to prev/next shot

    def to_dict(self) -> Dict[str, Any]:
        return {
            "shot_id": self.shot_id,
            "scene_desc": self.scene_desc,
            "camera_angle": self.camera_angle,
            "character_action": self.character_action,
            "dialogue": self.dialogue,
            "duration": self.duration,
            "emotion_hint": self.emotion_hint,
            "continuity_note": self.continuity_note,
        }


@dataclass
class StoryboardResult:
    """Complete storyboard with all shots and metadata."""
    shots: List[StoryboardShot] = field(default_factory=list)
    total_shots: int = 0
    total_duration: float = 0.0       # seconds
    character_map: Dict[str, str] = field(default_factory=dict)  # alias → canonical name
    warnings: List[str] = field(default_factory=list)
    filtered_words: List[str] = field(default_factory=list)

    def to_json(self) -> str:
        return json.dumps({
            "shots": [s.to_dict() for s in self.shots],
            "total_shots": self.total_shots,
            "total_duration": self.total_duration,
            "character_map": self.character_map,
            "warnings": self.warnings,
            "filtered_words": self.filtered_words,
        }, ensure_ascii=False, indent=2)


# ── Engine ────────────────────────────────────────────────────

class StoryboardEngine:
    """Novel-to-storyboard conversion engine.

    Input: novel_text, character_info, scene_info, item_info
    Output: structured StoryboardResult with shot-by-shot JSON

    Designed to work with an LLM backend — this class encapsulates
    the prompt construction, parsing, and validation logic.
    """

    # Shot types allowed by the original prompt
    ALLOWED_SHOT_TYPES: tuple = (
        "中景",
        "近景",
        "特写",
        "大特写",
        "全景",
        "双人中景",
        "俯视镜头",
        "仰视镜头",
        "OTS镜头",
    )

    def __init__(self) -> None:
        logger.info("StoryboardEngine initialized (V3.5)")

    # ── Public API ────────────────────────────────────────

    def build_prompt(
        self,
        novel_text: str,
        character_info: Dict[str, str],
        scene_info: Dict[str, str],
        item_info: Dict[str, str],
        context: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Build the LLM prompt for storyboard generation.

        Returns a complete prompt string that can be sent to any LLM.
        """
        word_count = len(novel_text.replace("\n", "").replace(" ", ""))
        target_shots = max(1, round(word_count / 1000 * SHOTS_PER_1K_WORDS))

        # Build character reference section
        char_lines = "\n".join(
            f"- {name}: {desc}" for name, desc in character_info.items()
        ) if character_info else "- (none)"

        scene_lines = "\n".join(
            f"- {name}: {desc}" for name, desc in scene_info.items()
        ) if scene_info else "- (none)"

        item_lines = "\n".join(
            f"- {name}: {desc}" for name, desc in item_info.items()
        ) if item_info else "- (none)"

        context_section = ""
        if context:
            prev = context.get("previous_shot", "")
            next_shot = context.get("next_shot", "")
            if prev:
                context_section += f"\n**前一个分镜：**\n{prev}\n"
            if next_shot:
                context_section += f"\n**后一个分镜：**\n{next_shot}\n"

        banned_list = "\n".join(sorted(BANNED_WORDS))

        prompt = f"""## 核心任务
你是一个专业的AI分镜脚本生成器。基于提供的文本信息，生成分镜脚本。

## 输入信息
**故事情节：**
{novel_text}

**角色信息库：**
{char_lines}

**场景信息库：**
{scene_lines}

**物品信息库：**
{item_lines}
{context_section}
## 生成规则 (必须严格遵守)
1. **忠实原文**：不添加原文没有的内容，不减少信息。
2. **分镜数量**：目标 {target_shots} 个分镜（每千字 {SHOTS_PER_1K_WORDS} 个，误差不超过 {ALLOWED_SHOT_ERROR_RATIO*100:.0f}%）。
3. **连续性**：参考前后分镜信息，确保起始状态与前一镜无缝衔接。
4. **动作归属**：必须根据文案准确判定动作发出的角色。
5. **禁忌**：不得描述服装，只能直接使用角色名字。
6. **视觉风格**：参考顶级动漫高燃视觉。加入速度线、冲击波、环境碎裂、流光溢彩、高对比度阴影等动漫化特效描写。
7. **角色名称强制统一**：自动识别并统一角色的不同称呼，必须全名输出。
8. **每分镜15秒**：按情节发展合理分镜。

## 违禁词列表（不得出现）：
{banned_list}

## 输出格式
JSON数组格式，每个分镜对象包含：shot_id, scene_desc, camera_angle, character_action, dialogue, duration, emotion_hint, continuity_note"""

        return prompt

    def validate_output(self, output_text: str) -> StoryboardResult:
        """Parse and validate LLM output into structured storyboard.

        Args:
            output_text: Raw LLM response text.

        Returns:
            Validated StoryboardResult.
        """
        result = StoryboardResult()
        shots_data: List[Dict[str, Any]] = []

        # Try to parse JSON
        try:
            # Find JSON block in output
            text = output_text.strip()
            if "```" in text:
                # Extract code block
                import re
                match = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
                if match:
                    text = match.group(1).strip()
                else:
                    # Try to find JSON array
                    start = text.find("[")
                    end = text.rfind("]")
                    if start != -1 and end != -1:
                        text = text[start:end + 1]

            parsed = json.loads(text)
            if isinstance(parsed, list):
                shots_data = parsed
            elif isinstance(parsed, dict) and "shots" in parsed:
                shots_data = parsed["shots"]

        except (json.JSONDecodeError, ValueError) as e:
            logger.warning(f"StoryboardEngine: JSON parse failed, attempting line-by-line: {e}")
            # Fallback: parse line by line
            shots_data = self._parse_legacy_format(output_text)

        # Build StoryboardShot objects
        for i, shot_data in enumerate(shots_data):
            shot_id = shot_data.get("shot_id", f"sc{i+1}")

            # Filter banned words from all text fields
            for key in ("scene_desc", "character_action", "dialogue", "emotion_hint"):
                if key in shot_data and contains_banned(str(shot_data[key])):
                    found = [w for w in BANNED_WORDS if w in str(shot_data[key])]
                    result.filtered_words.extend(found)
                    shot_data[key] = filter_banned(str(shot_data[key]))
                    result.warnings.append(f"Shot {shot_id}: filtered banned words: {found}")

            shot = StoryboardShot(
                shot_id=shot_id,
                scene_desc=shot_data.get("scene_desc", ""),
                camera_angle=shot_data.get("camera_angle", "中景"),
                character_action=shot_data.get("character_action", ""),
                dialogue=shot_data.get("dialogue", ""),
                duration=float(shot_data.get("duration", 15.0)),
                emotion_hint=shot_data.get("emotion_hint", ""),
                continuity_note=shot_data.get("continuity_note", ""),
            )
            result.shots.append(shot)

        result.total_shots = len(result.shots)
        result.total_duration = sum(s.duration for s in result.shots)

        logger.info(
            f"StoryboardEngine: generated {result.total_shots} shots, "
            f"total duration {result.total_duration:.1f}s, "
            f"{len(result.filtered_words)} banned words filtered"
        )

        return result

    def build_character_map(self, novel_text: str) -> Dict[str, str]:
        """Build alias → canonical name map from novel text.

        This is a heuristic extraction — the LLM handles the full mapping
        during storyboard generation.
        """
        # Basic heuristic: extract names and common aliases
        # In production, this is handled by the LLM during generation
        return {}

    # ── Internal ──────────────────────────────────────────

    def _parse_legacy_format(self, text: str) -> List[Dict[str, Any]]:
        """Fallback parser for legacy storyboard format."""
        shots: List[Dict[str, Any]] = []
        lines = text.strip().split("\n")
        current_shot: Dict[str, Any] = {}

        for line in lines:
            line = line.strip()
            if not line:
                continue

            # Detect shot ID lines (e.g., "sc1:" or "分镜1：")
            import re
            shot_match = re.match(r"(?:sc|分镜|shot)\s*(\d+)[：:]", line, re.IGNORECASE)
            if shot_match:
                if current_shot:
                    shots.append(current_shot)
                current_shot = {"shot_id": f"sc{shot_match.group(1)}"}
                continue

            if "shot_id" not in current_shot:
                current_shot["shot_id"] = f"sc{len(shots)+1}"

            # Parse key-value pairs
            kv_match = re.match(r"(场景|镜头|描述|对话|动作|情绪|continuity)[：:]\s*(.*)", line)
            if kv_match:
                key_map = {
                    "场景": "scene_desc",
                    "镜头": "camera_angle",
                    "描述": "character_action",
                    "对话": "dialogue",
                    "动作": "character_action",
                    "情绪": "emotion_hint",
                    "continuity": "continuity_note",
                }
                key = key_map.get(kv_match.group(1), kv_match.group(1))
                current_shot[key] = kv_match.group(2).strip()

        if current_shot:
            shots.append(current_shot)

        return shots
