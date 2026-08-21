"""Cinema DNA (电影感) cinematic rules integration module.

将 Cinema DNA 21:9×3 提示工程规则编码为 Python 数据结构，
提供 ``CinemaPromptEnhancer`` 类用于增强 AI Manga Studio 的关键帧
与视频生成提示词。

规则来源:
    - SKILL.md          — 核心 5 条优先级规则、构图压力库、色彩系统、
                          三联叙事结构、反 CG/反 AI 规则。
    - full-spec.md      — 完整导演 DNA 库(10 组)、镜头选择规则、
                          构图与场面调度、光学子系统。
    - v4-anti-ai.md     — 反 AI 图像纪律、镜头质感校准、受控脏化、
                          非常规三联节奏。

设计原则:
    1. 所有规则在模块加载时编码为常量字典 / 枚举, 不在运行时解析 Markdown。
    2. 输出遵循 Cinema DNA 第 11 节提示词写作规范:
       画幅基底 → 时空人物 → 动作状态 → 摄影机 → 光源 → 色彩 → 材质光学 → 负面约束。
    3. 正向提示词使用英文(便于直接喂给图像模型), 电影判断元数据保留中文。
    4. 与现有 creator.py 路由的 ``positive_prompt`` / ``negative_prompt``
       字段格式保持兼容。
"""

from __future__ import annotations

import random
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


# ===========================================================================
# 一、枚举定义
# ===========================================================================

class CompositionPressure(str, Enum):
    """7 种构图压力类型 (SKILL.md §4.1 构图压力库)。

    构图必须由"关系压力"产生, 而非随机选择远景/门框/负空间等模板。
    """

    OBSERVED = "observed"            # A. 被观察
    TRAPPED = "trapped"              # B. 被困住
    ALIENATION = "alienation"        # C. 关系疏离
    POWER_ASYMMETRY = "power"        # D. 权力不对等
    PSYCH_IMBALANCE = "psych"        # E. 心理失衡
    AFTERMATH = "aftermath"         # F. 事后状态
    SENSORY_INSERT = "sensory"      # G. 感官插入


class TriptychStructure(str, Enum):
    """6 种三联叙事结构 (SKILL.md §7)。

    三联不再固定为"建立—发展—余韵", 根据题材选择结构。
    """

    SPACE_CHARACTER_EVIDENCE = "space_char_evidence"    # §7.1 空间—人物—证据
    ORDER_ANOMALY_RESIDUE = "order_anomaly_residue"      # §7.2 秩序—异常—残留
    OBSERVER_OBSERVED_BLIND = "observer_blind"           # §7.3 观察者—被观察者—盲区
    DISTANCE_CLOSEUP_EMPTY = "distance_closeup_empty"    # §7.4 远距—突然贴近—空镜
    PARALLEL_EMOTION = "parallel_emotion"                 # §7.5 平行情绪三片段
    BEFORE_CRITICAL_IRREVERSIBLE = "before_critical"      # §7.6 事件前—临界点—不可逆


class DirectorDNA(str, Enum):
    """10 组导演 DNA 配方 (full-spec §10 + v4 validated recipes)。

    导演只作为内部配方, 必须转译为具体电影语言, 不在最终提示词里依赖导演名字。
    """

    PRECISE_ABSURDITY = "precise_absurdity"    # §10.1 精密荒诞 (韦斯·安德森)
    REALISTIC_EPIC = "realistic_epic"          # §10.2 现实史诗 (诺兰)
    SILENT_MONOLITH = "silent_monolith"         # §10.3 沉默巨构 (维伦纽瓦)
    EASTERN_WUXIA = "eastern_wuxia"             # §10.4 东方武侠 (胡金铨)
    DENSE_COLOR_EMOTION = "dense_color"         # §10.5 密色情绪 (王家卫)
    GEOMETRIC_UNKNOWN = "geometric_unknown"     # §10.6 几何未知 (库布里克)
    TIME_RUINS = "time_ruins"                   # §10.7 时间废墟 (塔可夫斯基)
    DISTANT_EASTERN = "distant_eastern"          # §10.8 远观东方 (侯孝贤/李安/黑泽明)
    COLD_GRAY_FUTURE = "cold_gray_future"       # §10.9 冷灰未来
    DOCUMENTARY_WITNESS = "documentary_witness" # §10.10/v4 纪实观察 (16mm 纪录式)


class ColorGradingMethod(str, Enum):
    """7 种色彩演绎方式 (SKILL.md §5.3)。"""

    LARGE_BLOCK = "large_block"                # 1. 大色块叙事
    LIMITED_PALETTE = "limited_palette"        # 2. 限定色谱
    COMPLEMENTARY_CONFLICT = "complementary"   # 3. 互补色冲突
    LIGHT_COLOR_SEPARATION = "light_sep"       # 4. 光色分离
    AIR_COMPOSITE = "air_composite"            # 5. 空气综合色
    HIGH_BRIGHTNESS = "high_brightness"         # 6. 高明度色彩
    OPTICAL_MIXING = "optical_mixing"           # 7. 光学混色与自然反射


class ColorContinuity(str, Enum):
    """5 种三联色彩连续方式 (SKILL.md §5.5)。"""

    STABLE_PALETTE = "stable"                  # 稳定色域
    INTERIOR_EXTERIOR = "int_ext"              # 内外转场
    ACCENT_MOVEMENT = "accent_movement"       # 强调色移动
    COLOR_FADING = "fading"                    # 色彩消退
    COMPOSITE_REVERSAL = "reversal"            # 综合色反转


class CaptureSubstrate(str, Enum):
    """7 种成像基底 (v4 patch §2 + SKILL.md §3 Step 6)。

    每组三联只选择一个主要成像基底。
    """

    RELEASE_PRINT_35MM = "35mm_print"          # 35mm release print
    TV_TRANSFER_16MM = "16mm_tv"               # 16mm television transfer
    VHS_BROADCAST = "vhs"                      # VHS / old broadcast capture
    MINIDV_DIGITAL = "minidv"                  # MiniDV / early digital video
    SURVEILLANCE_CRT = "surveillance"          # Surveillance / CRT / monitor rephotograph
    LONG_LENS_COMPRESSION = "long_lens"        # Long-lens film compression
    WIDE_WITNESS_POV = "wide_witness"          # Wide/fisheye witness POV


class ShotScale(str, Enum):
    """景别类型。"""

    EXTREME_WIDE = "extreme_wide"    # 大远景
    WIDE = "wide"                    # 远景
    MEDIUM_WIDE = "medium_wide"     # 中远景
    MEDIUM = "medium"               # 中景
    MEDIUM_CLOSE = "medium_close"   # 中近景
    CLOSE_UP = "close_up"           # 特写
    EXTREME_CLOSE = "extreme_close" # 大特写
    EMPTY = "empty"                  # 空镜


# ===========================================================================
# 二、构图压力库数据 (SKILL.md §4.1)
# ===========================================================================

COMPOSITION_PRESSURES: dict[CompositionPressure, dict[str, Any]] = {
    CompositionPressure.OBSERVED: {
        "name_cn": "被观察",
        "name_en": "observed",
        "applies_to": ["秘密", "监视", "迟到", "身份错位"],
        "methods": [
            "隔着玻璃、门缝、帘幕或人群观察",
            "前景观察者只出现肩部、头部或模糊轮廓",
            "关键动作发生在中远景",
            "观众不拥有完整信息",
        ],
        "prompt_fragment": (
            "observed through glass, doorway gap, curtain, or crowd; "
            "foreground witness reduced to shoulder or blurred silhouette; "
            "key action in mid-to-far ground; audience lacks full information"
        ),
        "preferred_lens": "long_lens",
    },
    CompositionPressure.TRAPPED: {
        "name_cn": "被困住",
        "name_en": "trapped",
        "applies_to": ["制度", "命运", "心理封闭", "仪式压力"],
        "methods": [
            "几何边界、桌面、走廊、门洞或座椅将人物压在局部",
            "极端俯拍或高位观察",
            "人物尺度小于空间",
            "空间秩序完整, 但人物位置出现一处偏差",
        ],
        "prompt_fragment": (
            "geometric boundaries — desk, corridor, doorway, or seating — "
            "compress the figure into a confined zone; figure smaller than space; "
            "spatial order intact with one meaningful deviation"
        ),
        "preferred_lens": "24-28mm",
    },
    CompositionPressure.ALIENATION: {
        "name_cn": "关系疏离",
        "name_en": "alienation",
        "applies_to": ["家庭", "亲密关系", "谈判", "诀别"],
        "methods": [
            "两人之间保留大面积空桌、床、走廊、地面或玻璃",
            "视线不相遇",
            "一人在亮区, 一人在暗区, 但不要戏剧化打光",
            "让空间物件成为第三方",
        ],
        "prompt_fragment": (
            "large negative space between two figures — empty table, bed, "
            "corridor, floor, or glass; sightlines do not meet; one in light, "
            "one in shadow, without theatrical lighting; spatial object as third party"
        ),
        "preferred_lens": "32-50mm",
    },
    CompositionPressure.POWER_ASYMMETRY: {
        "name_cn": "权力不对等",
        "name_en": "power_asymmetry",
        "applies_to": ["审判", "仪式", "战争", "组织", "政治与宗教空间"],
        "methods": [
            "低机位或高位俯视, 但必须有现实摄影机位置",
            "巨大墙面、台阶、门、屏幕或人群控制人物比例",
            "权力者不一定最大, 可以由空间为其背书",
        ],
        "prompt_fragment": (
            "low-angle or high-overhead camera with real physical position; "
            "massive wall, steps, door, screen, or crowd controls figure scale; "
            "power backed by spatial architecture, not figure size"
        ),
        "preferred_lens": "24-28mm",
    },
    CompositionPressure.PSYCH_IMBALANCE: {
        "name_cn": "心理失衡",
        "name_en": "psych_imbalance",
        "applies_to": ["发现", "错觉", "恐惧", "记忆断裂"],
        "methods": [
            "人物贴边",
            "头顶空间过多",
            "轻微倾斜",
            "焦点落在背景而非人物",
            "前景遮挡不完整",
        ],
        "prompt_fragment": (
            "figure pressed to frame edge; excessive headroom; slight tilt; "
            "focus on background rather than figure; incomplete foreground occlusion"
        ),
        "preferred_lens": "32-50mm",
    },
    CompositionPressure.AFTERMATH: {
        "name_cn": "事后状态",
        "name_en": "aftermath",
        "applies_to": ["事件刚结束", "某人已经离开", "秘密已发生"],
        "methods": [
            "人物缺席",
            "空椅、湿地、开着的门、未熄灭的灯、遗留衣物或错位物件",
            "镜头保持克制, 不拍解释性证据墙",
        ],
        "prompt_fragment": (
            "figure absent; empty chair, wet floor, open door, unextinguished lamp, "
            "leftover clothing or displaced objects; restrained, no explanatory evidence wall"
        ),
        "preferred_lens": "32-50mm",
    },
    CompositionPressure.SENSORY_INSERT: {
        "name_cn": "感官插入",
        "name_en": "sensory_insert",
        "applies_to": ["决定", "犹豫", "危险临界点"],
        "methods": [
            "嘴、手、后颈、鞋、湿发、衣料、钥匙、纸张等局部",
            "隐藏人物身份与空间全貌",
            "动作停在完成之前",
        ],
        "prompt_fragment": (
            "sensory fragment — mouth, hand, nape, shoe, wet hair, fabric, key, "
            "or paper; identity and spatial totality hidden; action frozen before completion"
        ),
        "preferred_lens": "65-85mm",
    },
}


