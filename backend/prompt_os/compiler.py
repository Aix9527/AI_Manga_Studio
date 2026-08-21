"""Prompt Compiler (Phase 13.6, GPT spec).

输入一句剧情（如"少年进入地下遗迹"）→ 输出完整八层 ShotDesign：
剧情/导演意图/摄影/构图/动作/运镜/灯光/风格 + continuity_contract +
transition + 时长 + 负面词。规则从 DNA 知识库抽取，支持手动覆盖。
"""

from __future__ import annotations

import re
import uuid
from datetime import datetime
from typing import Any

from backend.prompt_os.knowledge_base import DNAKnowledgeBase
from backend.prompt_os.model import ContinuityContract, ShotDesign

_DEFAULT_DURATION = 5.0
_MIN_DURATION = 10.0  # 用户要求单镜头 10 秒以上（默认仅当显式时长不足时提示）

# 中文剧情 → 语义要素的轻量规则词表
_SCENE_KEYWORDS = {
    "遗迹": ("scene_ruins_001", "地下遗迹", "未知、苍凉"),
    "宫殿": ("scene_palace_001", "古朝宫殿", "威压、肃穆"),
    "皇城": ("scene_palace_001", "古朝宫殿", "威压、肃穆"),
    "都市": ("scene_city_001", "赛博都市", "繁华、冷漠"),
    "城市": ("scene_city_001", "赛博都市", "繁华、冷漠"),
    "山": ("scene_mountain_001", "云海山巅", "辽阔、孤绝"),
    "山顶": ("scene_mountain_001", "云海山巅", "辽阔、孤绝"),
}

_MOTION_KEYWORDS = {
    "奔跑": ("mot_run_001", "run", "追逐/逃亡"),
    "逃": ("mot_run_001", "run", "追逐/逃亡"),
    "战斗": ("mot_fight_001", "fight", "冲突高潮"),
    "打": ("mot_fight_001", "fight", "冲突高潮"),
    "拔剑": ("mot_fight_001", "fight", "冲突高潮"),
    "回眸": ("mot_turn_001", "look_back", "情感节点"),
    "回头": ("mot_turn_001", "look_back", "情感节点"),
    "跳跃": ("mot_jump_001", "jump", "突破/逃离"),
    "跳": ("mot_jump_001", "jump", "突破/逃离"),
    "跪": ("mot_kneel_001", "kneel", "宣誓/崩溃"),
    "坐下": ("mot_sit_001", "sit", "对白/沉思"),
    "进入": ("mot_walk_001", "slow_walk", "探索/入场"),
    "走进": ("mot_walk_001", "slow_walk", "探索/入场"),
    "前行": ("mot_walk_001", "slow_walk", "探索/入场"),
}

_EMOTION_KEYWORDS = {
    "恐惧": ("fear", "压迫感", "low_key"),
    "害怕": ("fear", "压迫感", "low_key"),
    "孤独": ("isolation", "孤独", "moonlight"),
    "渺小": ("awe", "渺小", "cold_top"),
    "希望": ("hope", "希望", "golden_hour"),
    "绝望": ("despair", "绝望", "low_key"),
    "愤怒": ("anger", "愤怒", "low_key"),
    "哀伤": ("grief", "哀伤", "moonlight"),
    "悲伤": ("grief", "哀伤", "moonlight"),
    "喜悦": ("joy", "喜悦", "golden_hour"),
    "决心": ("resolve", "决心", "dawn"),
}

_DIRECTOR_INTENT_BY_EMOTION = {
    "fear": "体现未知与压迫，让观众屏息",
    "isolation": "体现孤独与疏离，拉远情感距离",
    "awe": "体现渺小与震撼，建立世界观尺度",
    "hope": "体现希望与新生，画面由暗转亮",
    "despair": "体现绝境与无力感",
    "anger": "体现愤怒与冲突张力",
    "grief": "体现哀伤与怀念",
    "joy": "体现温暖与治愈",
    "resolve": "体现决心与转折",
}

_COMPOSITION_BY_INTENT = {
    "渺小": "comp_negative_001",
    "压迫": "comp_leading_001",
    "对峙": "comp_center_001",
    "常规": "comp_thirds_001",
}

_LIGHTING_BY_ID = {
    "golden_hour": "lit_golden_001",
    "moonlight": "lit_moon_001",
    "cold_top": "lit_cold_top_001",
    "low_key": "lit_lowkey_001",
    "dawn": "lit_dawn_001",
}

_LENS_BY_SHOT = {
    "wide": "lens_24_001",
    "medium": "lens_35_001",
    "close_up": "lens_85_001",
    "extreme_close_up": "lens_135_001",
}


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


