"""AI_Manga_Studio v1.0 Phase 2：影视团队 Agents（GPT 岗位数字化）.

Writer / Actor / Camera / Motion / Art / Editor / Sound。
每个 Agent 是确定性规则引擎：输入剧情 → 输出影视参数/prompt。
"""

from __future__ import annotations

import json
from pathlib import Path

# --------------------------------------------------------------------------
# Camera 镜头语言库（GPT Phase 2 摄影参数库）
CAMERA_LIBRARY = {
    "紧张": {"camera": "handheld", "lens": "50mm", "movement": "shaky", "depth": "shallow", "lighting": "low key"},
    "史诗": {"camera": "crane shot", "lens": "anamorphic", "movement": "slow rise", "depth": "deep", "lighting": "backlight"},
    "英雄登场": {"camera": "low angle", "lens": "35mm", "movement": "slow dolly in", "depth": "medium", "lighting": "backlight"},
    "战斗": {"camera": "tracking shot", "lens": "24mm", "movement": "dynamic", "depth": "medium", "lighting": "high contrast"},
    "回忆": {"camera": "slow push", "lens": "85mm", "movement": "slow", "depth": "shallow", "lighting": "warm"},
    "对话": {"camera": "static", "lens": "50mm", "movement": "none", "depth": "medium", "lighting": "natural"},
    "默认": {"camera": "static wide", "lens": "35mm", "movement": "none", "depth": "deep", "lighting": "natural"},
}

# 动作库（GPT Motion Timeline）
MOTION_LIBRARY = {
    "战斗": ["0-1s 拔剑", "1-2s 身体旋转", "2-3s 冲刺", "3-4s 攻击", "4-5s 镜头跟随剑光"],
    "发现危险": ["0s 正常站立", "1s 停止动作", "2s 转头", "3s 瞳孔收缩", "5s 后退一步"],
    "探索": ["0-1s 缓慢迈步", "1-3s 观察环境", "3-5s 停下注视"],
    "对话": ["0-1s 开口", "1-3s 手势", "3-5s 沉默反应"],
    "默认": ["0-5s 自然连续运动"],
}

# 表演参数（GPT Actor character_state）
EXPRESSION_LIBRARY = {
    "恐惧": "subtle fear, slightly widened eyes, controlled breathing, tense facial muscles",
    "愤怒": "clenched jaw, narrowed eyes, aggressive posture, tense brows",
    "悲伤": "downcast eyes, trembling lips, heavy breathing, slumped posture",
    "坚定": "steady gaze, firm jaw, upright posture, focused expression",
    "好奇": "slightly raised brows, tilted head, forward lean, scanning eyes",
    "默认": "natural neutral expression, relaxed posture",
}

# 音效库（GPT Sound）
SOUND_LIBRARY = {
    "地下城": ["metal echo", "ancient machine", "footsteps", "wind"],
    "森林": ["wind through leaves", "birds", "footsteps on ground"],
    "宫殿": ["reverberant hall", "distant voices", "ceremonial drums"],
    "战场": ["clashing metal", "war cries", "explosions", "tension drone"],
    "默认": ["ambient room tone"],
}

# 情绪 → BGM（GPT BGM 选择）
BGM_BY_EMOTION = {
    "紧张": "低频弦乐", "悲伤": "钢琴", "高潮": "交响", "平静": "环境轻音乐", "默认": "氛围垫底",
}


class WriterAgent:
    """AI 编剧：剧情拆解 / 对白 / 镜头化。"""

    def write_episode(self, *, story: str, characters: list[str] | None = None,
                      structure: dict | None = None) -> dict:
        chars = characters or ["主角"]
        return {
            "episode": "EP001",
            "dramatic_structure": structure or {
                "opening": story,
                "conflict": "遭遇阻碍",
                "climax": "关键抉择",
                "ending": "悬念",
            },
            "scenes": [{
                "id": "SC-1",
                "characters": chars,
                "shots": [
                    {"shot": "001", "camera": "slow push in", "actor": chars[0], "action": story, "dialogue": ""},
                ],
            }],
            "dialogue_rule": "台词符合角色人格，避免直白情绪词",
        }