# ===========================================================================
# 三、三联叙事结构数据 (SKILL.md §7)
# ===========================================================================

TRIPTYCH_STRUCTURES: dict[TriptychStructure, dict[str, Any]] = {
    TriptychStructure.SPACE_CHARACTER_EVIDENCE: {
        "name_cn": "空间—人物—证据",
        "name_en": "space_character_evidence",
        "suitable_for": ["建筑叙事", "产品叙事", "悬疑"],
        "shots": [
            {"function": "展示事件发生的空间与限制", "scale": ShotScale.WIDE},
            {"function": "人物处于一个未完成动作中", "scale": ShotScale.MEDIUM},
            {"function": "局部物件改变观众对前两张的理解", "scale": ShotScale.CLOSE_UP},
        ],
    },
    TriptychStructure.ORDER_ANOMALY_RESIDUE: {
        "name_cn": "秩序—异常—残留",
        "name_en": "order_anomaly_residue",
        "suitable_for": ["制度空间", "仪式", "权力"],
        "shots": [
            {"function": "稳定、完整的空间秩序", "scale": ShotScale.WIDE},
            {"function": "一处行为或位置出现异常", "scale": ShotScale.MEDIUM},
            {"function": "人物消失, 只剩事件残留", "scale": ShotScale.EMPTY},
        ],
    },
    TriptychStructure.OBSERVER_OBSERVED_BLIND: {
        "name_cn": "观察者—被观察者—盲区",
        "name_en": "observer_observed_blind",
        "suitable_for": ["监视", "秘密", "偷窥"],
        "shots": [
            {"function": "先确定观察者的位置", "scale": ShotScale.MEDIUM_WIDE},
            {"function": "展示被观察者的具体行为", "scale": ShotScale.MEDIUM},
            {"function": "展示双方都未注意到的信息", "scale": ShotScale.MEDIUM_CLOSE},
        ],
    },
    TriptychStructure.DISTANCE_CLOSEUP_EMPTY: {
        "name_cn": "远距—突然贴近—空镜",
        "name_en": "distance_closeup_empty",
        "suitable_for": ["离别", "发现", "转折"],
        "shots": [
            {"function": "人物很小, 环境占主导", "scale": ShotScale.EXTREME_WIDE},
            {"function": "突然切入脸部、身体或动作局部", "scale": ShotScale.CLOSE_UP},
            {"function": "空间仍在, 但人已经离开或改变位置", "scale": ShotScale.EMPTY},
        ],
    },
    TriptychStructure.PARALLEL_EMOTION: {
        "name_cn": "平行情绪三片段",
        "name_en": "parallel_emotion",
        "suitable_for": ["情绪", "记忆", "诗意"],
        "shots": [
            {"function": "统一色彩命题与情绪密度的片段一", "scale": ShotScale.MEDIUM},
            {"function": "统一色彩命题与情绪密度的片段二", "scale": ShotScale.MEDIUM_CLOSE},
            {"function": "统一色彩命题与情绪密度的片段三, 含重复但变形的视觉线索", "scale": ShotScale.CLOSE_UP},
        ],
    },
    TriptychStructure.BEFORE_CRITICAL_IRREVERSIBLE: {
        "name_cn": "事件前—临界点—不可逆结果",
        "name_en": "before_critical_irreversible",
        "suitable_for": ["历史", "神话", "科幻", "悬疑"],
        "shots": [
            {"function": "决定发生前的等待", "scale": ShotScale.WIDE},
            {"function": "动作即将完成的临界点", "scale": ShotScale.MEDIUM},
            {"function": "结果发生后的微小物件或人物反应", "scale": ShotScale.CLOSE_UP},
        ],
    },
}


# ===========================================================================
# 四、导演 DNA 库数据 (full-spec §10 + §10.10 强度控制维度)
# ===========================================================================