class PromptCompiler:
    """把一句剧情编译为完整八层 ShotDesign。"""

    def __init__(self, knowledge_base: DNAKnowledgeBase | None = None):
        self.kb = knowledge_base or DNAKnowledgeBase()

    # ------------------------------------------------------------------
    def compile(
        self,
        logline: str,
        *,
        shot_id: str = "",
        duration_seconds: float = _DEFAULT_DURATION,
        camera_shot: str = "",        # 覆盖：wide|medium|close_up|extreme_close_up
        lens: str = "",               # 覆盖：24mm|35mm|50mm|85mm|135mm
        movement: str = "",           # 覆盖：slow_push|dolly|orbit|handheld|crane
        lighting: str = "",           # 覆盖：golden_hour|moonlight|back_light|rim_light|low_key|cold_top
        composition: str = "",        # 覆盖：center|thirds|leading_lines|negative_space
        style: str = "",              # 覆盖：east_wuxia|neon_cyber|epic_wide|ink_fantasy|anime
        director_intent: str = "",
        continuity_from: ShotDesign | None = None,   # 上一镜 → 继承 continuity
    ) -> ShotDesign:
        text = (logline or "").strip()
        if not text:
            raise ValueError("logline 不能为空")

        scene = self._detect_scene(text)
        motion = self._detect_motion(text)
        emotion = self._detect_emotion(text)

        # 镜头默认随情绪选择：恐惧/渺小 → wide；对峙 → medium；哀伤 → close_up
        shot = camera_shot or self._shot_for_emotion(emotion[0])
        lens_id = self._lens_for(shot, lens)
        lighting_id = self._lighting_for(emotion[2], lighting)
        composition_id = self._composition_for(director_intent or emotion[1], composition)
        style_id = self._style_for(style)

        layers = {
            "story": text,
            "director_intent": director_intent or _DIRECTOR_INTENT_BY_EMOTION.get(emotion[0], "推进叙事，强化情绪"),
            "photography": {
                "shot": shot,
                "lens": self._lens_mm(lens_id),
                "angle": self._angle_for(emotion[0]),
                "camera_position": self._camera_position(emotion[0]),
            },
            "composition": self._composition_text(composition_id, shot),
            "action": {
                "motion": motion[1],
                "detail": motion[2],
                "subject": self._detect_subject(text),
            },
            "camera_movement": movement or self._movement_for(emotion[0], shot),
            "lighting": self._lighting_text(lighting_id),
            "style": self._style_text(style_id),
        }

        contract = self._continuity_contract(text, continuity_from)

        negative_words = self.kb.negative_words()[:8]
        design = ShotDesign(
            id=shot_id or f"shot_{uuid.uuid4().hex[:10]}",
            version="v1",
            layers=layers,
            continuity_contract=contract,
            transition_in=continuity_from.transition_out if continuity_from else "",
            transition_out=self._transition_out(emotion[0]),
            duration_seconds=max(duration_seconds, _DEFAULT_DURATION),
            negative_words=negative_words,
            status="draft",
            notes="由 Prompt Compiler 生成；可人工覆盖后走审批",
            created_at=_now(),
            updated_at=_now(),
        )
        return design

    def compile_sequence(self, loglines: list[str], **overrides: Any) -> list[ShotDesign]:
        """连续多镜编译：自动把上一镜 transition_out 接到下一镜 transition_in，
        并让 continuity_contract 逐镜继承（GPT 修改建议 1/3 落地）。"""
        designs: list[ShotDesign] = []
        prev: ShotDesign | None = None
        for i, line in enumerate(loglines):
            design = self.compile(line, shot_id=f"shot_seq_{i + 1:03d}", continuity_from=prev, **overrides)
            designs.append(design)
            prev = design
        return designs

    # ------------------------------------------------------------------
    def _detect_scene(self, text: str) -> dict:
        for keyword, (entry_id, name, mood) in _SCENE_KEYWORDS.items():
            if keyword in text:
                return {"id": entry_id, "name": name, "mood": mood}
        return {"id": "scene_ruins_001", "name": "地下遗迹", "mood": "未知、苍凉"}

    def _detect_motion(self, text: str) -> tuple[str, str, str]:
        for keyword, (entry_id, motion, detail) in _MOTION_KEYWORDS.items():
            if keyword in text:
                return entry_id, motion, detail
        return "mot_walk_001", "slow_walk", "探索/入场"

    def _detect_emotion(self, text: str) -> tuple[str, str, str]:
        for keyword, (emotion, intent, lighting) in _EMOTION_KEYWORDS.items():
            if keyword in text:
                return emotion, intent, lighting
        return "awe", "渺小", "cold_top"

    def _detect_subject(self, text: str) -> str:
        for token in ["少年", "少女", "女主", "男主", "主角", "反派", "老人", "女孩", "男孩"]:
            if token in text:
                return token
        return "主角"

    def _shot_for_emotion(self, emotion: str) -> str:
        if emotion in ("fear", "awe"):
            return "wide"
        if emotion in ("anger", "resolve"):
            return "medium"
        if emotion in ("grief", "isolation"):
            return "close_up"
        return "medium"

    def _lens_for(self, shot: str, override: str) -> str:
        if override:
            for lid, mm in [("lens_24_001", "24mm"), ("lens_35_001", "35mm"), ("lens_50_001", "50mm"),
                            ("lens_85_001", "85mm"), ("lens_135_001", "135mm")]:
                if mm == override:
                    return lid
        return _LENS_BY_SHOT.get(shot, "lens_35_001")

    def _lens_mm(self, lens_id: str) -> str:
        entry = self.kb.get(lens_id)
        if entry:
            self.kb.record_usage(lens_id)
            return str(entry.values.get("focal", lens_id))
        return lens_id

    def _lighting_for(self, lighting_key: str, override: str) -> str:
        if override:
            for lid, key in [("lit_golden_001", "golden_hour"), ("lit_moon_001", "moonlight"),
                             ("lit_back_001", "back_light"), ("lit_rim_001", "rim_light"),
                             ("lit_lowkey_001", "low_key"), ("lit_cold_top_001", "cold_top")]:
                if key == override:
                    return lid
        return _LIGHTING_BY_ID.get(lighting_key, "lit_lowkey_001")

    def _lighting_text(self, lighting_id: str) -> dict:
        entry = self.kb.get(lighting_id)
        if entry:
            self.kb.record_usage(lighting_id)
            return {"id": lighting_id, "name": entry.name, "effect": entry.values.get("effect", ""),
                    "detail": entry.values.get("detail", "")}
        return {"id": lighting_id, "name": lighting_id, "effect": "", "detail": ""}

    def _composition_for(self, intent: str, override: str) -> str:
        if override:
            for cid, key in [("comp_center_001", "center"), ("comp_thirds_001", "thirds"),
                             ("comp_leading_001", "leading_lines"), ("comp_negative_001", "negative_space")]:
                if key == override:
                    return cid
        for keyword, cid in _COMPOSITION_BY_INTENT.items():
            if keyword in intent:
                return cid
        return "comp_thirds_001"

    def _composition_text(self, composition_id: str, shot: str) -> dict:
        entry = self.kb.get(composition_id)
        detail = entry.values.get("detail", "") if entry else ""
        if shot == "wide":
            detail = f"{detail}，人物位于画面下方 1/3" if detail else "人物位于画面下方 1/3"
        return {"id": composition_id, "name": entry.name if entry else composition_id, "detail": detail}

    def _style_for(self, override: str) -> str:
        if override:
            for sid, key in [("sty_wuxia_001", "east_wuxia"), ("sty_cyber_001", "neon_cyber"),
                             ("sty_epic_001", "epic_wide"), ("sty_ink_001", "ink_fantasy"),
                             ("sty_anime_001", "anime")]:
                if key == override:
                    return sid
        return "sty_epic_001"

    def _style_text(self, style_id: str) -> dict:
        entry = self.kb.get(style_id)
        if entry:
            self.kb.record_usage(style_id)
            return {"id": style_id, "name": entry.name, "visual": entry.values.get("visual", ""),
                    "palette": entry.values.get("palette", "")}
        return {"id": style_id, "name": style_id, "visual": "", "palette": ""}

    def _angle_for(self, emotion: str) -> str:
        if emotion in ("awe", "fear"):
            return "low_angle"
        if emotion == "isolation":
            return "high_angle"
        return "eye_level"

    def _camera_position(self, emotion: str) -> str:
        if emotion in ("awe", "fear"):
            return "低机位，接近地面"
        if emotion == "isolation":
            return "俯拍，拉远"
        return "与被摄主体同高"

    def _movement_for(self, emotion: str, shot: str) -> str:
        if emotion in ("fear", "awe"):
            return "slow_push_in"
        if emotion == "isolation":
            return "slow_dolly_back"
        if shot == "wide":
            return "crane_down"
        return "static"

    def _transition_out(self, emotion: str) -> str:
        if emotion == "grief":
            return "slow_fade"
        if emotion == "fear":
            return "whip_pan_to_next"
        return "match_cut"

    def _continuity_contract(self, text: str, prev: ShotDesign | None) -> ContinuityContract:
        subject = self._detect_subject(text)
        character = {subject: {"state": "inherit", "costume": "inherit", "expression": "inherit", "position": "inherit"}}
        props: dict[str, dict] = {}
        space: dict[str, dict] = {}
        if prev:
            # 继承上一镜约束，保证跨镜一致（GPT 修改建议 1/3）
            contract = prev.continuity_contract
            if contract.characters:
                character = contract.characters
            if contract.props:
                props = contract.props
            if contract.space:
                space = contract.space
            constraints = ["跨镜继承：人物/道具/空间状态保持一致，仅允许剧情驱动的变化"]
        else:
            scene = self._detect_scene(text)
            space = {scene["name"]: {"time": "inherit", "weather": "inherit", "layout": "inherit"}}
            constraints = ["人物服装/表情/站位跨镜一致", "空间道具相对位置固定", "道具受损状态跨镜延续"]
        return ContinuityContract(characters=character, props=props, space=space, constraints=constraints)