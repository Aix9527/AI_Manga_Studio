"""Prompt OS service (Phase 13.6, GPT spec).

十引擎注册表：Character / Scene / Camera / Story / Video / Voice /
QC / Compiler / Optimizer / Evolution。每个引擎有输入/输出 schema、
版本号、状态。ShotDesign 版本治理与 Character Bible v2 一致：
draft → approved → locked，新版本永远由人工审批产生。
"""

from __future__ import annotations

import json
import re
import threading
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from backend.prompt_os.compiler import PromptCompiler
from backend.prompt_os.evolution import PromptEvolution
from backend.prompt_os.knowledge_base import DNAKnowledgeBase
from backend.prompt_os.model import (
    DNAEntry,
    PromptEngine,
    SHOTDESIGN_LAYERS,
    SHOTDESIGN_STATUSES,
    ShotDesign,
)


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _new_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:10]}"


def _default_engines() -> list[PromptEngine]:
    return [
        PromptEngine(key="character", name="Character Prompt Engine", description="角色 DNA：脸/发/眼/体型/服装/配饰/声线/手势/走姿/表情/情绪",
                     input_schema={"character_id": "str", "emotion": "str"}, output_schema={"character_prompt": "str"}, status="active"),
        PromptEngine(key="scene", name="Scene Prompt Engine", description="场景与天气 DNA：雨雪雾/晨昏夜/地貌与氛围",
                     input_schema={"scene_id": "str", "weather": "str"}, output_schema={"scene_prompt": "str"}, status="active"),
        PromptEngine(key="camera", name="Camera Prompt Engine", description="镜头与焦段库：24/35/50/85/135mm，机位与角度",
                     input_schema={"shot": "str", "lens": "str"}, output_schema={"camera_prompt": "str"}, status="active"),
        PromptEngine(key="story", name="Story Prompt Engine", description="剧情层：一句话剧情 → 导演意图",
                     input_schema={"logline": "str"}, output_schema={"story_layer": "str"}, status="active"),
        PromptEngine(key="video", name="Video Prompt Engine", description="视频层：运镜/动作/时长/转场（首尾帧衔接）",
                     input_schema={"motion": "str", "movement": "str", "duration": "float"}, output_schema={"video_prompt": "str"}, status="active"),
        PromptEngine(key="voice", name="Voice Prompt Engine", description="配音层：声线/语速/情绪（角色 DNA 声线字段）",
                     input_schema={"voice": "str", "emotion": "str"}, output_schema={"voice_prompt": "str"}, status="active"),
        PromptEngine(key="qc", name="QC Prompt Engine", description="质检层：NegativeDNA 失败模式词库与一致性检查",
                     input_schema={"negative_ids": "list[str]"}, output_schema={"negative_prompt": "str"}, status="active"),
        PromptEngine(key="compiler", name="Prompt Compiler", description="一句剧情 → 八层 ShotDesign YAML",
                     input_schema={"logline": "str"}, output_schema={"shot_design": "dict"}, status="active"),
        PromptEngine(key="optimizer", name="Prompt Optimizer", description="根据 Evolution Score 建议升级方向",
                     input_schema={"score": "dict"}, output_schema={"suggestions": "dict"}, status="active"),
        PromptEngine(key="evolution", name="Prompt Evolution", description="完播/点赞/评论/收藏 → Score → 候选 → 人工审批 → 新版本",
                     input_schema={"metric": "dict"}, output_schema={"record": "dict"}, status="active"),
    ]