DIRECTOR_DNA_PROFILES: dict[DirectorDNA, dict[str, Any]] = {
    DirectorDNA.PRECISE_ABSURDITY: {
        "name_cn": "精密荒诞 DNA",
        "name_en": "precise_absurdity",
        "reference": "韦斯·安德森式视觉语言",
        "camera_ethic": "正面见证者",
        "staging": "轴线秩序 + 精确道具排列 + 群像站位",
        "rhythm": "程序化等待 + 几何重复",
        "light_logic": "平面化自然光, 舞台化均匀但不戏剧化",
        "color_discipline": "复古色块, 一个综合色母体 + 小面积反色",
        "signature_optics": "平面化景深, 边缘轻微软化",
        "extractions": [
            "正面静态机位", "严格但不过分机械的对称", "平面化景深",
            "精确道具排列", "冷静人物表情", "舞台化空间",
            "复古色块", "群像站位", "荒诞但严肃的瞬间",
        ],
        "prompt_snippet": (
            "frontal static camera, precise but not mechanical symmetry, "
            "flat depth, exact prop arrangement, calm expression, "
            "theatrical staging, retro color blocks, tableau group blocking"
        ),
    },
    DirectorDNA.REALISTIC_EPIC: {
        "name_cn": "现实史诗 DNA",
        "name_en": "realistic_epic",
        "reference": "诺兰式视觉语言",
        "camera_ethic": "受限参与者",
        "staging": "深透视 + 渺小人物 + 实景感",
        "rhythm": "行动前静止 + 突然缺席",
        "light_logic": "自然光, 冷暖冲突, 真实物理材质",
        "color_discipline": "焦褐、灰白、暗红, 一个综合色母体承担情绪论点",
        "signature_optics": "风、海浪、尘埃、烟雾, 克制颗粒",
        "extractions": [
            "巨大真实空间", "渺小人物", "深透视", "自然光",
            "真实物理材质", "风、海浪、尘埃、烟雾", "冷暖冲突",
            "时间、命运、未知", "实景感而非概念图感",
        ],
        "prompt_snippet": (
            "immense real space, tiny figure, deep perspective, natural light, "
            "physically plausible materials, wind waves dust smoke, "
            "cool-warm conflict, practical-set feeling not concept-art"
        ),
    },
    DirectorDNA.SILENT_MONOLITH: {
        "name_cn": "沉默巨构 DNA",
        "name_en": "silent_monolith",
        "reference": "维伦纽瓦式视觉语言",
        "camera_ethic": "仪式化对称",
        "staging": "极简巨大空间 + 粗粝建筑 + 小人物剪影",
        "rhythm": "几何重复 + 延迟揭示",
        "light_logic": "沙尘、浓雾、颗粒空气, 单一可解释光源",
        "color_discipline": "焦褐、灰白、暗红, 神秘但不解释",
        "signature_optics": "深负空间, 边缘软化, 遮挡面部",
        "extractions": [
            "极简巨大空间", "粗粝建筑", "小人物剪影",
            "沙尘、浓雾、颗粒空气", "仪式队列", "压迫几何",
            "焦褐、灰白、暗红", "神秘但不解释",
        ],
        "prompt_snippet": (
            "minimal vast space, brutalist architecture, small silhouette, "
            "sand dust dense fog particulate air, ritual queue, oppressive geometry, "
            "umber gray-white dark-red palette, mystery without explanation"
        ),
    },
    DirectorDNA.EASTERN_WUXIA: {
        "name_cn": "东方武侠 DNA",
        "name_en": "eastern_wuxia",
        "reference": "胡金铨式场面调度",
        "camera_ethic": "远观者",
        "staging": "山水与建筑共同叙事 + 门窗廊竹林帷幕形成层次",
        "rhythm": "动作前的静止 + 风吹衣摆与竹叶",
        "light_logic": "阴天散射光 + 微弱油灯/火光, 低饱和红或暗衣点缀",
        "color_discipline": "青灰 + 墨绿 + 朱砂, 大量留白",
        "signature_optics": "横向长卷感, 更多静止而非动作",
        "extractions": [
            "山水与建筑共同叙事", "门窗、廊道、竹林、帷幕形成层次",
            "人物隐藏于空间", "大量留白", "动作前的静止",
            "风吹衣摆与竹叶", "横向长卷感",
        ],
        "prompt_snippet": (
            "landscape and architecture co-narrate, doors windows corridors bamboo "
            "curtains form layers, figure hidden in space, abundant negative space, "
            "stillness before action, wind moves robes and bamboo, horizontal scroll feel"
        ),
    },
    DirectorDNA.DENSE_COLOR_EMOTION: {
        "name_cn": "密色情绪 DNA",
        "name_en": "dense_color_emotion",
        "reference": "王家卫及东亚都市情绪电影",
        "camera_ethic": "压缩距离的窥视",
        "staging": "狭窄室内 + 门框玻璃镜面帘幕遮挡 + 靠近但疏离的人物",
        "rhythm": "未解决停顿 + 错过",
        "light_logic": "潮湿、夜色、反射, 局部暖色灯具",
        "color_discipline": "深红、暗绿、烟黄、夜蓝, 狭窄色谱",
        "signature_optics": "局部 halation, 烟尘密度",
        "extractions": [
            "深红、暗绿、烟黄、夜蓝", "狭窄室内",
            "门框、玻璃、镜面、帘幕遮挡", "靠近但疏离的人物",
            "潮湿、夜色、反射", "错过、等待、欲望、记忆",
        ],
        "prompt_snippet": (
            "deep red dark green smoky yellow night blue, narrow interior, "
            "doorframe glass mirror curtain occlusion, close but alienated figures, "
            "humidity night reflection, missed encounter waiting desire memory"
        ),
    },
    DirectorDNA.GEOMETRIC_UNKNOWN: {
        "name_cn": "几何未知 DNA",
        "name_en": "geometric_unknown",
        "reference": "库布里克式视觉结构",
        "camera_ethic": "仪式化对称",
        "staging": "极端对称 + 中心透视 + 长走廊",
        "rhythm": "程序化等待 + 几何重复",
        "light_logic": "冷静空间, 单一可解释光源",
        "color_discipline": "秩序中的不安, 冷静色谱",
        "signature_optics": "一点透视, 克制颗粒",
        "extractions": [
            "极端对称", "中心透视", "冷静空间",
            "长走廊", "秩序中的不安", "仪式化动作", "建筑与人物冲突",
        ],
        "prompt_snippet": (
            "extreme symmetry, one-point perspective, cold calm space, "
            "long corridor, unease within order, ritualized action, "
            "architecture versus figure conflict"
        ),
    },
    DirectorDNA.TIME_RUINS: {
        "name_cn": "时间废墟 DNA",
        "name_en": "time_ruins",
        "reference": "塔可夫斯基式时间与遗迹感",
        "camera_ethic": "远观者",
        "staging": "废墟 + 旧工业空间 + 自然侵入建筑",
        "rhythm": "缓慢时间 + 延迟揭示",
        "light_logic": "风雨雾, 自然光, 水迹",
        "color_discipline": "记忆与现实叠压, 褪色色谱",
        "signature_optics": "水迹, 缓慢运动模糊, 克制颗粒",
        "extractions": [
            "水迹", "废墟", "旧工业空间", "风雨雾",
            "缓慢时间", "人物漫游", "自然侵入建筑", "记忆与现实叠压",
        ],
        "prompt_snippet": (
            "water stains, ruins, old industrial space, rain wind fog, "
            "slow time, wandering figure, nature invading architecture, "
            "memory and reality superimposed, faded palette"
        ),
    },
    DirectorDNA.DISTANT_EASTERN: {
        "name_cn": "远观东方 DNA",
        "name_en": "distant_eastern",
        "reference": "侯孝贤、李安、黑泽明等东方远景叙事",
        "camera_ethic": "远观者",
        "staging": "远观人物 + 自然遮挡 + 真实地形",
        "rhythm": "行动前静止 + 延迟揭示",
        "light_logic": "风雨尘土, 自然光",
        "color_discipline": "克制服装, 历史环境中的人",
        "signature_optics": "长焦远观, 风尘颗粒",
        "extractions": [
            "远观人物", "自然遮挡", "风雨尘土",
            "动作在空间中发生", "真实地形",
            "克制服装", "历史环境中的人",
        ],
        "prompt_snippet": (
            "distant figure observation, natural occlusion, rain wind dust, "
            "action unfolding in space, real terrain, restrained costume, "
            "human within historical environment"
        ),
    },
    DirectorDNA.COLD_GRAY_FUTURE: {
        "name_cn": "冷灰未来 DNA",
        "name_en": "cold_gray_future",
        "reference": "现代都市、科幻、办公室与高层空间",
        "camera_ethic": "监控式观察",
        "staging": "大面积玻璃 + 极简现代空间 + 城市天际线",
        "rhythm": "冰冷秩序 + 程序化等待",
        "light_logic": "冷灰蓝色空气, 荧光灯制度空间",
        "color_discipline": "冷灰蓝 + 深黑, 高层孤独",
        "signature_optics": "边缘软化, 局部 halation",
        "extractions": [
            "冷灰蓝色空气", "大面积玻璃", "极简现代空间",
            "城市天际线", "冰冷秩序", "高层孤独",
            "人物在结构中极小或被背光",
        ],
        "prompt_snippet": (
            "cold gray-blue air, large glass surfaces, minimal modern space, "
            "city skyline, cold institutional order, high-rise isolation, "
            "figure tiny or backlit within structure"
        ),
    },
    DirectorDNA.DOCUMENTARY_WITNESS: {
        "name_cn": "纪实观察 DNA",
        "name_en": "documentary_witness",
        "reference": "16mm 纪录式 + v4 县城荒诞现实主义",
        "camera_ethic": "手持不确定",
        "staging": "静态观察机位 + 普通县镇地点 + 一个被认真对待的荒诞物件",
        "rhythm": "无聊但真实的过渡 + 延迟揭示",
        "light_logic": "不完美曝光, 冷白管灯, 微弱招牌红",
        "color_discipline": "水泥灰或雨天混凝土 + 一两个生活色点缀",
        "signature_optics": "16mm 颗粒, 轻微色溢, 不均匀颗粒, 不完美曝光",
        "extractions": [
            "静态观察机位", "不完美曝光", "轻微色溢", "不均匀颗粒",
            "水泥灰或雨天混凝土色体", "生活色点缀: 公交站蓝/塑料红/褪色婚粉",
            "普通县镇地点: 公交站/商场中庭/诊所/走廊/空宴会厅",
            "一个被认真对待的荒诞物件",
        ],
        "prompt_snippet": (
            "static observational camera, imperfect exposure, slight color bleed, "
            "uneven grain, cement-gray or rainy concrete body, lived-in color accents, "
            "ordinary county-town location, one mundane absurd object treated seriously"
        ),
    },
}


# ===========================================================================
# 五、镜头规格数据 (SKILL.md §6.3 + full-spec §12)
# ===========================================================================

