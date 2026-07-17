"""
AI Manga Studio Pro V4 — Visual Effects Layer

Generates VFX descriptions for each shot based on:
- Emotion/intensity → dynamic effects (速度线/冲击波/环境碎裂/流光溢彩)
- Action type → specific VFX (剑灵气劲/法术光效/爆炸碎片)
- Environment → ambient effects (雨滴/雪花/尘埃/雾气)
- Camera movement → motion effects (运动模糊/动态拖影/速度线)

These VFX descriptions are injected into:
1. Image prompts (for static visual effects)
2. Video prompts (for animated effects)
3. Shot table (for production reference)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set

from loguru import logger


# ============================================================
# Constants
# ============================================================

# Core dynamic effects from reference materials
CORE_DYNAMIC_EFFECTS = [
    "速度线",       # Speed lines
    "冲击波",       # Impact wave
    "环境碎裂",     # Environmental fracture
    "流光溢彩",     # Flowing light and color
    "高对比度阴影",  # High contrast shadows
]

# Emotion → VFX mapping
EMOTION_VFX: Dict[str, List[str]] = {
    "angry": ["速度线从角色周围放射", "高对比度阴影", "冲击波扭曲"],
    "sad": ["柔和体积光", "雨滴粒子叠加", "去饱和色调"],
    "happy": ["暖金色调", "闪光粒子", "柔光泛光"],
    "fearful": ["冷蓝色轮廓光", "浅景深模糊", "暗角加深"],
    "surprised": ["闪光白叠加", "径向速度线", "瞬间焦点切换"],
    "tense": ["明暗对照法", "荷兰角张力", "脉冲式呼吸运动"],
    "determined": ["锐利轮廓光", "稳定镜头推进", "干净构图"],
    "excited": ["动态镜头环绕", "暖色分级", "快速微运动"],
    "calm": ["柔和散射光", "慢速摇镜头", "最小主体运动"],
}

# Action type → VFX mapping
ACTION_VFX: Dict[str, List[str]] = {
    "attack": ["剑气轨迹", "武器光效拖尾", "冲击波扩散"],
    "defend": ["能量护盾光效", "防御粒子屏障"],
    "cast_spell": ["法术光环", "能量汇聚特效", "符文光芒"],
    "fight": ["连续冲击波", "碰撞火花", "速度线交错"],
    "run": ["运动模糊", "身后速度线", "尘土粒子"],
    "jump": ["滞空光效", "重力拖影", "落地冲击波"],
    "fly": ["气流轨迹", "高度光晕", "云散效果"],
    "teleport": ["空间扭曲", "残影消散", "瞬移光效"],
}

# Weather → ambient VFX
WEATHER_VFX: Dict[str, List[str]] = {
    "rain": ["雨滴下落轨迹", "地面水花溅射", "水面涟漪", "湿滑反光"],
    "snow": ["雪花飘落", "地面积雪", "呼出白气", "雪花堆积"],
    "wind": ["风吹发丝", "衣物飘动", "树叶摇曳", "沙尘粒子"],
    "fog": ["雾气流动", "能见度降低", "背光雾化", "层次渐变"],
    "storm": ["闪电照亮", "狂风暴雨", "树木剧烈摇晃", "乌云翻滚"],
    "clear": ["无特殊环境效果"],
}

# Camera movement → motion VFX
CAMERA_VFX: Dict[str, List[str]] = {
    "dolly_in": ["背景透视变化", "运动模糊", "焦点切换"],
    "pan": ["水平运动拖影", "背景视差"],
    "tracking": ["跟随运动模糊", "背景视差移动"],
    "handheld": ["手持抖动效果", "不规则运动模糊"],
    "whip_pan": ["高速运动模糊", "方向性拖影"],
    "static": ["无运动效果"],
}


# ============================================================
# Data Models
# ============================================================

@dataclass
class ShotVFX:
    """Visual effects configuration for a single shot."""
    shot_id: str = ""
    
    # Dynamic effects (anime-style)
    dynamic_effects: List[str] = field(default_factory=list)
    
    # Action-specific VFX
    action_vfx: List[str] = field(default_factory=list)
    
    # Ambient/environmental VFX
    ambient_vfx: List[str] = field(default_factory=list)
    
    # Camera motion VFX
    camera_vfx: List[str] = field(default_factory=list)
    
    # Combined description (for prompts)
    combined_description: str = ""
    
    # English version
    combined_english: str = ""


# ============================================================
# VFX Generator
# ============================================================

class VFXGenerator:
    """Generates visual effects for each shot based on context."""

    def __init__(self):
        logger.info("VFXGenerator initialized (V4)")

    def generate(self, shot_data: Dict[str, Any]) -> ShotVFX:
        """Generate VFX for a single shot.
        
        Args:
            shot_data: Dict with keys: emotion, action, weather,
                      camera_movement, shot_type, vfx_override
        
        Returns:
            ShotVFX with categorized effects.
        """
        vfx = ShotVFX(shot_id=shot_data.get("shot_id", ""))
        
        # 1. Emotion-based dynamic effects
        emotion = shot_data.get("emotion", "neutral").lower()
        vfx.dynamic_effects = EMOTION_VFX.get(emotion, [])
        
        # 2. Action-based VFX
        actions = shot_data.get("actions", [shot_data.get("action", "")])
        for action in actions:
            action_lower = action.lower()
            for key, effects in ACTION_VFX.items():
                if key in action_lower:
                    vfx.action_vfx.extend(effects)
                    break
        
        # 3. Weather/ambient VFX
        weather = shot_data.get("weather", "clear").lower()
        vfx.ambient_vfx = WEATHER_VFX.get(weather, WEATHER_VFX["clear"])
        
        # 4. Camera motion VFX
        cam_move = shot_data.get("camera_movement", "").lower()
        for key, effects in CAMERA_VFX.items():
            if key in cam_move:
                vfx.camera_vfx.extend(effects)
                break
        
        # 5. Remove duplicates while preserving order
        vfx.dynamic_effects = self._dedup(vfx.dynamic_effects)
        vfx.action_vfx = self._dedup(vfx.action_vfx)
        vfx.ambient_vfx = self._dedup(vfx.ambient_vfx)
        vfx.camera_vfx = self._dedup(vfx.camera_vfx)
        
        # 6. Combine into single description
        all_effects = (
            vfx.dynamic_effects + vfx.action_vfx + 
            vfx.ambient_vfx + vfx.camera_vfx
        )
        vfx.combined_description = "；".join(all_effects) if all_effects else "无特殊特效"
        
        # 7. English version
        vfx.combined_english = self._to_english(vfx)
        
        return vfx

    def generate_batch(self, shots: List[Dict[str, Any]]) -> List[ShotVFX]:
        """Generate VFX for a batch of shots."""
        return [self.generate(shot) for shot in shots]

    def _dedup(self, items: List[str]) -> List[str]:
        """Remove duplicates while preserving order."""
        seen: Set[str] = set()
        result = []
        for item in items:
            if item not in seen:
                seen.add(item)
                result.append(item)
        return result

    def _to_english(self, vfx: ShotVFX) -> str:
        """Convert VFX description to English."""
        all_effects = (
            vfx.dynamic_effects + vfx.action_vfx +
            vfx.ambient_vfx + vfx.camera_vfx
        )
        if not all_effects:
            return "no special effects"
        
        # Simple keyword translation
        translations = {
            "速度线": "speed lines",
            "冲击波": "impact waves",
            "环境碎裂": "environmental fracture",
            "流光溢彩": "flowing light and color",
            "高对比度阴影": "high contrast shadows",
            "剑气轨迹": "sword qi trail",
            "法术光环": "spell aura",
            "雨滴下落": "falling raindrops",
            "雪花飘落": "falling snowflakes",
            "风吹发丝": "wind-blown hair",
            "雾气流动": "flowing fog",
            "运动模糊": "motion blur",
            "手持抖动": "handheld shake",
            "背景视差": "parallax background",
        }
        
        translated = []
        for effect in all_effects:
            en = translations.get(effect, effect)
            translated.append(en)
        
        return "; ".join(translated)