class PromptOS:
    """Prompt 操作系统：DNA 知识库 + Compiler + Evolution + 十引擎。"""

    def __init__(
        self,
        root: str | Path = "storage/prompt_os",
        *,
        knowledge_base: DNAKnowledgeBase | None = None,
        compiler: PromptCompiler | None = None,
        evolution: PromptEvolution | None = None,
    ):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.kb = knowledge_base or DNAKnowledgeBase(self.root / "dna.json")
        self.compiler = compiler or PromptCompiler(self.kb)
        self.evolution = evolution or PromptEvolution(self.root)
        self._lock = threading.RLock()
        self._engines: dict[str, dict] = self._load("engines.json")
        if not self._engines:
            for engine in _default_engines():
                self._engines[engine.key] = engine.to_dict()
            self._save("engines.json", self._engines)
        self._designs: dict[str, dict] = self._load("shot_designs.json")

    # ------------------------------------------------------------ io
    def _load(self, name: str) -> dict[str, dict]:
        path = self.root / name
        if not path.exists():
            return {}
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            return {}

    def _save(self, name: str, data: dict[str, dict]) -> None:
        path = self.root / name
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(path)

    # ------------------------------------------------------------ engines
    def engines(self) -> list[dict]:
        return list(self._engines.values())

    def engine(self, key: str) -> dict:
        if key not in self._engines:
            raise KeyError(f"engine not found: {key}")
        return dict(self._engines[key])

    def run_engine(self, key: str, payload: dict) -> dict:
        if key not in self._engines:
            raise KeyError(f"engine not found: {key}")
        engine = self._engines[key]
        if engine.get("status") != "active":
            raise ValueError(f"engine disabled: {key}")
        if key == "compiler":
            logline = payload.get("logline", "")
            overrides = {k: payload[k] for k in ("camera_shot", "lens", "movement", "lighting", "composition", "style", "director_intent") if k in payload}
            design = self.compiler.compile(logline, **overrides)
            saved = self.save_shot_design(design)
            return {"engine": key, "shot_design": saved}
        if key == "evolution":
            metric = dict(payload)
            return {"engine": key, "metric": self.evolution.record_metric(**metric)}
        if key == "qc":
            words = self.kb.negative_words(payload.get("negative_ids") or None)
            return {"engine": key, "negative_prompt": ", ".join(words), "count": len(words)}
        if key == "story":
            text = str(payload.get("logline", ""))
            from backend.prompt_os.compiler import _DIRECTOR_INTENT_BY_EMOTION, _EMOTION_KEYWORDS
            emotion = "awe"
            for keyword, (em, _intent, _lit) in _EMOTION_KEYWORDS.items():
                if keyword in text:
                    emotion = em
                    break
            return {"engine": key, "story_layer": text, "director_intent": _DIRECTOR_INTENT_BY_EMOTION.get(emotion, "")}
        if key == "character":
            return {"engine": key, "character_prompt": self._compose_character(payload)}
        if key == "scene":
            scene = self._pick_scene(payload.get("scene_id") or payload.get("logline", ""))
            weather = self._pick_weather(payload.get("weather") or "")
            return {"engine": key, "scene_prompt": {"scene": scene.to_dict(), "weather": weather.to_dict()}}
        if key == "camera":
            shot = payload.get("shot", "medium")
            lens = payload.get("lens", "35mm")
            lens_entry = self._pick_lens(lens)
            return {"engine": key, "camera_prompt": {"shot": shot, "lens": lens_entry.to_dict()}}
        if key == "video":
            return {"engine": key, "video_prompt": {
                "motion": payload.get("motion", "slow_walk"),
                "movement": payload.get("movement", "static"),
                "duration_seconds": payload.get("duration", 10.0),
                "transition": payload.get("transition", "match_cut"),
            }}
        if key == "voice":
            return {"engine": key, "voice_prompt": payload}
        if key == "optimizer":
            score = payload.get("score", {})
            design = self.get_shot_design(score.get("shot_design_id", "")) if score.get("shot_design_id") else None
            suggestions = self.evolution._suggest(design, score) if design else {"director_intent": "提供 score 后给出建议"}
            return {"engine": key, "suggestions": suggestions}
        raise ValueError(f"engine not implemented: {key}")

    # ------------------------------------------------------------ DNA
    def dna_all(self) -> list[dict]:
        return [entry.to_dict() for entry in self.kb.all()]

    def dna_by_kind(self, kind: str) -> list[dict]:
        return [entry.to_dict() for entry in self.kb.by_kind(kind)]

    def dna_add(self, data: dict) -> dict:
        return self.kb.add_from_dict(data).to_dict()

    def dna_stats(self) -> dict:
        return self.kb.stats()

    # ------------------------------------------------------------ ShotDesign
    def compile_shot(self, logline: str, **overrides: Any) -> dict:
        design = self.compiler.compile(logline, **overrides)
        return self.save_shot_design(design)

    def compile_sequence(self, loglines: list[str], **overrides: Any) -> list[dict]:
        designs = self.compiler.compile_sequence(loglines, **overrides)
        return [self.save_shot_design(d) for d in designs]

    def save_shot_design(self, design: ShotDesign) -> dict:
        with self._lock:
            self._designs[design.id] = design.to_dict()
            self._save("shot_designs.json", self._designs)
        return self._designs[design.id]

    def get_shot_design(self, design_id: str) -> ShotDesign | None:
        with self._lock:
            raw = self._designs.get(design_id)
        return ShotDesign.from_dict(raw) if raw else None

    def list_shot_designs(self) -> list[dict]:
        rows = list(self._designs.values())
        rows.sort(key=lambda r: r.get("created_at", ""), reverse=True)
        return rows

    def new_version(self, design_id: str, *, overrides: dict | None = None, approved_by: str = "", notes: str = "") -> dict:
        """基于已锁定版本生成新版本（不原地修改，GPT 修改建议 2 版本化管理）。"""
        with self._lock:
            raw = self._designs.get(design_id)
            if not raw:
                raise KeyError(f"shot design not found: {design_id}")
            design = ShotDesign.from_dict(raw)
            if design.status != "locked":
                raise ValueError(f"只有 locked 版本可以派生新版本，当前 {design.status}")
            new_design = ShotDesign.from_dict(raw)
            new_design.id = _new_id("SD")
            new_design.parent_version = design.version
            new_design.version = self._next_version(design.version)
            new_design.status = "draft"
            new_design.approved_by = ""
            new_design.approved_at = ""
            new_design.notes = notes or f"从 {design.version} 派生，待人工审批"
            new_design.created_at = _now()
            new_design.updated_at = _now()
            if overrides:
                for key, value in overrides.items():
                    if key == "continuity_contract" and isinstance(value, dict):
                        from backend.prompt_os.model import ContinuityContract
                        new_design.continuity_contract = ContinuityContract.from_dict(value)
                    elif key in ("layers",):
                        new_design.layers = {**new_design.layers, **value}
                    elif hasattr(new_design, key):
                        setattr(new_design, key, value)
            self._designs[new_design.id] = new_design.to_dict()
            self._save("shot_designs.json", self._designs)
        return self._designs[new_design.id]

    def _next_version(self, version: str) -> str:
        match = re.fullmatch(r"v(\d+)", version)
        if not match:
            return "v2"
        return f"v{int(match.group(1)) + 1}"

    def set_status(self, design_id: str, status: str, approved_by: str = "human") -> dict:
        if status not in SHOTDESIGN_STATUSES:
            raise ValueError(f"invalid status: {status}")
        with self._lock:
            raw = self._designs.get(design_id)
            if not raw:
                raise KeyError(f"shot design not found: {design_id}")
            design = ShotDesign.from_dict(raw)
            if status == "locked" and design.status != "approved":
                raise ValueError("locked 之前必须先 approved")
            if status == "approved" and design.status not in ("draft", "approved"):
                raise ValueError(f"approved 只能从 draft 或 approved 进入，当前 {design.status}")
            design.status = status
            if status == "approved":
                design.approved_by = approved_by
                design.approved_at = _now()
            design.updated_at = _now()
            self._designs[design_id] = design.to_dict()
            self._save("shot_designs.json", self._designs)
        return self._designs[design_id]

    # ------------------------------------------------------------ evolution
    def record_metric(self, **kwargs: Any) -> dict:
        return self.evolution.record_metric(**kwargs)

    def leaderboard(self, limit: int = 20) -> list[dict]:
        return self.evolution.leaderboard(limit=limit)

    def propose_candidates(self) -> list[dict]:
        designs = {design_id: ShotDesign.from_dict(raw) for design_id, raw in self._designs.items()}
        return self.evolution.propose_candidates(designs)

    def evolution_records(self, status: str | None = None) -> list[dict]:
        return self.evolution.list_records(status=status)

    def review_candidate(self, record_id: str, decision: str, reviewer: str = "human") -> dict:
        return self.evolution.review(record_id, decision, reviewer)

    def apply_candidate(self, record_id: str) -> dict:
        return self.evolution.apply(record_id)

    def evolution_stats(self) -> dict:
        return self.evolution.stats()

    # ------------------------------------------------------------ helpers
    def stats(self) -> dict:
        engines = self.engines()
        return {
            "engines": len(engines),
            "engines_active": sum(1 for e in engines if e.get("status") == "active"),
            "dna": self.kb.stats(),
            "shot_designs": len(self._designs),
            "evolution": self.evolution.stats(),
            "layers": SHOTDESIGN_LAYERS,
        }

    def _compose_character(self, payload: dict) -> dict:
        character_id = payload.get("character_id", "")
        entries = self.kb.by_kind("character")
        entry = None
        if character_id:
            entry = self.kb.get(character_id)
        entry = entry or (entries[0] if entries else None)
        if not entry:
            return {}
        self.kb.record_usage(entry.id)
        emotion = payload.get("emotion", "")
        data = entry.to_dict()
        if emotion:
            data["values"] = {**data.get("values", {}), "emotion_override": emotion}
        return data

    def _pick_scene(self, scene_id_or_text: str) -> DNAEntry:
        entry = self.kb.get(scene_id_or_text)
        if entry:
            return entry
        for keyword, (entry_id, _name, _mood) in [
            ("遗迹", "scene_ruins_001"), ("宫殿", "scene_palace_001"), ("都市", "scene_city_001"),
            ("山", "scene_mountain_001"),
        ]:
            if keyword in scene_id_or_text:
                found = self.kb.get(entry_id)
                if found:
                    return found
        return self.kb.by_kind("scene")[0]

    def _pick_weather(self, keyword: str) -> DNAEntry:
        for key, entry_id in [("雨", "wx_rain_001"), ("雪", "wx_snow_001"), ("雾", "wx_fog_001"),
                              ("晨", "wx_dawn_001"), ("黄昏", "wx_sunset_001"), ("夜", "wx_night_001")]:
            if key in keyword:
                found = self.kb.get(entry_id)
                if found:
                    return found
        return self.kb.by_kind("weather")[0]

    def _pick_lens(self, mm: str) -> DNAEntry:
        for lid, focal in [("lens_24_001", "24mm"), ("lens_35_001", "35mm"), ("lens_50_001", "50mm"),
                           ("lens_85_001", "85mm"), ("lens_135_001", "135mm")]:
            if focal == mm:
                found = self.kb.get(lid)
                if found:
                    return found
        return self.kb.by_kind("lens")[0]