LENS_SPECS: dict[str, dict[str, Any]] = {
    "18-24mm": {
        "name_cn": "18–24mm",
        "use_for": ["巨构", "建筑", "史诗", "极端空间关系"],
        "note": "避免过度畸变, 不拉长人物",
        "prompt_fragment": "18-24mm wide-angle, vast architecture, extreme spatial relation",
        "subject_ratio": "2%-8%",
    },
    "24-28mm": {
        "name_cn": "24–28mm",
        "use_for": ["空间与人物比例", "建立镜头", "避免夸张透视"],
        "note": "Shot 1 默认: 中深景深, 人物 5%-15%, 强空间秩序",
        "prompt_fragment": "24-28mm, person 5-15% of frame, strong spatial order, medium-deep DOF",
        "subject_ratio": "5%-15%",
    },
    "28-35mm": {
        "name_cn": "28–35mm",
        "use_for": ["空间叙事", "人物与环境", "酒店", "街道", "房间", "山林", "群像"],
        "note": "默认电影焦段",
        "prompt_fragment": "28-35mm, default cinema focal length, person-environment relation",
        "subject_ratio": "10%-25%",
    },
    "32-40mm": {
        "name_cn": "32–40mm",
        "use_for": ["现场观察", "关系调度"],
        "note": "Shot 2 默认: 人物 20%-35%, 分层关系",
        "prompt_fragment": "32-40mm, observational staging, layered relation, person 20-35%",
        "subject_ratio": "20%-35%",
    },
    "40-50mm": {
        "name_cn": "40–50mm",
        "use_for": ["对话", "室内", "等待", "人物心理", "双人关系"],
        "note": "更自然克制的叙事",
        "prompt_fragment": "40-50mm, natural conversational distance, restrained psychological narrative",
        "subject_ratio": "25%-45%",
    },
    "50mm": {
        "name_cn": "50mm",
        "use_for": ["自然人物距离"],
        "note": "标准自然距离",
        "prompt_fragment": "50mm, natural human-eye distance",
        "subject_ratio": "30%-50%",
    },
    "65-85mm": {
        "name_cn": "65–85mm",
        "use_for": ["压缩", "局部和观察感", "人群中的人物", "隔窗/门框", "武侠远观", "孤独切离"],
        "note": "Shot 3 默认: 不要奶油化虚化",
        "prompt_fragment": "65-85mm, compressed observation, figure in crowd, through glass or doorway, no creamy bokeh",
        "subject_ratio": "40%-70%",
    },
    "100mm+": {
        "name_cn": "100mm 以上",
        "use_for": ["强烈压缩与距离感"],
        "note": "只在需要强烈压缩与距离感时使用",
        "prompt_fragment": "100mm+ telephoto, strong compression and distance",
        "subject_ratio": "50%-80%",
    },
    "long_lens": {
        "name_cn": "长焦隔窗",
        "use_for": ["被观察", "城市", "离别"],
        "note": "适合被观察、城市与离别",
        "prompt_fragment": "long-lens through glass, compressed distance, surveillance or departure",
        "subject_ratio": "30%-60%",
    },
}


# ===========================================================================
# 六、色彩系统数据 (SKILL.md §5)
# ===========================================================================

COLOR_GRADING_METHODS: dict[ColorGradingMethod, dict[str, Any]] = {
    ColorGradingMethod.LARGE_BLOCK: {
        "name_cn": "大色块叙事",
        "suitable_for": ["仪式", "权力", "历史转折", "群像"],
        "rule": "颜色来自布景和人物, 不是强行调色",
        "prompt_fragment": "color from costume, wall, flag, curtain, ground, or natural environment as main block",
    },
    ColorGradingMethod.LIMITED_PALETTE: {
        "name_cn": "限定色谱",
        "suitable_for": ["现代生活", "家庭", "城市", "低调悬疑"],
        "rule": "全片只围绕少数相邻色展开",
        "prompt_fragment": "limited adjacent palette — cream yellow tobacco brown olive green, or gray-blue lime-white oxidized red",
    },
    ColorGradingMethod.COMPLEMENTARY_CONFLICT: {
        "name_cn": "互补色冲突",
        "suitable_for": ["关系冲突", "戏剧"],
        "rule": "低纯度互补色, 避免饱和度过高, 不做 MV 或游戏海报",
        "prompt_fragment": "low-saturation complementary conflict — old red vs sickly green, or earth yellow vs dark blue",
    },
    ColorGradingMethod.LIGHT_COLOR_SEPARATION: {
        "name_cn": "光色分离",
        "suitable_for": ["离开", "等待", "记忆", "身份转变"],
        "rule": "日光与室内实景灯拥有不同色温, 人物位于两者交界",
        "prompt_fragment": "daylight and practical tungsten at different color temperature, figure at the boundary",
    },
    ColorGradingMethod.AIR_COMPOSITE: {
        "name_cn": "空气综合色",
        "suitable_for": ["海洋", "历史", "城市", "神话", "自然"],
        "rule": "通过雾、雨、海风、灰尘、玻璃或水面反射形成整体色彩",
        "prompt_fragment": "air composite color via fog rain sea-wind dust glass or water reflection",
    },
    ColorGradingMethod.HIGH_BRIGHTNESS: {
        "name_cn": "高明度色彩",
        "suitable_for": ["白天", "未来", "医院", "机场", "现代建筑", "制度空间"],
        "rule": "高明度不等于甜美或广告; 保留真实曝光、阴影和人物状态",
        "prompt_fragment": "high-luminance palette — warm white light gray pale blue faded pink — with real exposure and shadow",
    },
    ColorGradingMethod.OPTICAL_MIXING: {
        "name_cn": "光学混色与自然反射",
        "suitable_for": ["午后", "花园", "海岸", "夏日", "记忆", "人物近景"],
        "rule": "从自然光、天空、水面、玻璃、树叶和皮肤之间产生细微色彩变化",
        "prompt_fragment": "optical color mixing from natural light sky water glass leaves and skin, impressionist observation but live-action film",
    },
}

COLOR_CONTINUITY_METHODS: dict[ColorContinuity, dict[str, Any]] = {
    ColorContinuity.STABLE_PALETTE: {
        "name_cn": "稳定色域",
        "rule": "三张保持一致, 只改变光线密度",
    },
    ColorContinuity.INTERIOR_EXTERIOR: {
        "name_cn": "内外转场",
        "rule": "冷或中性外景 → 暖室内 → 去色余韵",
    },
    ColorContinuity.ACCENT_MOVEMENT: {
        "name_cn": "强调色移动",
        "rule": "同一个强调色从人物转移到物件或背景",
    },
    ColorContinuity.COLOR_FADING: {
        "name_cn": "色彩消退",
        "rule": "第一张最完整, 第三张只剩少量颜色",
    },
    ColorContinuity.COMPOSITE_REVERSAL: {
        "name_cn": "综合色反转",
        "rule": "前两张看似温暖, 第三张进入冷白现实; 必须由空间变化驱动",
    },
}

# 默认色彩搭配 (full-spec §15)
DEFAULT_COLOR_PALETTES: list[dict[str, str]] = [
    {"primary": "cold gray", "secondary": "smoke blue", "accent": "near black"},
    {"primary": "dark gold", "secondary": "umber brown", "accent": "deep black"},
    {"primary": "ink green", "secondary": "cinnabar red", "accent": "fog white"},
    {"primary": "sea blue", "secondary": "rice white", "accent": "dark red"},
    {"primary": "burnt orange", "secondary": "gray brown", "accent": "metal black"},
    {"primary": "cement gray", "secondary": "rainy concrete", "accent": "bus-stop blue"},
    {"primary": "olive umber", "secondary": "aged plaster", "accent": "oxidized brass"},
]


# ===========================================================================
# 七、成像基底数据 (v4 patch §2)
# ===========================================================================

CAPTURE_SUBSTRATES: dict[CaptureSubstrate, dict[str, Any]] = {
    CaptureSubstrate.RELEASE_PRINT_35MM: {
        "name_cn": "35mm 发行拷贝",
        "prompt_fragment": (
            "35mm release print, soft gate, print density, mild color breathing, "
            "medium-low microcontrast, fine uneven grain"
        ),
        "halation": "medium-low",
        "grain": "fine uneven",
    },
    CaptureSubstrate.TV_TRANSFER_16MM: {
        "name_cn": "16mm 电视转拍",
        "prompt_fragment": (
            "16mm television transfer, softer resolution, chunkier natural grain, "
            "slight color bleed, imperfect exposure, documentary immediacy"
        ),
        "halation": "low",
        "grain": "chunky natural",
    },
    CaptureSubstrate.VHS_BROADCAST: {
        "name_cn": "VHS / 旧广播转拍",
        "prompt_fragment": (
            "VHS / old broadcast capture, lower fidelity, scan softness, "
            "luma noise, color bleed, unstable blacks"
        ),
        "halation": "low",
        "grain": "luma noise",
    },
    CaptureSubstrate.MINIDV_DIGITAL: {
        "name_cn": "MiniDV / 早期数字视频",
        "prompt_fragment": (
            "MiniDV / early digital video, small-sensor practical light, "
            "limited dynamic range, slight edge harshness"
        ),
        "halation": "none",
        "grain": "minimal",
    },
    CaptureSubstrate.SURVEILLANCE_CRT: {
        "name_cn": "监控 / CRT / 屏幕翻拍",
        "prompt_fragment": (
            "surveillance / CRT / monitor rephotograph, geometry distortion, "
            "screen texture, glare, black crush"
        ),
        "halation": "screen glare",
        "grain": "scan line",
    },
    CaptureSubstrate.LONG_LENS_COMPRESSION: {
        "name_cn": "长焦胶片压缩",
        "prompt_fragment": (
            "long-lens film compression, restrained shallow focus, "
            "compressed figures, window or heat distortion"
        ),
        "halation": "low",
        "grain": "fine",
    },
    CaptureSubstrate.WIDE_WITNESS_POV: {
        "name_cn": "广角/鱼眼见证视角",
        "prompt_fragment": (
            "wide/fisheye witness POV, distortion justified by camera placement "
            "inside vehicle, doorway, crowd, checkpoint, or hiding place"
        ),
        "halation": "low",
        "grain": "fine",
    },
}


# ===========================================================================
# 八、反 CG / 反 AI 规则数据 (SKILL.md §9 + v4 patch)
# ===========================================================================

# v4 反 AI 纪律: 每张画面限制
ANTI_AI_PER_SHOT_LIMITS: dict[str, Any] = {
    "concrete_scene_details": "2-3",
    "primary_actions": 1,
    "secondary_clues": 1,
    "main_light_sources": 1,
    "composition_mechanisms": 1,
}

