"""
Structured Script Parser for AI Manga Studio

Handles pre-formatted shooting scripts (X.txt format) directly,
bypassing LLM-based AIDirector.

Format markers:
  📍 第X集 / ## 第X章  → chapter boundaries
  【场景】→ location, time, interior/exterior, camera
  【画面】→ visual description → background
  【动作】→ character action
  【台词】→ character dialogue (multi-line, parenthetical)
  【音效】→ sound effects
  【特效】→ visual effects
  核心人物：→ character definitions
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple


# ============================================================
# Data Models
# ============================================================

@dataclass
class StructuredCharacter:
    name: str
    role: str = ""
    age: int = 0
    traits: List[str] = field(default_factory=list)
    description: str = ""


@dataclass
class StructuredShot:
    index: int
    chapter_title: str = ""
    location: str = ""
    time_of_day: str = "noon"
    interior_exterior: str = "内"
    camera: str = "medium"
    camera_angle: str = ""
    camera_motion: str = ""
    scene_description: str = ""
    action: str = ""
    dialogue: str = ""
    characters_present: List[str] = field(default_factory=list)
    emotion: str = "neutral"
    sfx: str = ""
    bgm: str = ""
    vfx: str = ""
    duration: float = 3.0


@dataclass
class StructuredChapter:
    index: int
    title: str = ""
    shots: List[StructuredShot] = field(default_factory=list)


@dataclass
class StructuredScript:
    title: str = ""
    characters: Dict[str, StructuredCharacter] = field(default_factory=dict)
    chapters: List[StructuredChapter] = field(default_factory=list)
    total_shots: int = 0


# ============================================================
# Parser
# ============================================================

class ScriptParser:

    CHAPTER_RE = re.compile(r'(?:📍|##)\s*第\s*(\d+)\s*[集章]\s*(.*)')
    SCENE_RE = re.compile(r'【场景】\s*(.*)')
    VISUAL_RE = re.compile(r'【画面】\s*(.*)')
    ACTION_RE = re.compile(r'【动作】\s*(.*)')
    DIALOGUE_RE = re.compile(r'【台词】\s*')
    SFX_RE = re.compile(r'【音效】\s*(.*)')
    VFX_RE = re.compile(r'【特效】\s*(.*)')

    TIME_MAP = {
        "夜": "night", "夜间": "night", "夜晚": "night",
        "日": "day", "白天": "day",
        "黄昏": "dusk", "傍晚": "dusk",
        "清晨": "dawn", "早晨": "morning",
    }

    # ── Character extraction ──────────────────────────────
    # Matches: 林云（男主，23岁，顶尖电竞选手，四世重生，冷漠果断）
    CHAR_LINE_RE = re.compile(r'(\S+)\s*[（(]\s*(.+?)\s*[)）]')

    # ── Camera extraction from scene header ──────────────
    # Matches: 机位：特写推近 | 机位：低角度仰拍对峙 | 机位：环绕打斗，爆炸特效
    CAMERA_RE = re.compile(r'[|｜]\s*机位\s*[：:]\s*([^|｜\n]*)')

    # ── Inline scene header detection ────────────────────
    # Matches lines like: 林云家卫生间（夜，内）| 机位：特写推近
    # or: 天极公会总部·会长办公室（日，内）| 机位：低角度仰拍对峙
    INLINE_SCENE_RE = re.compile(
        r'(.*?)\s*[（(]\s*(夜|夜间|夜晚|日|白天|黄昏|傍晚|清晨|早晨)\s*[，,]\s*(内|外)\s*[）)]'
    )

    # ── Dialogue line patterns ───────────────────────────
    # 雷刚（假笑搓手）：“云神，你快坐，关于那个S级天赋，其实……”
    # （林云内心独白）“第一世，我拼死拿世界冠军；..."
    # 林云：“抽取。”
    DIALOG_LINE_RE = re.compile(
        r'[（(]?(\S+?)(?:内心独白)?[）)]?\s*[：:]\s*[""「『""]([^""」『""]+)[""」『""]'
    )

    def parse(self, text: str) -> StructuredScript:
        script = StructuredScript()
        script.title = self._extract_title(text)
        script.characters = self._extract_characters(text)

        # Split chapters at 📍 markers
        chapters_raw = self._split_chapters(text)

        for ch_idx, (ch_title, ch_text) in enumerate(chapters_raw):
            shots = self._parse_chapter_shots(ch_text, ch_idx + 1, ch_title)
            if not shots:
                continue  # skip empty chapters (prologue, character list, etc.)
            chapter = StructuredChapter(
                index=ch_idx + 1,
                title=ch_title,
                shots=shots,
            )
            script.chapters.append(chapter)
            script.total_shots += len(shots)

        return script

    # -------------------------------------------------------
    # Internal
    # -------------------------------------------------------

    def _extract_title(self, text: str) -> str:
        for line in text.split("\n")[:5]:
            line = line.strip()
            if "剧本" in line:
                return line
        return "Untitled"

    def _extract_characters(self, text: str) -> Dict[str, StructuredCharacter]:
        chars: Dict[str, StructuredCharacter] = {}

        # Locate character block
        char_start = text.find("核心人物")
        if char_start < 0:
            return chars

        # Find end — first chapter marker or empty block
        char_end = text.find("📍", char_start)
        if char_end < 0:
            char_end = text.find("##", char_start)
        if char_end < 0:
            char_end = len(text)

        block = text[char_start:char_end]

        # Parse each character definition line
        for line in block.split("\n"):
            line = line.strip()
            if not line or line.startswith("核心人物"):
                continue

            # Try full pattern: 林云（男主，23岁，顶尖电竞选手，四世重生，冷漠果断）
            m = re.match(r'(\S+)\s*[（(]\s*(.+?)\s*[）)]', line)
            if not m:
                continue

            name = m.group(1).strip()
            if len(name) > 10 or name in ("核心人物",):
                continue

            inner = m.group(2).strip()
            parts = [p.strip() for p in inner.replace("，", ",").split(",") if p.strip()]

            role = parts[0] if parts else ""
            age = 0
            trait_start = 0

            # Try extract age
            for i, p in enumerate(parts):
                age_match = re.match(r'(\d+)\s*岁', p)
                if age_match:
                    age = int(age_match.group(1))
                    trait_start = i + 1
                    break

            traits = parts[trait_start:] if trait_start > 0 else parts[1:] if len(parts) > 1 else []

            chars[name] = StructuredCharacter(
                name=name,
                role=role,
                age=age,
                traits=traits,
                description=inner,
            )

        return chars

    def _split_chapters(self, text: str) -> List[Tuple[str, str]]:
        """Split text at 📍 chapter markers. Returns [(title, text), ...]."""
        lines = text.split("\n")
        chapters: List[Tuple[str, str]] = []
        current_title = "Prologue"
        current_start = 0

        for i, line in enumerate(lines):
            m = self.CHAPTER_RE.match(line.strip())
            if m:
                # Save previous chapter
                if i > current_start:
                    chapters.append((current_title, "\n".join(lines[current_start:i])))
                current_title = m.group(2).strip() or f"第{m.group(1)}集"
                current_start = i

        # Last chapter
        if current_start < len(lines):
            chapters.append((current_title, "\n".join(lines[current_start:])))

        return chapters

    def _parse_chapter_shots(
        self,
        ch_text: str,
        ch_idx: int,
        ch_title: str,
    ) -> List[StructuredShot]:
        """Parse a single chapter into shots.

        Each 【场景】/【画面】 block starts a new shot.
        """
        shots: List[StructuredShot] = []
        lines = ch_text.split("\n")

        current: Optional[StructuredShot] = None
        in_dialogue_block = False
        dialogue_lines: List[str] = []

        for line in lines:
            line_stripped = line.strip()
            if not line_stripped:
                continue

            # Chapter marker — skip
            if self.CHAPTER_RE.match(line_stripped):
                continue

            # ── Scene starts new shot ──
            scene_m = self.SCENE_RE.match(line_stripped)

            if scene_m:
                # Flush previous shot
                if current:
                    if dialogue_lines:
                        current.dialogue = "\n".join(dialogue_lines)
                        dialogue_lines = []
                    shots.append(current)

                location, tod, ie, cam, cam_motion, cam_angle = self._parse_scene_header(scene_m.group(1))

                current = StructuredShot(
                    index=len(shots) + 1,
                    chapter_title=ch_title,
                    location=location,
                    time_of_day=tod,
                    interior_exterior=ie,
                    camera=cam,
                    camera_motion=cam_motion,
                    camera_angle=cam_angle,
                )
                continue

            # ── Inline scene header (no 【场景】 marker) ──
            # Lines like: 林云家卫生间（夜，内）| 机位：特写推近
            inline_m = self.INLINE_SCENE_RE.match(line_stripped)
            if inline_m and current is None and not any(
                ch in line_stripped for ch in ('"', '\u201c', '\u201d', '：', ':“', '：【')
            ):
                # Flush previous shot if any
                if current:
                    if dialogue_lines:
                        current.dialogue = "\n".join(dialogue_lines)
                        dialogue_lines = []
                    shots.append(current)

                full = line_stripped
                location, tod, ie, cam, cam_motion, cam_angle = self._parse_scene_header(full)

                current = StructuredShot(
                    index=len(shots) + 1,
                    chapter_title=ch_title,
                    location=location,
                    time_of_day=tod,
                    interior_exterior=ie,
                    camera=cam,
                    camera_motion=cam_motion,
                    camera_angle=cam_angle,
                )
                continue

            # ── Visual: populate scene description on current shot ──
            visual_m = self.VISUAL_RE.match(line_stripped)
            if visual_m and current is not None:
                current.scene_description = visual_m.group(1)
                continue

            if current is None:
                continue

            # ── Dialogue block ──
            if self.DIALOGUE_RE.match(line_stripped):
                in_dialogue_block = True
                dialogue_lines = []
                continue

            if in_dialogue_block:
                # Check if next section starts
                if any(re.match(p, line_stripped) for p in [
                    r'【场景】', r'【画面】', r'【动作】', r'【音效】', r'【特效】',
                ]) or self.CHAPTER_RE.match(line_stripped):
                    # End dialogue block, flush and reprocess this line
                    if dialogue_lines:
                        current.dialogue = "\n".join(dialogue_lines)
                        dialogue_lines = []
                    in_dialogue_block = False
                    # Reprocess this line
                    if self.ACTION_RE.match(line_stripped):
                        current.action += ("\n" + self.ACTION_RE.match(line_stripped).group(1)).strip()
                    elif self.SFX_RE.match(line_stripped):
                        current.sfx = self.SFX_RE.match(line_stripped).group(1)
                    elif self.VFX_RE.match(line_stripped):
                        current.vfx = self.VFX_RE.match(line_stripped).group(1)
                    continue
                else:
                    dialogue_lines.append(line_stripped)
                    continue

            # ── Action ──
            m = self.ACTION_RE.match(line_stripped)
            if m:
                current.action = m.group(1)
                continue

            # ── SFX ──
            m = self.SFX_RE.match(line_stripped)
            if m:
                current.sfx = m.group(1)
                # Detect BGM
                if "BGM" in current.sfx or "bgm" in current.sfx.lower():
                    current.bgm = current.sfx
                continue

            # ── VFX ──
            m = self.VFX_RE.match(line_stripped)
            if m:
                current.vfx = m.group(1)
                continue

        # Flush last shot
        if current:
            if dialogue_lines:
                current.dialogue = "\n".join(dialogue_lines)
            shots.append(current)

        # ── Post-process: extract characters and duration ──
        for shot in shots:
            self._extract_characters_from_dialogue(shot)
            self._estimate_duration(shot)

        return shots

    def _parse_scene_header(self, text: str) -> Tuple[str, str, str, str, str, str]:
        """Parse: 林云家卫生间（夜，内）| 机位：特写推近

        Returns (location, time_of_day, interior_exterior, camera, motion, angle)
        """
        location = text
        time_of_day = "noon"
        interior_exterior = "内"
        camera = "medium"
        cam_motion = ""
        cam_angle = ""

        # Split on | for camera
        cam_part = ""
        if "|" in text or "｜" in text:
            parts = re.split(r'[|｜]', text, maxsplit=1)
            location = parts[0].strip()
            cam_part = parts[1].strip() if len(parts) > 1 else ""

        # Parse camera from the | part
        if cam_part:
            cam_m = re.match(r'机位\s*[：:]\s*(.+)', cam_part)
            if cam_m:
                cam_text = cam_m.group(1).strip()
                camera, cam_motion, cam_angle = self._classify_camera(cam_text)

        # Parse (time, interior/exterior) from location
        paren_m = re.search(r'[（(]\s*(夜|夜间|夜晚|日|白天|黄昏|傍晚|清晨|早晨)\s*[，,]\s*(内|外)\s*[）)]', location)
        if paren_m:
            raw_time = paren_m.group(1)
            time_of_day = self.TIME_MAP.get(raw_time, "noon")
            interior_exterior = paren_m.group(2)
            # Remove parenthetical from location
            location = re.sub(r'\s*[（(]\s*\S+\s*[，,]\s*\S+\s*[）)]', '', location).strip()

        return location, time_of_day, interior_exterior, camera, cam_motion, cam_angle

    def _classify_camera(self, text: str) -> Tuple[str, str, str]:
        """Classify camera description into (type, motion, angle)."""
        cam = "medium"
        motion = ""
        angle = ""

        if any(w in text for w in ["特写", "近景"]):
            cam = "close"
        elif any(w in text for w in ["中景"]):
            cam = "medium"
        elif any(w in text for w in ["远景", "全景", "广角", "大远景", "播报视角"]):
            cam = "wide"
        elif any(w in text for w in ["鸟瞰", "航拍"]):
            cam = "drone"
        elif any(w in text for w in ["POV", "主观"]):
            cam = "pov"

        if "推" in text:
            motion = "push_in"
        elif "拉" in text:
            motion = "pull_out"
        elif "摇" in text:
            motion = "pan"
        elif "环绕" in text:
            motion = "orbit"
        elif "快切" in text:
            motion = "fast_cut"

        if "仰" in text:
            angle = "low_angle"
        elif "俯" in text:
            angle = "high_angle"
        elif "平" in text:
            angle = "eye_level"

        return cam, motion, angle

    def _extract_characters_from_dialogue(self, shot: StructuredShot) -> None:
        """Extract character names from dialogue lines.

        Handles:
          雷刚（假笑搓手）：“云神，你快坐...”
          林云：“抽取。”
          （林云内心独白）“第一世，我拼死...”
          全员：“干翻真神！”
        """
        seen: set = set(shot.characters_present)

        if not shot.dialogue:
            return

        # Known non-character speakers
        non_characters = {"系统公告", "系统音", "女皇NPC", "排队玩家", "全员",
                         "内容", "字体设计", "全服沉默"}

        for line in shot.dialogue.split("\n"):
            line = line.strip()
            if not line:
                continue

            # Pattern A: （角色名<optional tone>）"..."
            # Lazy capture of name, then explicit tone keyword list as delimiter
            TONE_WORDS = (
                r"内心独白|冷笑一声|冷笑|假笑|惊喜|愤怒|悲伤|无奈|淡然|平静|微笑|轻叹|"
                r"苦笑|吼道|笑道|惊道|怒道|冷声|不屑|得意|惊讶|疑惑|嘲讽|哭腔|"
                r"虚弱|搓手|咆哮|暴怒|咬牙|冷哼|轻声|严肃|叹气|呢喃|嘀咕|嘶吼|"
                r"颤声|媚笑|憨笑|窃笑|讪笑|暗笑|感慨|长叹|低语|怒吼|厉喝|感叹|"
                r"杀意|漠然|讥讽|大笑|浅笑|狂喜|骇然|哭喊|淡定|苦涩|恍惚|愤然|"
                r"寒声|阴笑|狂笑|惨笑|呻吟|自语|喃喃|急道|慢声|质问|反问|"
                r"紧张|忐忑|嫉妒|鄙夷|怜悯|热泪|哽咽|沉吟"
            )
            m = re.match(
                rf'[（(]\s*(\S+?)\s*(?:{TONE_WORDS})?\s*[）)]\s*["\u201c「『]', line
            )
            if m:
                name = m.group(1).strip()
                if name and len(name) <= 6 and name not in non_characters:
                    seen.add(name)
                continue

            # Pattern B: 角色名（tone...）：“...”
            # Captures name before （tone）then ：
            m = re.match(r'([^\s（(]+)\s*[（(][^）)]*[）)]?\s*[：:]', line)
            if m:
                name = m.group(1).strip()
                if name and len(name) <= 6 and name not in non_characters:
                    seen.add(name)
                continue

            # Pattern C: 角色名：“...”
            m = re.match(r'([^\s（(]+)\s*[：:]\s*["\u201c「『]', line)
            if m:
                name = m.group(1).strip()
                if name and len(name) <= 6 and name not in non_characters:
                    seen.add(name)

        shot.characters_present = list(seen)

    def _estimate_duration(self, shot: StructuredShot) -> None:
        """Estimate shot duration from dialogue length."""
        base = 3.0
        if shot.dialogue:
            # Chinese: ~3 chars/sec
            extra = len(shot.dialogue) * 0.2
            base = max(2.0, extra)
        shot.duration = min(base, 15.0)  # cap at 15s