class ActorAgent:
    """AI 演员：情绪/表情/动作。"""

    def act(self, *, character: str, emotion: str, action: str = "") -> dict:
        expression = EXPRESSION_LIBRARY.get(emotion, EXPRESSION_LIBRARY["默认"])
        return {
            "character": character,
            "character_state": {
                "emotion": emotion,
                "body": {"posture": "slightly forward", "movement": "slow"},
            },
            "expression_prompt": expression,
            "acting_prompt": f"{character}：{action or emotion}，{expression}，连续自然表演，避免僵硬",
        }


class CameraAgent:
    """摄影指导：镜头语言库。"""

    def direct(self, *, mood: str = "默认", scene: str = "") -> dict:
        spec = CAMERA_LIBRARY.get(mood, CAMERA_LIBRARY["默认"])
        return {
            "shot_type": spec["camera"],
            "lens": spec["lens"],
            "movement": spec["movement"],
            "depth_of_field": spec["depth"],
            "lighting": spec["lighting"],
            "camera_prompt": (
                f"{spec['camera']} with {spec['lens']} lens, {spec['movement']} movement, "
                f"{spec['depth']} depth of field, {spec['lighting']} lighting"
            ),
        }


class MotionAgent:
    """动作指导：Motion Timeline。"""

    def choreograph(self, *, action_type: str = "默认", duration_seconds: int = 5) -> dict:
        timeline = MOTION_LIBRARY.get(action_type, MOTION_LIBRARY["默认"])
        return {
            "action_type": action_type,
            "duration_seconds": duration_seconds,
            "motion_timeline": timeline,
            "motion_prompt": (
                "dynamic continuous movement, real body mechanics, "
                "no sudden jumps, smooth transitions, camera tracking"
            ),
        }


class ArtAgent:
    """美术指导：统一视觉风格。"""

    def design(self, *, style: str = "cinematic realism", color: str = "bronze + cyan",
               lighting: str = "volumetric fog") -> dict:
        return {
            "style_dna": {
                "style": style,
                "color": color,
                "material": "metal stone",
                "lighting": lighting,
            },
            "style_prefix": (
                f"{style}, color palette {color}, {lighting}, consistent across all shots, "
                "no style drift"
            ),
        }


class EditorAgent:
    """剪辑师：节奏 / 转场 / 音画同步。"""

    def edit(self, *, mood: str = "剧情", shot_count: int = 12) -> dict:
        duration = 3 if mood == "动作" else 8
        return {
            "shot_duration_rule": f"{mood}镜头建议 {duration}-{duration + 2} 秒",
            "transitions": ["match cut", "fade", "camera transition"],
            "sound_sync": "音效在动作发生后 0.1 秒内",
            "edit_plan": f"共 {shot_count} 镜头，按情绪节奏组接",
        }


class SoundAgent:
    """声音导演：配音 / 音效 / BGM。"""

    def sound(self, *, scene: str = "默认", emotion: str = "默认") -> dict:
        sfx = SOUND_LIBRARY.get(scene, SOUND_LIBRARY["默认"])
        bgm = BGM_BY_EMOTION.get(emotion, BGM_BY_EMOTION["默认"])
        return {
            "sfx": sfx,
            "bgm": bgm,
            "voice": {"voice_type": "角色专属音色", "speed": "normal", "emotion": emotion},
            "sound_prompt": f"场景音效 {'、'.join(sfx)}；BGM {bgm}；角色配音情绪匹配",
        }


class CreativeTeam:
    """影视团队总入口（Phase 2 协作）。"""

    def __init__(self):
        self.writer = WriterAgent()
        self.actor = ActorAgent()
        self.camera = CameraAgent()
        self.motion = MotionAgent()
        self.art = ArtAgent()
        self.editor = EditorAgent()
        self.sound = SoundAgent()

    def produce_shot_bible(self, *, story: str, characters: list[str],
                           emotion: str, mood: str, action_type: str) -> dict:
        """协作生成 Shot Bible 2.0（GPT Phase 2 统一数据结构）。"""
        script = self.writer.write_episode(story=story, characters=characters)
        acting = self.actor.act(character=characters[0], emotion=emotion, action=story)
        camera = self.camera.direct(mood=mood)
        motion = self.motion.choreograph(action_type=action_type)
        art = self.art.design()
        sound = self.sound.sound(scene="默认", emotion=emotion)
        return {
            "id": "gx001",
            "scene": "场景",
            "characters": characters,
            "script": script,
            "acting": acting,
            "camera": camera,
            "motion": motion,
            "art": art,
            "sound": sound,
        }