# 强制禁止项 (SKILL.md §9.1)
ANTI_AI_FORBIDDEN_TERMS: list[str] = [
    "CGI concept art", "game cinematic key art", "fantasy poster",
    "superhero scale", "hyper-detailed digital rendering", "volumetric light everywhere",
    "glowing magic cracks", "floating particles everywhere",
    "excessive smoke fog and sparks", "teal-orange blockbuster grading",
    "glossy skin", "perfect costume and props", "razor-sharp background",
    "HDR clarity", "artificial rim light", "neon cyberpunk as default future",
    "clean utopian white-and-pink future advertising",
    "overly ornate ancient costume-drama aesthetic",
]

# v4 禁用空泛词 (不写入最终提示词)
ANTI_AI_FORBIDDEN_WORDS: list[str] = [
    "rich detail", "highly detailed", "intricate", "epic", "dramatic",
    "volumetric", "beautiful", "masterpiece", "cinematic", "poetic",
    "emotional", "mysterious", "atmospheric", "hyper realistic",
    "ultra detailed", "razor sharp", "8k",
]

# 受控脏化家族 (v4 §3): 每组只选一个
CONTROLLED_DIRT_FAMILIES: list[str] = [
    "dust and dry scratches",
    "rain and wet reflection",
    "smoke and low-output lamps",
    "fluorescent institutional grime",
    "broadcast/video noise",
    "fogged glass or condensation",
    "sun-faded fabric and chipped paint",
]

# 光学缺陷禁用裸词 (full-spec §6.1.4)
OPTICAL_FORBIDDEN_BARE: list[str] = [
    "chromatic aberration", "RGB split", "heavy film grain",
    "vintage filter", "retro washed out", "cinematic color grading",
    "moody film still", "anamorphic flare", "strong aberration",
]

# 推荐英文基底 (SKILL.md §11.4)
ENGLISH_BASE_POSITIVE: str = (
    "live-action feature-film still, practical location, real actors, "
    "physically plausible set and props, restrained production design, "
    "soft highlight roll-off, medium-low microcontrast, subtle uneven grain, "
    "local optical softness, natural skin texture, no commercial fill light"
)

# 推荐负面补丁 (SKILL.md §11.5)
ENGLISH_BASE_NEGATIVE: str = (
    "no CGI concept art, no game key art, no glossy AI rendering, no HDR, "
    "no plastic skin, no excessive particles, no fantasy poster composition, "
    "no teal-orange grading, no artificial rim light, no commercial beauty lighting, "
    "no television-drama blocking"
)

# 东方题材追加负面
EASTERN_EXTRA_NEGATIVES: str = (
    "no xianxia glow, no magical sword aura, no plastic armor, "
    "no costume-drama beauty filter, no generic ink overlay"
)

# 科幻题材追加负面
SCIFI_EXTRA_NEGATIVES: str = (
    "no random holographic UI, no game boss scene, no excessive machinery, "
    "no neon cyberpunk unless requested"
)


# ===========================================================================
# 九、三联节奏 / 拼接数据 (v4 §4 + SKILL.md §13)
# ===========================================================================

TRIPTYCH_LAYOUTS: dict[str, dict[str, Any]] = {
    "equal": {"ratios": [1.0, 1.0, 1.0], "name_cn": "等高", "use_for": "默认"},
    "held_opening": {"ratios": [1.25, 0.9, 0.85], "name_cn": "开场更大", "use_for": "酒店/房间向外看"},
    "impact_middle": {"ratios": [0.85, 1.3, 0.85], "name_cn": "中段冲击", "use_for": "仪式/拒绝/典礼"},
    "aftertaste_ending": {"ratios": [0.85, 0.9, 1.25], "name_cn": "结尾余韵", "use_for": "海洋/离别/失去"},
    "uneven_memory": {"ratios": [0.7, 1.2, 0.75], "name_cn": "不均记忆条", "use_for": "记忆碎片"},
    "broken_surveillance": {"ratios": [1.0, 1.0, 1.0], "name_cn": "破碎监控条", "use_for": "监控/转拍"},
}

# 剧情种子库 (SKILL.md §8.3)
STORY_SEEDS: list[str] = [
    "错过", "误认", "拒绝执行", "迟到后的等待", "仪式中的缺席",
    "秘密被第三人看到", "胜利后的错误", "归来后无法进入",
    "交换物被调包", "记忆与现实不一致", "群体庆祝中的个人恐惧",
    "救援完成后发现对象错误", "神谕、命令或制度要求与个人决定冲突",
]


# ===========================================================================
# 十、光源规则 (SKILL.md §6.5)
# ===========================================================================

PRACTICAL_LIGHT_SOURCES: list[str] = [
    "single window daylight", "overcast diffused light", "afternoon hard light",
    "daylight and indoor tungsten boundary", "fluorescent institutional space",
    "candle oil-lamp firelight (historical practical)",
    "reflection from water snow or wall surface",
]


# ===========================================================================
# 十一、Pydantic 数据模型
# ===========================================================================

class CameraSpec(BaseModel):
    """摄影机规格 (SKILL.md §6.2: 每张图至少明确五项)。"""

    focal_length: str = Field(default="35mm", description="焦段")
    camera_height: str = Field(default="eye-level", description="摄影机高度")
    subject_distance: str = Field(default="medium", description="与主体距离")
    subject_ratio: str = Field(default="15%", description="主体在画面中的比例")
    spatial_axis: str = Field(default="horizontal", description="主空间轴线")
    foreground_obstruction: str = Field(default="none", description="前景遮挡")
    focus_point: str = Field(default="subject", description="焦点位置")
    light_source: str = Field(default="single window daylight", description="主要光源")
    sightline: str = Field(default="toward background", description="人物视线")
    info_layer: str = Field(default="midground", description="关键信息所在层")


class ColorGrade(BaseModel):
    """色彩命题 (SKILL.md §5)。"""

    method: str = Field(default="limited_palette", description="色彩演绎方式")
    primary: str = Field(default="cold gray", description="主色域")
    secondary: str = Field(default="smoke blue", description="次色域")
    accent: str = Field(default="near black", description="强调色 (面积 5%-15%)")
    accent_ratio: str = Field(default="5-15%", description="强调色面积比")
    source: str = Field(default="wall, costume, natural light", description="颜色来源")
    continuity: str = Field(default="stable", description="三联色彩连续方式")
    proposition: str = Field(default="", description="一句话色彩命题")


class CompositionInfo(BaseModel):
    """构图信息。"""

    pressure_type: str = Field(default="observed", description="构图压力类型")
    pressure_name_cn: str = Field(default="被观察", description="构图压力中文名")
    sightline_flow: str = Field(default="", description="视线流量描述")
    foreground_rule: str = Field(default="", description="前景虚焦规则")


class EnhancedKeyframePrompt(BaseModel):
    """增强后的关键帧提示词 (enhance_keyframe_prompt 返回)。"""

    positive_prompt: str = Field(default="", description="正向提示词 (英文)")
    negative_prompt: str = Field(default="", description="负面提示词 (英文)")
    camera_spec: CameraSpec = Field(default_factory=CameraSpec, description="摄影机规格")
    color_grade: ColorGrade = Field(default_factory=ColorGrade, description="色彩命题")
    composition_type: str = Field(default="observed", description="构图压力类型")


class MotionEnhancement(BaseModel):
    """视频运动增强。"""

    motion_description: str = Field(default="", description="运动描述")
    camera_movement: str = Field(default="static", description="摄影机运动")
    rhythm: str = Field(default="slow", description="节奏")
    motion_bucket_hint: int = Field(default=127, description="运动强度建议 (0-255)")
    special_lens_event: str = Field(default="", description="特殊镜头/光事件 (v4 §5.1)")


class EnhancedVideoPrompt(BaseModel):
    """增强后的视频提示词 (enhance_video_prompt 返回)。"""

    positive_prompt: str = Field(default="", description="正向提示词 (英文)")
    negative_prompt: str = Field(default="", description="负面提示词 (英文)")
    motion_enhancement: MotionEnhancement = Field(default_factory=MotionEnhancement)


class TriptychShot(BaseModel):
    """三联中的单个镜头描述。"""

    shot_index: int = Field(description="镜头序号 (1-3)")
    function: str = Field(default="", description="镜头功能")
    scale: str = Field(default="medium", description="景别")
    focal_length: str = Field(default="35mm", description="焦段")
    composition: str = Field(default="", description="构图机制")
    action: str = Field(default="", description="主要动作")
    info_layer: str = Field(default="midground", description="关键信息层")
    prompt: str = Field(default="", description="完整英文提示词")


class DirectorDNAProfile(BaseModel):
    """导演 DNA 风格档案 (get_director_dna 返回)。"""

    name: str = Field(default="", description="DNA 名称 (英文)")
    name_cn: str = Field(default="", description="DNA 名称 (中文)")
    reference: str = Field(default="", description="参考来源 (内部配方, 不写入提示词)")
    camera_ethic: str = Field(default="", description="摄影机伦理")
    staging: str = Field(default="", description="调度习惯")
    rhythm: str = Field(default="", description="节奏")
    light_logic: str = Field(default="", description="光线逻辑")
    color_discipline: str = Field(default="", description="色彩纪律")
    signature_optics: str = Field(default="", description="标志性光学缺陷")
    extractions: list[str] = Field(default_factory=list, description="提取的具体视觉语言")
    prompt_snippet: str = Field(default="", description="可直接拼接的英文提示词片段")


