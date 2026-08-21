# -*- coding: utf-8 -*-
"""分镜（Storyboard）驱动生产 — 将分镜 HTML/JSON 转换为生产管线数据。

用户指令：使用
  C:\\Users\\X\\AppData\\Roaming\\TRAE SOLO CN\\ModularData\\ai-agent\\work-mode-projects\\
  6a773741a73a69c9ab4e5e06\\guixu-awakening-storyboard\\guixu-awakening-storyboard.html
作为生成依据（《归墟觉醒》分镜脚本）。

职责：
  1. ``load_storyboard(path)`` —— 解析 HTML 或读取已生成的 manifest JSON
  2. ``storyboard_to_plan(...)`` —— 分镜 -> ProductionPlan（ShotSpec 列表，接入
     plan_builder / executor 主流程）
  3. ``storyboard_to_shot_dicts(...)`` —— 分镜 -> ChainRuntime 镜头配置
     （每镜 keyframe/prompt/duration/handoff_mode，配合 Spectrum H3 provider）

镜头字段映射（分镜表列 -> ShotSpec）：
  镜号      -> shot_id / shot_number
  景别      -> shot_class（establishing / dialogue / emotion_closeup /
              character_motion / action / climax / transition）
  运镜      -> camera（英文运镜描述，供 H3 prompt 使用）
  画面内容  -> description + positive_prompt（叠加 LIVE_ACTION_ANCHOR）
  台词/音效 -> dialogue / narration / sfx
  时长      -> duration（无时长标注时按 shot_class 取 Duration Policy v1 区间中值）
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from backend.production.contracts import (
    Chapter,
    InputContract,
    InputType,
    LoadedInput,
    ProductionPlan,
    ShotSpec,
)
from backend.production.plan_builder import (
    LIVE_ACTION_ANCHOR,
    NEGATIVE_PROMPT,
    _shot_motion_level,
)

logger = logging.getLogger(__name__)

# 景别 -> shot_class（用于 Duration Policy v1 时长 + H3 参考强度）
_SHOT_CLASS_BY_SHOT_SIZE = {
    "大远景": "establishing",
    "远景": "establishing",
    "全景": "establishing",
    "中景": "dialogue",
    "近景": "dialogue",
    "特写": "emotion_closeup",
    "大特写": "emotion_closeup",
    "黑场": "transition",
}
_ACTION_CLASS_KEYWORDS = (
    "动作", "混战", "打斗", "战斗", "突入", "逃", "奔跑", "追击", "开枪",
    "枪", "爆炸", "冲击波", "变形", "爆开", "甩切", "高速跳切", "升格",
)
_CLIMAX_KEYWORDS = (
    "高潮", "献祭", "牺牲", "觉醒", "爆发", "金光", "广播", "基因",
    "圣", "神", "归来", "手术", "决战",
)
_TRANSITION_KEYWORDS = (
    "转场", "黑场", "蒙太奇", "跳切", "叠化", "切", "时间流逝",
)

# 运镜中文 -> 英文描述（H3 prompt 镜头语言）
_CAMERA_MAP = {
    "推": "slow push-in camera move",
    "慢推": "slow push-in camera move",
    "拉": "slow pull-back camera move",
    "升": "crane up shot",
    "固定": "static locked-off shot",
    "摇": "panning shot",
    "慢摇": "slow panning shot",
    "移": "dolly tracking shot",
    "慢移": "slow dolly shot",
    "跟": "tracking shot, handheld",
    "环绕": "orbiting camera shot",
    "环绕定格": "orbiting shot ending on a freeze frame",
    "甩切": "fast whip-cut transition",
    "叠化": "crossfade dissolve transition",
    "跳切": "jump cut sequence",
    "高速跳切": "rapid jump cut montage",
    "升格": "slow motion (overcranked)",
    "升格环绕": "slow motion orbiting shot",
    "动画合成": "animated composite sequence",
    "切": "hard cut",
}
_DEFAULT_CAMERA = "cinematic establishing camera move"


@dataclass
class StoryboardShot:
    shot_id: str
    shot_size: str = ""          # 景别
    camera_cn: str = ""          # 运镜（中文原样）
    content: str = ""            # 画面内容（去景别/运镜/台词/时长后）
    dialogue: str = ""           # 对白/旁白原文（含角色名）
    narration: str = ""          # 旁白台词
    sfx: str = ""                # 音效提示
    duration_s: float | None = None
    shot_class: str = "dialogue"
    camera_en: str = _DEFAULT_CAMERA

    def to_dict(self) -> dict:
        return {
            "shot_id": self.shot_id,
            "shot_size": self.shot_size,
            "camera_cn": self.camera_cn,
            "camera_en": self.camera_en,
            "content": self.content,
            "dialogue": self.dialogue,
            "narration": self.narration,
            "sfx": self.sfx,
            "duration_s": self.duration_s,
            "shot_class": self.shot_class,
        }


@dataclass
class Storyboard:
    source: str = ""
    sequences: list[dict[str, Any]] = field(default_factory=list)

    def all_shots(self) -> list[StoryboardShot]:
        shots: list[StoryboardShot] = []
        for seq in self.sequences:
            for s in seq.get("shots", []):
                if isinstance(s, dict):
                    shots.append(_from_manifest_shot(s))
        return shots


# ------------------------------------------------------------- HTML 解析

def _strip_html(seg: str) -> str:
    seg = re.sub(r"<script.*?</script>", " ", seg, flags=re.S)
    seg = re.sub(r"<style.*?</style>", " ", seg, flags=re.S)
    seg = re.sub(r"<[^>]+>", " ", seg)
    seg = re.sub(r"\s+", " ", seg)
    return seg.strip()


def _parse_html_shots(plain: str) -> list[dict[str, Any]]:
    """从章节纯文本提取镜头条目（S01-1 等）。"""
    entries = re.split(r"(?=S\d+-\d+)", plain)
    shots: list[dict[str, Any]] = []
    for entry in entries:
        m = re.match(r"^(S\d+-\d+)\s+(.*)$", entry.strip())
        if not m:
            continue
        shot_id, body = m.group(1), m.group(2)
        dur_m = re.search(r"(\d+(?:\.\d+)?)\s*s\s*$", body)
        duration = float(dur_m.group(1)) if dur_m else None
        shots.append({
            "shot_id": shot_id,
            "duration_s": duration,
            "content": body.strip(),
        })
    return shots


def parse_storyboard_html(html: str) -> Storyboard:
    """从 HTML 分镜脚本解析结构化 Storyboard（可独立于 manifest 使用）。"""
    seq_markers = [(m.start(), m.group(1)) for m in re.finditer(r'id="(seq-\d+)"', html)]
    sequences: list[dict[str, Any]] = []
    for i, (pos, seq_id) in enumerate(seq_markers):
        end = seq_markers[i + 1][0] if i + 1 < len(seq_markers) else len(html)
        plain = _strip_html(html[pos:end])
        seq: dict[str, Any] = {"id": seq_id, "raw": plain, "shots": []}
        title_m = re.search(r"(?:id=\"seq-\d+\">\s*)?(S\d+)\s+(.*?)(?:\s+\d+\s*镜|\s+约\s|$)", plain)
        if title_m:
            seq["title"] = title_m.group(2).strip()
        seq["shots"] = _parse_html_shots(plain)
        sequences.append(seq)
    return Storyboard(source="html", sequences=sequences)


def load_storyboard(path: str | Path) -> Storyboard:
    """加载分镜数据：JSON manifest 优先，HTML 则直接解析。"""
    p = Path(path)
    if not p.is_file():
        raise FileNotFoundError(f"Storyboard not found: {p}")
    if p.suffix.lower() == ".json":
        data = json.loads(p.read_text(encoding="utf-8"))
        return Storyboard(
            source=str(p),
            sequences=data.get("sequences", data if isinstance(data, list) else []),
        )
    if p.suffix.lower() == ".html":
        sb = parse_storyboard_html(p.read_text(encoding="utf-8"))
        sb.source = str(p)
        return sb
    raise ValueError(f"Unsupported storyboard format: {p.suffix}")


# ------------------------------------------------------------- 镜头解析

_SHOT_SIZE_PREFIXES = tuple(sorted(_SHOT_CLASS_BY_SHOT_SIZE, key=len, reverse=True))


def _from_manifest_shot(item: dict[str, Any]) -> StoryboardShot:
    """从 manifest 镜头条目解析字段。"""
    shot_id = str(item.get("shot_id", ""))
    content = str(item.get("content", "") or item.get("raw", "") or "")
    duration = item.get("duration_s")
    duration = float(duration) if duration else None

    # 1. 去掉尾部时长 "8s"
    body = re.sub(r"\s*\d+(?:\.\d+)?\s*s\s*$", "", content).strip()

    # 2. 景别（首词）
    shot_size = ""
    rest = body
    for prefix in _SHOT_SIZE_PREFIXES:
        if body.startswith(prefix):
            shot_size = prefix
            rest = body[len(prefix):].strip()
            break
    # 3. 运镜（次词）
    camera_cn = ""
    m = re.match(r"^([\u4e00-\u9fff]{1,4})\s*", rest)
    if m and any(k in m.group(1) for k in (
        "推", "拉", "升", "固定", "摇", "移", "跟", "环绕", "甩切",
        "叠化", "跳切", "升格", "切", "动画",
    )):
        camera_cn = m.group(1)
        rest = rest[len(camera_cn):].strip()

    # 4. 台词/音效：括号注解（旁白/字幕/音效/（无对白）等）
    dialogue = ""
    narration = ""
    sfx = ""
    # 抓取"XXX："或（旁白：）形式
    lines = re.split(r"(?<=\s|\))(?=［「【]?[^。]{0,12}?[:：])", rest)
    main_parts: list[str] = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        if re.match(r"^[（(].*(旁白|字幕|对白|画外|无对白|无)。*", line):
            if "旁白" in line or "无对白" in line:
                narration = line
            else:
                sfx = f"{sfx} {line}".strip()
            continue
        if "：" in line or ":" in line:
            dialogue = f"{dialogue} {line}".strip()
        else:
            main_parts.append(line)
    description = " ".join(main_parts).strip() or rest

    shot_class = _classify_shot(shot_size, description, dialogue, shot_id)
    camera_en = _CAMERA_MAP.get(camera_cn, _DEFAULT_CAMERA)

    return StoryboardShot(
        shot_id=shot_id,
        shot_size=shot_size,
        camera_cn=camera_cn,
        content=description,
        dialogue=dialogue,
        narration=narration,
        sfx=sfx,
        duration_s=duration,
        shot_class=shot_class,
        camera_en=camera_en,
    )


def _classify_shot(shot_size: str, description: str, dialogue: str, shot_id: str) -> str:
    """推断镜头类型（用于时长/参考强度策略）。"""
    text = f"{shot_size} {description} {dialogue} {shot_id}".lower()
    if any(k in text for k in _CLIMAX_KEYWORDS):
        return "climax"
    if any(k in text for k in _ACTION_CLASS_KEYWORDS):
        return "action"
    if any(k in text for k in _TRANSITION_KEYWORDS):
        return "transition"
    return _SHOT_CLASS_BY_SHOT_SIZE.get(shot_size, "dialogue")


# ------------------------------------------------------------- 生产管线接入

def storyboard_to_plan(
    project_id: str,
    storyboard: Storyboard,
    settings: dict[str, Any] | None = None,
    max_shots: int = 0,
) -> ProductionPlan:
    """分镜 -> ProductionPlan（ShotSpec 列表）。

    settings 可包含：width/height/fps/target_seconds/max_shots。
    未标注时长的镜头按 shot_class 使用 Duration Policy v1 区间中值。
    """
    from backend.production.engine_policy import DURATION_POLICY_V1

    settings = settings or {}
    max_shots = int(max_shots or settings.get("max_shots", 0) or 0)
    shots: list[ShotSpec] = []
    shot_number = 0
    for seq in storyboard.sequences:
        for item in seq.get("shots", []):
            sb = _from_manifest_shot(item)
            shot_number += 1
            if max_shots and shot_number > max_shots:
                break

            duration = sb.duration_s
            if not duration or duration <= 0:
                lo, hi = DURATION_POLICY_V1.get(sb.shot_class, (5.0, 10.0))
                duration = max(lo, (lo + hi) / 2.0)

            # H3 竖屏 prompt：画面内容 + 运镜 + 实拍锚点
            positive = (
                f"{LIVE_ACTION_ANCHOR}, vertical cinematic composition, "
                f"{sb.camera_en}, {sb.content}"
            )
            if sb.narration and sb.narration not in positive:
                positive = f"{positive}, {sb.narration}"

            shots.append(ShotSpec(
                id=sb.shot_id,
                shot_number=shot_number,
                description=sb.content,
                duration=duration,
                camera=sb.camera_en,
                characters=_infer_characters(sb.content),
                dialogue=[sb.dialogue] if sb.dialogue else [],
                sfx=_infer_sfx(sb.sfx + sb.content),
                positive_prompt=positive,
                negative_prompt=NEGATIVE_PROMPT,
                narration=sb.narration,
                transition=_transition_for(sb.shot_class, sb.camera_cn),
                seed=_seed_for(sb.shot_id),
                motion_level=_shot_motion_level(
                    description=sb.content,
                    camera=sb.camera_en,
                    dialogue=sb.dialogue,
                    narration=sb.narration,
                ),
            ))
        if max_shots and shot_number >= max_shots:
            break

    contract = InputContract(
        path=storyboard.source or "storyboard",
        type=InputType.STORYBOARD,
        title=_storyboard_title(storyboard),
        chapter_count=len(storyboard.sequences),
        total_words=0,
        metadata={"format": "storyboard"},
    )
    chapter = Chapter(
        index=1,
        title=_storyboard_title(storyboard),
        content=_plain_storyboard_text(storyboard),
        word_count=len(_plain_storyboard_text(storyboard)),
    )
    return ProductionPlan(
        project_id=project_id,
        input_contract=contract,
        chapters=[chapter],
        shots=shots,
        total_duration=sum(s.duration for s in shots),
        settings={
            **settings,
            "source": storyboard.source,
            "storyboard_driven": True,
            "sequences": [
                {"id": seq.get("id"), "title": seq.get("title"),
                 "shot_count": len(seq.get("shots", []))}
                for seq in storyboard.sequences
            ],
        },
    )


def storyboard_to_shot_dicts(storyboard: Storyboard, max_shots: int = 0) -> list[dict]:
    """分镜 -> ChainRuntime 镜头配置列表（配合 Spectrum H3 provider 使用）。

    每镜：id / description / prompt_tail / shot_class / duration_s /
          handoff_mode / seed / motion_level。
    首帧由调用方指定（角色参考图 / 前镜尾帧 / 独立关键帧）。
    """
    shots: list[dict] = []
    for seq in storyboard.sequences:
        for item in seq.get("shots", []):
            sb = _from_manifest_shot(item)
            if max_shots and len(shots) >= max_shots:
                break
            duration = sb.duration_s
            if not duration or duration <= 0:
                from backend.production.engine_policy import DURATION_POLICY_V1
                lo, hi = DURATION_POLICY_V1.get(sb.shot_class, (5.0, 10.0))
                duration = max(lo, (lo + hi) / 2.0)
            shots.append({
                "id": sb.shot_id,
                "shot_id": sb.shot_id,
                "description": sb.content,
                "prompt_tail": (
                    f"vertical cinematic composition, {sb.camera_en}, {sb.content}"
                    + (f", {sb.narration}" if sb.narration else "")
                ),
                "shot_class": sb.shot_class,
                "duration_s": round(duration, 1),
                "handoff_mode": _handoff_mode(sb.shot_class, sb.camera_cn),
                "seed": _seed_for(sb.shot_id),
                "motion_level": _shot_motion_level(
                    description=sb.content,
                    camera=sb.camera_en,
                    dialogue=sb.dialogue,
                    narration=sb.narration,
                ),
                "scene": seq.get("id", ""),
            })
    return shots


def _handoff_mode(shot_class: str, camera_cn: str) -> str:
    if shot_class == "transition":
        return "scene_change"
    if shot_class == "action" or camera_cn in ("跟", "甩切", "高速跳切", "升格"):
        return "continuous_action"
    if camera_cn in ("叠化", "跳切", "切", "黑场"):
        return "scene_change"
    return "same_scene_reangle"


def _transition_for(shot_class: str, camera_cn: str) -> str:
    if shot_class == "transition" or camera_cn in ("叠化", "切"):
        return "dip_to_black" if camera_cn == "切" else "crossfade"
    if shot_class == "action":
        return "light_flash"
    return "fade"


def _seed_for(shot_id: str) -> int:
    m = re.search(r"-(\d+)", shot_id)
    num = int(m.group(1)) if m else 0
    return 20260801 + num * 7919


def _infer_characters(content: str) -> list[str]:
    known = ("苏晚", "方觉明", "陈夜", "赵一鸣", "苏小满", "白砚行", "陈姐", "林远舟")
    return [name for name in known if name in content]


def _infer_sfx(text: str) -> list[str]:
    mapping = (
        (("枪", "警报", "爆炸", "震"), "impact"),
        (("列车", "铁", "金属"), "train"),
        (("风", "雨", "雷"), "wind"),
        (("脚步", "奔跑"), "footsteps"),
        (("心跳", "呼吸"), "heartbeat"),
    )
    return [sound for keywords, sound in mapping if any(k in text for k in keywords)]


def _storyboard_title(storyboard: Storyboard) -> str:
    for seq in storyboard.sequences:
        if seq.get("title"):
            m = re.match(r"^(.*?)[·．.]?\s*(第[一二三四五六七八九十]章)?", seq["title"])
            if m and m.group(1):
                return m.group(1).strip()
    return "归墟觉醒"


def _plain_storyboard_text(storyboard: Storyboard) -> str:
    parts = []
    for seq in storyboard.sequences:
        parts.append(seq.get("raw", ""))
    return "\n".join(parts)
