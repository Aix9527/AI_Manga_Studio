"""Prompt DNA Knowledge Base (Phase 13.6, GPT spec).

种子数据来自抖音 AI 漫剧工业体系文档（剧本/角色Bible/三视图/表情库/
场景/分镜/镜头库/风格库/Identity Lock/多角色同框/SOP）。DNA 种类：
Character / Camera / Lens / Scene / Weather / Motion / Lighting /
Composition / Style / Continuity / Negative。风格一律用视觉特征描述。
"""

from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any

from backend.prompt_os.model import DNAEntry, _now as _model_now


def _seed() -> list[DNAEntry]:
    rows: list[dict] = [
        # ------------------------------------------------ character
        {"id": "char_hero_001", "kind": "character", "name": "少年主角", "tags": ["hero", "male", "young"],
         "values": {"face": "清秀，下颌线清晰", "hair": "黑色碎发，额前微长", "eyes": "深褐，坚定",
                    "body": "少年体型，肩窄腰细", "costume": "灰蓝劲装，束袖", "accessories": "旧玉佩",
                    "voice": "清亮带沙", "gesture": "手常按剑柄", "walk": "步伐轻快但警觉",
                    "expression": "克制", "emotion": "倔强→成长"}},
        {"id": "char_female_001", "kind": "character", "name": "女主", "tags": ["female", "lead"],
         "values": {"face": "鹅蛋脸，眉眼细长", "hair": "黑长直，发尾微卷", "eyes": "琥珀色",
                    "body": "高挑", "costume": "月白长裙，外罩薄纱", "accessories": "银铃手链",
                    "voice": "温润", "gesture": "抚发尾思考", "walk": "步态从容",
                    "expression": "含蓄", "emotion": "温柔→坚韧"}},
        {"id": "char_antagonist_001", "kind": "character", "name": "反派", "tags": ["antagonist", "male"],
         "values": {"face": "棱角分明，左眉疤", "hair": "银白短发", "eyes": "灰蓝，冷",
                    "body": "高大", "costume": "玄黑大氅", "accessories": "鎏金扳指",
                    "voice": "低沉压迫", "gesture": "负手而立", "walk": "缓慢沉稳",
                    "expression": "无表情", "emotion": "野心→疯狂"}},
        # ------------------------------------------------ camera
        {"id": "cam_wide_001", "kind": "camera", "name": "全景 Wide", "tags": ["wide", "scale"],
         "values": {"shot": "wide", "use": "交代环境与人物关系", "effect": "渺小感、史诗感"}},
        {"id": "cam_medium_001", "kind": "camera", "name": "中景 Medium", "tags": ["medium"],
         "values": {"shot": "medium", "use": "动作与对白主镜头", "effect": "叙事中性"}},
        {"id": "cam_closeup_001", "kind": "camera", "name": "特写 Close-up", "tags": ["closeup", "emotion"],
         "values": {"shot": "close_up", "use": "表情与细节", "effect": "情绪放大"}},
        {"id": "cam_ecu_001", "kind": "camera", "name": "大特写 Extreme Close-up", "tags": ["ecu", "detail"],
         "values": {"shot": "extreme_close_up", "use": "眼睛/手/信物", "effect": "心理压迫"}},
        # ------------------------------------------------ lens
        {"id": "lens_24_001", "kind": "lens", "name": "24mm", "tags": ["wide_angle"],
         "values": {"focal": "24mm", "use": "超广角低机位", "effect": "空间夸张、压迫感"}},
        {"id": "lens_35_001", "kind": "lens", "name": "35mm", "tags": ["standard_wide"],
         "values": {"focal": "35mm", "use": "人文纪实感", "effect": "自然临场"}},
        {"id": "lens_50_001", "kind": "lens", "name": "50mm", "tags": ["standard"],
         "values": {"focal": "50mm", "use": "标准叙事", "effect": "接近人眼"}},
        {"id": "lens_85_001", "kind": "lens", "name": "85mm", "tags": ["portrait"],
         "values": {"focal": "85mm", "use": "人像特写", "effect": "浅景深、唯美"}},
        {"id": "lens_135_001", "kind": "lens", "name": "135mm", "tags": ["tele"],
         "values": {"focal": "135mm", "use": "压缩空间", "effect": "窥视感、隔离感"}},
        # ------------------------------------------------ scene
        {"id": "scene_ruins_001", "kind": "scene", "name": "地下遗迹", "tags": ["ruins", "underground"],
         "values": {"type": "ancient_ruins", "mood": "未知、苍凉", "props": ["石柱", "壁画", "断桥"]}},
        {"id": "scene_city_001", "kind": "scene", "name": "赛博都市", "tags": ["city", "neon"],
         "values": {"type": "cyber_city", "mood": "繁华、冷漠", "props": ["霓虹", "天桥", "雨巷"]}},
        {"id": "scene_palace_001", "kind": "scene", "name": "古朝宫殿", "tags": ["palace", "imperial"],
         "values": {"type": "imperial_palace", "mood": "威压、肃穆", "props": ["龙纹柱", "长阶", "香炉"]}},
        {"id": "scene_mountain_001", "kind": "scene", "name": "云海山巅", "tags": ["mountain", "cloud"],
         "values": {"type": "mountain_peak", "mood": "辽阔、孤绝", "props": ["孤松", "云海", "断崖"]}},
        # ------------------------------------------------ weather
        {"id": "wx_rain_001", "kind": "weather", "name": "雨 Rain", "tags": ["rain", "sad"],
         "values": {"weather": "rain", "effect": "压抑、泪点", "detail": "雨丝反光，地面倒影"}},
        {"id": "wx_snow_001", "kind": "weather", "name": "雪 Snow", "tags": ["snow", "calm"],
         "values": {"weather": "snow", "effect": "安静、宿命感", "detail": "落雪减速运动感"}},
        {"id": "wx_fog_001", "kind": "weather", "name": "雾 Fog", "tags": ["fog", "mystery"],
         "values": {"weather": "fog", "effect": "神秘、未知", "detail": "层次雾，光柱"}},
        {"id": "wx_dawn_001", "kind": "weather", "name": "晨 Dawn", "tags": ["dawn", "hope"],
         "values": {"weather": "dawn", "effect": "希望、新生", "detail": "低角度暖光"}},
        {"id": "wx_sunset_001", "kind": "weather", "name": "黄昏 Sunset", "tags": ["sunset", "nostalgia"],
         "values": {"weather": "sunset", "effect": "离别、回忆", "detail": "长影，金色轮廓"}},
        {"id": "wx_night_001", "kind": "weather", "name": "夜 Night", "tags": ["night", "tension"],
         "values": {"weather": "night", "effect": "危险、静谧", "detail": "月光与暗部对比"}},
        # ------------------------------------------------ motion
        {"id": "mot_walk_001", "kind": "motion", "name": "缓步 Walk", "tags": ["walk"],
         "values": {"motion": "slow_walk", "use": "探索/入场", "detail": "重心前倾，衣摆微动"}},
        {"id": "mot_run_001", "kind": "motion", "name": "奔跑 Run", "tags": ["run", "chase"],
         "values": {"motion": "run", "use": "追逐/逃亡", "detail": "甩臂幅度大，镜头跟移"}},
        {"id": "mot_fight_001", "kind": "motion", "name": "战斗 Fight", "tags": ["fight", "action"],
         "values": {"motion": "fight", "use": "冲突高潮", "detail": "发力瞬间停顿，残影"}},
        {"id": "mot_turn_001", "kind": "motion", "name": "回眸 Turn-back", "tags": ["turn", "look_back"],
         "values": {"motion": "look_back", "use": "情感节点", "detail": "慢速转身，发丝甩动"}},
        {"id": "mot_jump_001", "kind": "motion", "name": "跃起 Jump", "tags": ["jump", "dynamic"],
         "values": {"motion": "jump", "use": "突破/逃离", "detail": "腾空压缩帧"}},
        {"id": "mot_sit_001", "kind": "motion", "name": "落座 Sit", "tags": ["sit", "calm"],
         "values": {"motion": "sit", "use": "对白/沉思", "detail": "缓慢坐下，衣料堆叠"}},
        {"id": "mot_kneel_001", "kind": "motion", "name": "跪地 Kneel", "tags": ["kneel", "vow"],
         "values": {"motion": "kneel", "use": "宣誓/崩溃", "detail": "重心下沉，低头"}},
        # ------------------------------------------------ lighting
        {"id": "lit_golden_001", "kind": "lighting", "name": "Golden Hour", "tags": ["warm", "golden"],
         "values": {"lighting": "golden_hour", "effect": "温暖、希望", "detail": "低角度暖金逆光"}},
        {"id": "lit_moon_001", "kind": "lighting", "name": "Moonlight", "tags": ["cold", "night"],
         "values": {"lighting": "moonlight", "effect": "清冷、孤独", "detail": "冷蓝顶光，长影"}},
        {"id": "lit_back_001", "kind": "lighting", "name": "Back Light", "tags": ["rim", "silhouette"],
         "values": {"lighting": "back_light", "effect": "剪影、神秘", "detail": "轮廓光勾勒身形"}},
        {"id": "lit_rim_001", "kind": "lighting", "name": "Rim Light", "tags": ["rim", "drama"],
         "values": {"lighting": "rim_light", "effect": "戏剧化、立体", "detail": "发丝/肩线亮边"}},
        {"id": "lit_lowkey_001", "kind": "lighting", "name": "Low-key", "tags": ["noir", "tension"],
         "values": {"lighting": "low_key", "effect": "压抑、危险", "detail": "高反差，暗部为主"}},
        {"id": "lit_cold_top_001", "kind": "lighting", "name": "顶部冷光", "tags": ["cold", "alien"],
         "values": {"lighting": "cold_top", "effect": "未知、疏离", "detail": "顶光冷白，眼窝阴影"}},
        # ------------------------------------------------ composition
        {"id": "comp_center_001", "kind": "composition", "name": "中心构图", "tags": ["center", "power"],
         "values": {"composition": "center", "use": "主角出场/对峙", "detail": "主体居中，对称"}},
        {"id": "comp_thirds_001", "kind": "composition", "name": "三分法", "tags": ["thirds", "balance"],
         "values": {"composition": "thirds", "use": "常规叙事", "detail": "主体位于交叉点"}},
        {"id": "comp_leading_001", "kind": "composition", "name": "引导线", "tags": ["leading", "depth"],
         "values": {"composition": "leading_lines", "use": "纵深/行进", "detail": "道路/栏杆指向主体"}},
        {"id": "comp_negative_001", "kind": "composition", "name": "留白", "tags": ["negative_space", "lonely"],
         "values": {"composition": "negative_space", "use": "孤独/渺小", "detail": "大面积空景"}},
        # ------------------------------------------------ style
        {"id": "sty_wuxia_001", "kind": "style", "name": "东方武侠", "tags": ["wuxia", "east"],
         "values": {"style": "east_wuxia", "visual": "水墨晕染，留白写意，衣袂翻飞", "palette": "墨色+朱砂点缀"}},
        {"id": "sty_cyber_001", "kind": "style", "name": "高对比霓虹赛博", "tags": ["cyberpunk", "neon"],
         "values": {"style": "neon_cyber", "visual": "高对比霓虹赛博，雨夜反射光", "palette": "品红+青蓝"}},
        {"id": "sty_epic_001", "kind": "style", "name": "广角史诗", "tags": ["epic", "scale"],
         "values": {"style": "epic_wide", "visual": "广角史诗感，大景深，人物渺小", "palette": "晨昏冷暖对撞"}},
        {"id": "sty_ink_001", "kind": "style", "name": "水墨东方幻想", "tags": ["ink", "fantasy"],
         "values": {"style": "ink_fantasy", "visual": "水墨东方幻想，气韵流动", "palette": "灰阶+金箔"}},
        {"id": "sty_anime_001", "kind": "style", "name": "日系动画", "tags": ["anime", "clean"],
         "values": {"style": "anime", "visual": "干净线条，大色块，高饱和", "palette": "明快"}},
        # ------------------------------------------------ continuity（GPT 修改建议 3）
        {"id": "cont_state_001", "kind": "continuity", "name": "人物状态继承", "tags": ["character", "state"],
         "values": {"rule": "character_state_inherit", "fields": ["costume", "expression", "position", "hand_props"],
                    "detail": "相邻镜头人物服装/表情/站位/手中道具必须一致，只允许剧情驱动变化"}},
        {"id": "cont_space_001", "kind": "continuity", "name": "空间布局一致", "tags": ["space", "layout"],
         "values": {"rule": "space_layout_lock", "fields": ["door", "window", "furniture", "light_source"],
                    "detail": "同一场景空间道具相对位置固定，机位变化不改变布局"}},
        {"id": "cont_prop_001", "kind": "continuity", "name": "道具状态锁定", "tags": ["prop", "state"],
         "values": {"rule": "prop_state_lock", "fields": ["broken", "blood", "weather_wet"],
                    "detail": "道具受损/染色/淋湿状态跨镜延续"}},
        {"id": "cont_match_001", "kind": "continuity", "name": "动作匹配剪辑", "tags": ["match_cut", "motion"],
         "values": {"rule": "motion_match_cut", "fields": ["trajectory", "speed"],
                    "detail": "镜头衔接点运动方向与速度连续，可用 match cut / 甩镜 / 叠化"}},
        # ------------------------------------------------ negative（GPT 修改建议 4）
        {"id": "neg_face_001", "kind": "negative", "name": "面部失败模式", "tags": ["face", "artifact"],
         "values": {"failures": ["表情僵硬", "皮笑肉不笑", "五官错位", "眼睛不对称", "嘴型崩坏"]}},
        {"id": "neg_anatomy_001", "kind": "negative", "name": "形体失败模式", "tags": ["anatomy", "body"],
         "values": {"failures": ["手指畸形", "手臂穿模", "肢体错位", "比例失衡", "多余肢体"]}},
        {"id": "neg_physics_001", "kind": "negative", "name": "物理失败模式", "tags": ["physics", "motion"],
         "values": {"failures": ["漂浮", "穿墙", "重力反常", "影子错乱", "布料穿透"]}},
        {"id": "neg_quality_001", "kind": "negative", "name": "画质失败模式", "tags": ["quality", "artifact"],
         "values": {"failures": ["模糊", "噪点", "水印", "文字乱码", "画面撕裂", "跳帧"]}},
        {"id": "neg_consistency_001", "kind": "negative", "name": "一致性失败模式", "tags": ["identity", "drift"],
         "values": {"failures": ["换脸", "服装突变", "发色漂移", "场景跳变", "道具消失"]}},
    ]
    return [DNAEntry(**row) for row in rows]