# ===========================================================================
# 十二、CinemaPromptEnhancer 主类
# ===========================================================================

# mood → 构图压力映射
_MOOD_TO_PRESSURE: dict[str, CompositionPressure] = {
    "紧张": CompositionPressure.POWER_ASYMMETRY,
    "tense": CompositionPressure.POWER_ASYMMETRY,
    "孤独": CompositionPressure.ALIENATION,
    "lonely": CompositionPressure.ALIENATION,
    "孤独感": CompositionPressure.ALIENATION,
    "疏离": CompositionPressure.ALIENATION,
    "alienated": CompositionPressure.ALIENATION,
    "秘密": CompositionPressure.OBSERVED,
    "secret": CompositionPressure.OBSERVED,
    "监视": CompositionPressure.OBSERVED,
    "surveillance": CompositionPressure.OBSERVED,
    "恐惧": CompositionPressure.PSYCH_IMBALANCE,
    "fear": CompositionPressure.PSYCH_IMBALANCE,
    "恐惧感": CompositionPressure.PSYCH_IMBALANCE,
    "发现": CompositionPressure.PSYCH_IMBALANCE,
    "discovery": CompositionPressure.PSYCH_IMBALANCE,
    "记忆": CompositionPressure.PSYCH_IMBALANCE,
    "memory": CompositionPressure.PSYCH_IMBALANCE,
    "离别": CompositionPressure.AFTERMATH,
    "departure": CompositionPressure.AFTERMATH,
    "事后": CompositionPressure.AFTERMATH,
    "aftermath": CompositionPressure.AFTERMATH,
    "犹豫": CompositionPressure.SENSORY_INSERT,
    "hesitation": CompositionPressure.SENSORY_INSERT,
    "决定": CompositionPressure.SENSORY_INSERT,
    "decision": CompositionPressure.SENSORY_INSERT,
    "危险": CompositionPressure.SENSORY_INSERT,
    "danger": CompositionPressure.SENSORY_INSERT,
    "被困": CompositionPressure.TRAPPED,
    "trapped": CompositionPressure.TRAPPED,
    "仪式": CompositionPressure.TRAPPED,
    "ritual": CompositionPressure.TRAPPED,
    "权力": CompositionPressure.POWER_ASYMMETRY,
    "power": CompositionPressure.POWER_ASYMMETRY,
    "审判": CompositionPressure.POWER_ASYMMETRY,
    "judgment": CompositionPressure.POWER_ASYMMETRY,
    "等待": CompositionPressure.AFTERMATH,
    "waiting": CompositionPressure.AFTERMATH,
}

# mood → 色彩演绎方式映射
_MOOD_TO_COLOR: dict[str, ColorGradingMethod] = {
    "紧张": ColorGradingMethod.COMPLEMENTARY_CONFLICT,
    "tense": ColorGradingMethod.COMPLEMENTARY_CONFLICT,
    "孤独": ColorGradingMethod.LIMITED_PALETTE,
    "lonely": ColorGradingMethod.LIMITED_PALETTE,
    "秘密": ColorGradingMethod.LIGHT_COLOR_SEPARATION,
    "secret": ColorGradingMethod.LIGHT_COLOR_SEPARATION,
    "恐惧": ColorGradingMethod.AIR_COMPOSITE,
    "fear": ColorGradingMethod.AIR_COMPOSITE,
    "记忆": ColorGradingMethod.OPTICAL_MIXING,
    "memory": ColorGradingMethod.OPTICAL_MIXING,
    "温暖": ColorGradingMethod.HIGH_BRIGHTNESS,
    "warm": ColorGradingMethod.HIGH_BRIGHTNESS,
    "白天": ColorGradingMethod.HIGH_BRIGHTNESS,
    "daytime": ColorGradingMethod.HIGH_BRIGHTNESS,
    "仪式": ColorGradingMethod.LARGE_BLOCK,
    "ritual": ColorGradingMethod.LARGE_BLOCK,
    "权力": ColorGradingMethod.LARGE_BLOCK,
    "power": ColorGradingMethod.LARGE_BLOCK,
    "海洋": ColorGradingMethod.AIR_COMPOSITE,
    "ocean": ColorGradingMethod.AIR_COMPOSITE,
    "城市": ColorGradingMethod.LIMITED_PALETTE,
    "urban": ColorGradingMethod.LIMITED_PALETTE,
}

# theme → 导演 DNA 映射
_THEME_TO_DIRECTOR: dict[str, DirectorDNA] = {
    "东方": DirectorDNA.EASTERN_WUXIA,
    "武侠": DirectorDNA.EASTERN_WUXIA,
    "古代": DirectorDNA.DISTANT_EASTERN,
    "历史": DirectorDNA.REALISTIC_EPIC,
    "神话": DirectorDNA.REALISTIC_EPIC,
    "科幻": DirectorDNA.COLD_GRAY_FUTURE,
    "未来": DirectorDNA.COLD_GRAY_FUTURE,
    "都市": DirectorDNA.DENSE_COLOR_EMOTION,
    "城市": DirectorDNA.DENSE_COLOR_EMOTION,
    "现代": DirectorDNA.COLD_GRAY_FUTURE,
    "荒诞": DirectorDNA.PRECISE_ABSURDITY,
    "精密": DirectorDNA.PRECISE_ABSURDITY,
    "巨构": DirectorDNA.SILENT_MONOLITH,
    "废墟": DirectorDNA.TIME_RUINS,
    "记忆": DirectorDNA.TIME_RUINS,
    "纪实": DirectorDNA.DOCUMENTARY_WITNESS,
    "县城": DirectorDNA.DOCUMENTARY_WITNESS,
    "悬疑": DirectorDNA.GEOMETRIC_UNKNOWN,
    "恐怖": DirectorDNA.GEOMETRIC_UNKNOWN,
}

# shot_type → 焦段映射
_SHOT_TYPE_TO_LENS: dict[str, str] = {
    "extreme_wide": "18-24mm",
    "wide": "24-28mm",
    "establishing": "24-28mm",
    "medium_wide": "28-35mm",
    "medium": "32-40mm",
    "medium_close": "40-50mm",
    "close_up": "65-85mm",
    "extreme_close": "100mm+",
    "empty": "32-40mm",
    "远景": "24-28mm",
    "中景": "32-40mm",
    "近景": "40-50mm",
    "特写": "65-85mm",
    "大特写": "100mm+",
    "空镜": "32-40mm",
}


class CinemaPromptEnhancer:
    """Cinema DNA 提示词增强器。

    将基础场景描述增强为符合 Cinema DNA 电影感规则的关键帧 / 视频提示词。

    核心能力:
        - 应用 7 种构图压力类型 (被观察/被困住/关系疏离/权力不对等/
          心理失衡/事后状态/感官插入)
        - 从 6 种三联叙事结构中选择
        - 匹配 10 组导演 DNA 配方
        - 匹配镜头规格 (18-24mm 至 100mm+)
        - 应用色彩命题 (7 种演绎 + 5 种连续方式)
        - 应用 v4 反 AI/反 CG 规则
        - 生成正向与负面提示词

    用法::

        enhancer = CinemaPromptEnhancer()
        result = enhancer.enhance_keyframe_prompt(
            scene_desc="一个女人独自在高层办公室看着城市",
            shot_type="medium",
            mood="孤独",
        )
        print(result["positive_prompt"])
    """

    def __init__(self, *, seed: int | None = None) -> None:
        """初始化增强器。

        Args:
            seed: 随机种子, 用于受控随机选择 (None 表示真随机)。
        """
        self._rng = random.Random(seed) if seed is not None else random.Random()

    # ------------------------------------------------------------------
    # 公开方法
    # ------------------------------------------------------------------

    def enhance_keyframe_prompt(
        self,
        scene_desc: str,
        shot_type: str = "medium",
        mood: str = "",
    ) -> dict[str, Any]:
        """增强关键帧提示词。

        Args:
            scene_desc: 基础场景描述 (中英文均可)。
            shot_type: 景别类型 (如 wide/medium/close_up 或 远景/中景/特写)。
            mood: 情绪关键词 (如 孤独/紧张/秘密)。

        Returns:
            dict 包含: positive_prompt, negative_prompt,
            camera_spec, color_grade, composition_type。
        """
        # 1. 选择构图压力类型
        pressure = self._select_composition_pressure(mood)
        pressure_data = COMPOSITION_PRESSURES[pressure]

        # 2. 选择导演 DNA
        director = self._select_director_dna(scene_desc)
        director_data = DIRECTOR_DNA_PROFILES[director]

        # 3. 选择镜头规格
        lens_key = self._select_lens(shot_type, pressure)
        lens_data = LENS_SPECS.get(lens_key, LENS_SPECS["28-35mm"])

        # 4. 选择色彩命题
        color_method = self._select_color_method(mood)
        color_data = COLOR_GRADING_METHODS[color_method]
        palette = self._rng.choice(DEFAULT_COLOR_PALETTES)
        continuity = self._rng.choice(list(ColorContinuity))
        continuity_data = COLOR_CONTINUITY_METHODS[continuity]

        # 5. 选择成像基底
        substrate = self._select_capture_substrate(scene_desc, director)
        substrate_data = CAPTURE_SUBSTRATES[substrate]

        # 6. 选择光源
        light_source = self._rng.choice(PRACTICAL_LIGHT_SOURCES)

        # 7. 构建 camera_spec
        camera_spec = CameraSpec(
            focal_length=lens_key,
            camera_height=self._infer_camera_height(pressure),
            subject_distance=lens_data.get("subject_ratio", "medium"),
            subject_ratio=lens_data.get("subject_ratio", "15%"),
            spatial_axis="horizontal" if "wide" in lens_key or "24" in lens_key else "layered",
            foreground_obstruction=pressure_data["methods"][0] if pressure_data["methods"] else "none",
            focus_point="background" if pressure == CompositionPressure.PSYCH_IMBALANCE else "subject",
            light_source=light_source,
            sightline="toward background" if pressure == CompositionPressure.AFTERMATH else "toward subject",
            info_layer="background" if pressure in (CompositionPressure.AFTERMATH, CompositionPressure.OBSERVED) else "midground",
        )

        # 8. 构建 color_grade
        color_proposition = self._build_color_proposition(palette, continuity_data)
        color_grade = ColorGrade(
            method=color_method.value,
            primary=palette["primary"],
            secondary=palette["secondary"],
            accent=palette["accent"],
            accent_ratio="5-15%",
            source=color_data["rule"],
            continuity=continuity.value,
            proposition=color_proposition,
        )

        # 9. 组装正向提示词 (遵循 §11.2 结构)
        positive = self._assemble_positive_prompt(
            scene_desc=scene_desc,
            substrate_data=substrate_data,
            lens_data=lens_data,
            pressure_data=pressure_data,
            director_data=director_data,
            color_data=color_data,
            palette=palette,
            light_source=light_source,
        )

        # 10. 组装负面提示词
        negative = self._assemble_negative_prompt(scene_desc)

        return {
            "positive_prompt": positive,
            "negative_prompt": negative,
            "camera_spec": camera_spec.model_dump(),
            "color_grade": color_grade.model_dump(),
            "composition_type": pressure.value,
        }

    def enhance_video_prompt(
        self,
        scene_desc: str,
        motion_desc: str = "",
        shot_type: str = "medium",
    ) -> dict[str, Any]:
        """增强视频提示词。

        在关键帧提示词基础上增加运动描述、摄影机运动和节奏。

        Args:
            scene_desc: 基础场景描述。
            motion_desc: 运动描述 (如 "缓慢推近"/"人物转身离开")。
            shot_type: 景别类型。

        Returns:
            dict 包含: positive_prompt, negative_prompt, motion_enhancement。
        """
        # 复用关键帧增强逻辑获取基础
        base = self.enhance_keyframe_prompt(scene_desc, shot_type, mood="")

        # 推断运动参数
        camera_movement = self._infer_camera_movement(motion_desc, shot_type)
        rhythm = self._infer_rhythm(motion_desc)
        motion_bucket = self._infer_motion_bucket(motion_desc, shot_type)
        special_event = self._maybe_special_lens_event(scene_desc)

        motion_enhancement = MotionEnhancement(
            motion_description=motion_desc or "subtle ambient motion",
            camera_movement=camera_movement,
            rhythm=rhythm,
            motion_bucket_hint=motion_bucket,
            special_lens_event=special_event,
        )

        # 在正向提示词中追加运动增强
        motion_parts: list[str] = []
        if motion_desc:
            motion_parts.append(motion_desc)
        motion_parts.append(f"camera movement: {camera_movement}")
        motion_parts.append(f"rhythm: {rhythm}")
        if special_event:
            motion_parts.append(f"motivated special: {special_event}")

        positive = base["positive_prompt"] + ", " + ", ".join(motion_parts)

        # 视频追加负面
        negative = base["negative_prompt"] + (
            ", no jarring motion, no unnatural morphing, no flickering, "
            "no temporal instability, no puppet-like animation"
        )

        return {
            "positive_prompt": positive,
            "negative_prompt": negative,
            "motion_enhancement": motion_enhancement.model_dump(),
        }

    def get_triptych_structure(self, story_beats: list[str] | str = "") -> list[dict[str, Any]]:
        """生成三联叙事结构。

        从 6 种三联叙事结构中选择最贴合 story_beats 的一种,
        返回 3 个镜头描述。

        Args:
            story_beats: 故事节拍列表或单个描述字符串。
                         若为列表, 长度应 >= 1; 长度 >= 3 时直接映射。

        Returns:
            list[dict] 长度为 3, 每项含: shot_index, function, scale,
            focal_length, composition, action, info_layer, prompt。
        """
        # 标准化输入
        if isinstance(story_beats, str):
            beats = [story_beats] if story_beats else []
        else:
            beats = list(story_beats)

        # 选择三联结构
        structure = self._select_triptych_structure(beats)
        struct_data = TRIPTYCH_STRUCTURES[structure]

        # 选择共享的导演 DNA 和色彩命题
        combined_desc = " ".join(beats)
        director = self._select_director_dna(combined_desc)
        director_data = DIRECTOR_DNA_PROFILES[director]
        color_method = self._select_color_method("")
        palette = self._rng.choice(DEFAULT_COLOR_PALETTES)
        substrate = self._select_capture_substrate(combined_desc, director)
        substrate_data = CAPTURE_SUBSTRATES[substrate]

        # 默认焦段递进: 建立→关系→余韵
        default_lenses = ["24-28mm", "32-50mm", "50-85mm"]

        shots: list[dict[str, Any]] = []
        for i, shot_def in enumerate(struct_data["shots"]):
            scale = shot_def["scale"].value
            function = shot_def["function"]
            action = beats[i] if i < len(beats) else function

            lens_key = default_lenses[i] if i < len(default_lenses) else "35mm"
            lens_data = LENS_SPECS.get(lens_key, LENS_SPECS["28-35mm"])

            prompt = self._assemble_positive_prompt(
                scene_desc=action,
                substrate_data=substrate_data,
                lens_data=lens_data,
                pressure_data={"prompt_fragment": ""},
                director_data=director_data,
                color_data=COLOR_GRADING_METHODS[color_method],
                palette=palette,
                light_source=self._rng.choice(PRACTICAL_LIGHT_SOURCES),
            )

            shots.append({
                "shot_index": i + 1,
                "function": function,
                "scale": scale,
                "focal_length": lens_key,
                "composition": director_data["staging"],
                "action": action,
                "info_layer": "foreground" if i == 2 else "midground",
                "prompt": prompt,
            })

        return shots

    def get_director_dna(self, theme: str) -> dict[str, Any]:
        """获取导演 DNA 风格档案。

        根据 theme 关键词匹配最合适的导演 DNA 配方,
        返回包含摄影机伦理、调度、节奏、光线、色彩纪律等完整档案。

        Args:
            theme: 主题关键词 (如 "东方武侠"/"科幻"/"都市孤独")。

        Returns:
            dict 包含: name, name_cn, reference, camera_ethic, staging,
            rhythm, light_logic, color_discipline, signature_optics,
            extractions, prompt_snippet。
        """
        director = self._select_director_dna(theme)
        data = DIRECTOR_DNA_PROFILES[director]
        profile = DirectorDNAProfile(
            name=data["name_en"],
            name_cn=data["name_cn"],
            reference=data["reference"],
            camera_ethic=data["camera_ethic"],
            staging=data["staging"],
            rhythm=data["rhythm"],
            light_logic=data["light_logic"],
            color_discipline=data["color_discipline"],
            signature_optics=data["signature_optics"],
            extractions=data["extractions"],
            prompt_snippet=data["prompt_snippet"],
        )
        return profile.model_dump()

    # ------------------------------------------------------------------
    # 内部选择方法 (受控随机)
    # ------------------------------------------------------------------

    def _select_composition_pressure(self, mood: str) -> CompositionPressure:
        """根据 mood 关键词选择构图压力类型 (SKILL.md §1.3 受控随机)。"""
        mood_lower = mood.lower().strip()
        for keyword, pressure in _MOOD_TO_PRESSURE.items():
            if keyword in mood_lower:
                return pressure
        # 无匹配时受控随机
        return self._rng.choice(list(CompositionPressure))

    def _select_director_dna(self, text: str) -> DirectorDNA:
        """根据文本关键词选择导演 DNA。"""
        text_lower = text.lower()
        for keyword, director in _THEME_TO_DIRECTOR.items():
            if keyword in text or keyword.lower() in text_lower:
                return director
        return self._rng.choice(list(DirectorDNA))

    def _select_lens(self, shot_type: str, pressure: CompositionPressure) -> str:
        """根据景别和构图压力选择镜头规格。"""
        shot_lower = shot_type.lower().strip()
        # 优先按景别匹配
        for key, lens in _SHOT_TYPE_TO_LENS.items():
            if key in shot_lower:
                return lens
        # 其次按构图压力的偏好镜头
        pressure_data = COMPOSITION_PRESSURES.get(pressure)
        if pressure_data and pressure_data.get("preferred_lens"):
            return pressure_data["preferred_lens"]
        return "28-35mm"

    def _select_color_method(self, mood: str) -> ColorGradingMethod:
        """根据 mood 选择色彩演绎方式。"""
        mood_lower = mood.lower().strip()
        for keyword, method in _MOOD_TO_COLOR.items():
            if keyword in mood_lower:
                return method
        return self._rng.choice(list(ColorGradingMethod))

    def _select_capture_substrate(
        self, scene_desc: str, director: DirectorDNA,
    ) -> CaptureSubstrate:
        """选择成像基底。"""
        desc_lower = scene_desc.lower()
        # 纪实观察 DNA → 16mm
        if director == DirectorDNA.DOCUMENTARY_WITNESS:
            return CaptureSubstrate.TV_TRANSFER_16MM
        # 监控/监控关键词
        if any(kw in desc_lower for kw in ("监控", "surveillance", "cctv", "monitor")):
            return CaptureSubstrate.SURVEILLANCE_CRT
        # 被观察/隔窗 → 长焦
        if any(kw in desc_lower for kw in ("隔窗", "through glass", "观察", "observe")):
            return CaptureSubstrate.LONG_LENS_COMPRESSION
        # 默认 35mm
        return CaptureSubstrate.RELEASE_PRINT_35MM

    def _select_triptych_structure(self, beats: list[str]) -> TriptychStructure:
        """根据故事节拍选择三联叙事结构。"""
        combined = " ".join(beats).lower()
        # 关键词匹配
        if any(kw in combined for kw in ("离别", "departure", "失去", "loss")):
            return TriptychStructure.DISTANCE_CLOSEUP_EMPTY
        if any(kw in combined for kw in ("仪式", "ritual", "典礼", "拒绝", "refusal")):
            return TriptychStructure.ORDER_ANOMALY_RESIDUE
        if any(kw in combined for kw in ("监视", "surveillance", "秘密", "secret", "偷窥")):
            return TriptychStructure.OBSERVER_OBSERVED_BLIND
        if any(kw in combined for kw in ("记忆", "memory", "情绪", "emotion", "诗意")):
            return TriptychStructure.PARALLEL_EMOTION
        if any(kw in combined for kw in ("历史", "history", "神话", "myth", "科幻", "sci", "悬疑", "mystery")):
            return TriptychStructure.BEFORE_CRITICAL_IRREVERSIBLE
        if any(kw in combined for kw in ("建筑", "architecture", "产品", "product", "空间", "space")):
            return TriptychStructure.SPACE_CHARACTER_EVIDENCE
        # 默认受控随机
        return self._rng.choice(list(TriptychStructure))

    def _infer_camera_height(self, pressure: CompositionPressure) -> str:
        """根据构图压力推断摄影机高度。"""
        if pressure == CompositionPressure.TRAPPED:
            return "high overhead"
        if pressure == CompositionPressure.POWER_ASYMMETRY:
            return "low-angle"
        if pressure == CompositionPressure.SENSORY_INSERT:
            return "close to subject"
        return "eye-level"

    def _infer_camera_movement(self, motion_desc: str, shot_type: str) -> str:
        """推断摄影机运动方式。"""
        desc_lower = (motion_desc or "").lower()
        if any(kw in desc_lower for kw in ("推近", "push", "dolly in", "zoom in")):
            return "slow dolly-in"
        if any(kw in desc_lower for kw in ("拉远", "pull", "dolly out", "zoom out")):
            return "slow dolly-out"
        if any(kw in desc_lower for kw in ("横移", "pan", "track", "横摇")):
            return "lateral tracking"
        if any(kw in desc_lower for kw in ("跟随", "follow", "跟拍")):
            return "following tracking"
        if any(kw in desc_lower for kw in ("手持", "handheld", "晃动")):
            return "handheld"
        if any(kw in desc_lower for kw in ("静止", "static", "固定")):
            return "static"
        # 根据景别推断
        if "wide" in shot_type or "远景" in shot_type:
            return "slow lateral drift"
        if "close" in shot_type or "特写" in shot_type:
            return "subtle handheld"
        return "static with subtle drift"

    def _infer_rhythm(self, motion_desc: str) -> str:
        """推断节奏。"""
        desc_lower = (motion_desc or "").lower()
        if any(kw in desc_lower for kw in ("快", "fast", "急", "rapid")):
            return "fast"
        if any(kw in desc_lower for kw in ("慢", "slow", "缓慢", "lingering")):
            return "slow"
        return "medium"

    def _infer_motion_bucket(self, motion_desc: str, shot_type: str) -> int:
        """推断运动强度建议 (Wan2.2 motion_bucket_id 0-255)。"""
        rhythm = self._infer_rhythm(motion_desc)
        if rhythm == "fast":
            return 180
        if rhythm == "slow":
            return 80
        # 中速根据景别微调
        if "close" in shot_type or "特写" in shot_type:
            return 100
        return 127

    def _maybe_special_lens_event(self, scene_desc: str) -> str:
        """根据场景决定是否插入特殊镜头/光事件 (v4 §5.1)。

        默认节奏: 两张稳定 + 一张特殊。此方法仅判断是否需要。
        """
        desc_lower = scene_desc.lower()
        if any(kw in desc_lower for kw in ("水", "water", "pool", "雨", "rain")):
            return "water caustics from real wet surface"
        if any(kw in desc_lower for kw in ("投影", "projector", "百叶", "blind", "venetian")):
            return "venetian-blind shadows cutting across subject"
        if any(kw in desc_lower for kw in ("车灯", "headlight", "车", "car")):
            return "car headlights sweeping through room"
        return ""

    def _build_color_proposition(
        self, palette: dict[str, str], continuity_data: dict[str, Any],
    ) -> str:
        """构建一句话色彩命题 (SKILL.md §1.4)。"""
        return (
            f"{palette['primary']} as dominant body, {palette['secondary']} as "
            f"secondary, {palette['accent']} as small accent (5-15%); "
            f"continuity: {continuity_data['name_cn']} — {continuity_data['rule']}"
        )

    # ------------------------------------------------------------------
    # 提示词组装方法
    # ------------------------------------------------------------------

    def _assemble_positive_prompt(
        self,
        scene_desc: str,
        substrate_data: dict[str, Any],
        lens_data: dict[str, Any],
        pressure_data: dict[str, Any],
        director_data: dict[str, Any],
        color_data: dict[str, Any],
        palette: dict[str, str],
        light_source: str,
    ) -> str:
        """组装正向提示词 (遵循 SKILL.md §11.2 结构)。

        顺序:
        1. 画幅与成像基底
        2. 具体时间、空间和人物
        3. 主要动作与未完成状态
        4. 摄影机位置、焦段、景别和构图机制
        5. 实际光源
        6. 色彩命题
        7. 真实材质与光学限制
        """
        parts: list[str] = []

        # 1. 成像基底 + 英文基底
        parts.append(ENGLISH_BASE_POSITIVE)
        parts.append(substrate_data["prompt_fragment"])

        # 2. 场景描述
        parts.append(scene_desc)

        # 3. 构图压力 (如有)
        if pressure_data.get("prompt_fragment"):
            parts.append(pressure_data["prompt_fragment"])

        # 4. 摄影机 + 焦段 + 导演调度
        parts.append(lens_data["prompt_fragment"])
        if director_data.get("prompt_snippet"):
            parts.append(director_data["prompt_snippet"])

        # 5. 光源
        parts.append(f"main light: {light_source}")

        # 6. 色彩命题
        parts.append(
            f"color: {palette['primary']} dominant, {palette['secondary']} secondary, "
            f"{palette['accent']} accent at 5-15%"
        )

        return ", ".join(parts)

    def _assemble_negative_prompt(self, scene_desc: str) -> str:
        """组装负面提示词 (SKILL.md §11.5 + §9 + v4)。"""
        parts: list[str] = [ENGLISH_BASE_NEGATIVE]

        # 追加 v4 反 AI 禁止项
        parts.extend(ANTI_AI_FORBIDDEN_TERMS)

        # 通用负面
        parts.extend([
            "no text", "no subtitles", "no watermark", "no poster layout",
            "no collage", "no split screen", "no storyboard grid",
            "no oversharpening", "no random lens flare", "no duplicated people",
            "no extra limbs", "no generic model pose", "no fake cinematic filter",
        ])

        # 根据题材追加
        desc_lower = scene_desc.lower()
        if any(kw in desc_lower for kw in ("东方", "武侠", "古代", "wuxia", "eastern", "ancient")):
            parts.append(EASTERN_EXTRA_NEGATIVES)
        if any(kw in desc_lower for kw in ("科幻", "未来", "sci", "future", "cyber")):
            parts.append(SCIFI_EXTRA_NEGATIVES)

        # 去重
        seen: set[str] = set()
        unique: list[str] = []
        for p in parts:
            if p not in seen:
                seen.add(p)
                unique.append(p)

        return ", ".join(unique)


# ===========================================================================
# 十三、便捷函数 (单例)
# ===========================================================================

_default_enhancer: CinemaPromptEnhancer | None = None


def get_enhancer() -> CinemaPromptEnhancer:
    """获取默认的 CinemaPromptEnhancer 单例实例。"""
    global _default_enhancer
    if _default_enhancer is None:
        _default_enhancer = CinemaPromptEnhancer()
    return _default_enhancer


def enhance_keyframe(
    scene_desc: str,
    shot_type: str = "medium",
    mood: str = "",
) -> dict[str, Any]:
    """便捷函数: 使用默认增强器增强关键帧提示词。"""
    return get_enhancer().enhance_keyframe_prompt(scene_desc, shot_type, mood)