class DNAKnowledgeBase:
    """Prompt DNA 知识库（JSON 持久化，首次运行写入种子）。"""

    def __init__(self, path: str | Path = "storage/prompt_os/dna.json"):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._data: dict[str, dict] = self._load()

    def _load(self) -> dict:
        if not self.path.exists():
            data = {entry.id: entry.to_dict() for entry in _seed()}
            self.path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
            return data
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            return {}

    def _save(self) -> None:
        with self._lock:
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps(self._data, ensure_ascii=False, indent=2), encoding="utf-8")
            tmp.replace(self.path)

    def all(self) -> list[DNAEntry]:
        with self._lock:
            return [DNAEntry.from_dict(raw) for raw in self._data.values()]

    def by_kind(self, kind: str) -> list[DNAEntry]:
        return [entry for entry in self.all() if entry.kind == kind]

    def get(self, entry_id: str) -> DNAEntry | None:
        with self._lock:
            raw = self._data.get(entry_id)
        return DNAEntry.from_dict(raw) if raw else None

    def add(self, entry: DNAEntry) -> DNAEntry:
        with self._lock:
            self._data[entry.id] = entry.to_dict()
            self._save()
        return entry

    def add_from_dict(self, data: dict) -> DNAEntry:
        import uuid
        data = dict(data)
        data.setdefault("id", "")
        entry = DNAEntry.from_dict(data)
        if not entry.id:
            entry.id = f"{entry.kind}_{uuid.uuid4().hex[:8]}"
        return self.add(entry)

    def record_usage(self, entry_id: str) -> None:
        with self._lock:
            raw = self._data.get(entry_id)
            if raw:
                raw["usage_count"] = raw.get("usage_count", 0) + 1
                raw["updated_at"] = _model_now()
                self._save()

    def stats(self) -> dict:
        rows = self.all()
        by_kind: dict[str, int] = {}
        for entry in rows:
            by_kind[entry.kind] = by_kind.get(entry.kind, 0) + 1
        return {"entries": len(rows), "by_kind": by_kind, "kinds": sorted(by_kind)}

    def negative_words(self, ids: list[str] | None = None) -> list[str]:
        """从 NegativeDNA 展开失败模式词库（GPT 修改建议 4 落地）。"""
        entries = self.by_kind("negative")
        if ids:
            wanted = set(ids)
            entries = [e for e in entries if e.id in wanted]
        words: list[str] = []
        for entry in entries:
            words.extend(entry.values.get("failures", []))
        return words