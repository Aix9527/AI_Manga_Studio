"""Chinese Name Extraction with multi-strategy fusion.

Strategy 1: jieba POS tagging for person names (nr tag)
Strategy 2: Title/role association — 少年/少女/师父/黑衣人 → entity linking
Strategy 3: Frequency-based rare word detection for novel-specific names
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field
from typing import Optional

import jieba
import jieba.posseg as pseg


@dataclass
class ChineseCharacter:
    """Extracted Chinese character entity."""
    name: str
    name_type: str = "person"          # person, title_role, ambiguous
    aliases: list[str] = field(default_factory=list)
    frequency: int = 0
    associated_actions: list[str] = field(default_factory=list)
    associated_emotions: list[str] = field(default_factory=list)
    pronouns: list[str] = field(default_factory=list)  # 他/她/其


class ChineseExtractor:
    """Multi-strategy Chinese character name extractor."""

    # Common Chinese surnames for dictionary augmentation
    SURNAMES: set[str] = {
        "林", "苏", "王", "李", "张", "刘", "陈", "杨", "赵", "黄",
        "周", "吴", "徐", "孙", "胡", "朱", "高", "林", "何", "郭",
        "马", "罗", "梁", "宋", "郑", "谢", "韩", "唐", "冯", "于",
        "叶", "萧", "程", "曹", "袁", "邓", "许", "傅", "沈", "曾",
        "彭", "吕", "苏", "卢", "蒋", "蔡", "贾", "丁", "魏", "薛",
        "慕容", "欧阳", "东方", "独孤", "令狐", "司马", "上官", "端木",
    }

    # Title/role words that indicate a character but aren't proper names
    TITLE_ROLES: dict[str, str] = {
        "少年": "youth_male", "少女": "youth_female",
        "青年": "young_man", "女子": "young_woman",
        "中年男子": "middle_aged_man", "中年女子": "middle_aged_woman",
        "老者": "elder", "老人": "elder",
        "师父": "master", "师傅": "master",
        "长老": "elder_council", "掌门": "sect_leader",
        "黑衣人": "mysterious_antagonist", "蒙面人": "masked_figure",
        "剑客": "swordsman", "刀客": "blade_wielder",
        "将军": "general", "士兵": "soldier",
        "王子": "prince", "公主": "princess",
        "皇帝": "emperor", "皇后": "empress",
        "道士": "taoist", "和尚": "monk",
        "刺客": "assassin", "杀手": "hitman",
        "商人": "merchant", "书生": "scholar",
        "侍女": "maid", "侍卫": "guard",
        "妖怪": "monster", "妖魔": "demon",
        "星兽": "star_beast",
    }

    # Action verbs for character behavior tracking
    ACTION_VERBS: set[str] = {
        "拔剑", "握拳", "流泪", "微笑", "苦笑", "冷笑", "怒吼",
        "冲锋", "后退", "跃起", "落下", "转身", "回头", "抬头",
        "低头", "凝视", "闭眼", "睁眼", "叹气", "喘息", "颤抖",
        "跪倒", "站起", "坐下", "奔跑", "行走", "站立", "蹲下",
        "挥拳", "踢腿", "刺出", "斩下", "格挡", "闪避", "追击",
        "施法", "念咒", "结印", "召唤", "封印", "释放",
        "抓住", "推开", "拉起", "扑倒", "撞上", "摔倒",
    }

    # Emotion indicators
    EMOTION_KEYWORDS: dict[str, str] = {
        "愤怒": "anger", "狂怒": "rage", "怒气": "anger",
        "悲伤": "sadness", "痛苦": "pain", "绝望": "despair",
        "恐惧": "fear", "害怕": "fear", "惊恐": "terror",
        "喜悦": "joy", "兴奋": "excitement", "惊喜": "surprise",
        "冷静": "calm", "冰冷": "cold", "淡漠": "indifferent",
        "温柔": "gentle", "温柔": "tenderness",
        "紧张": "tense", "焦虑": "anxiety",
        "坚定": "determined", "决然": "resolute",
        "孤独": "loneliness", "寂寞": "loneliness",
        "思念": "longing", "怀念": "nostalgia",
    }

    def __init__(self):
        # Augment jieba dictionary with common surnames
        for surname in self.SURNAMES:
            jieba.add_word(surname, freq=1000, tag="nr")
        # Add common two-character given names
        common_given = [
            "明月", "清风", "流云", "飞雪", "残月", "龙吟",
            "剑心", "风云", "天羽", "璃月", "雪落", "寒霜",
            "无痕", "逍遥", "灵犀", "凤歌", "云逸", "霜华",
        ]
        for name in common_given:
            jieba.add_word(name, freq=500, tag="nr")

    def extract(self, text: str) -> list[ChineseCharacter]:
        """Full extraction pipeline. Returns deduplicated character list."""
        # Strategy 1: jieba POS tagging + context validation
        pos_names = self._extract_pos_names(text)
        # Strategy 2: title/role association
        title_chars = self._extract_title_roles(text)
        # Strategy 3: surname pattern + strong person context
        pattern_names = self._extract_name_patterns(text)

        # Merge and deduplicate, applying context validation
        all_chars: dict[str, ChineseCharacter] = {}

        for name in pos_names:
            if self._is_probable_person(name, text):
                all_chars[name] = ChineseCharacter(name=name, name_type="person")

        for tc in title_chars:
            if tc.name not in all_chars:
                all_chars[tc.name] = tc

        for name in pattern_names:
            if name not in all_chars and self._is_probable_person(name, text):
                all_chars[name] = ChineseCharacter(name=name, name_type="person")

        # Enrich: frequency, actions, emotions
        for ch in all_chars.values():
            ch.frequency = text.count(ch.name)
            ch.associated_actions = self._extract_actions(text, ch.name)
            ch.associated_emotions = self._extract_emotions(text, ch.name)
            ch.pronouns = self._extract_pronouns(text, ch.name)

        # Filter: keep only characters with sufficient presence
        result = [c for c in all_chars.values() if c.frequency >= 2]
        result.sort(key=lambda c: c.frequency, reverse=True)
        return result

    def extract_names(self, text: str) -> list[str]:
        """Convenience: return just name strings, compatible with CharacterExtractor interface."""
        chars = self.extract(text)
        return [c.name for c in chars]

    def _is_probable_person(self, name: str, text: str) -> bool:
        """Validate that a candidate name is likely a person, not a building/object/concept.

        Checks:
        - Name appears in sentences with person indicators (他/她, speech verbs, action verbs, emotions)
        - Name is NOT in common non-person contexts (building markers, object markers)
        - Requires strictly more person context than non-person context
        """
        non_person_markers = {"顶部", "底部", "内部", "外部", "之上", "之下", "窗口",
                              "楼层", "墙壁", "大门", "建筑", "塔顶", "塔尖", "之上",
                              "轰鸣", "倒塌", "碎裂", "倒塌", "耸立", "城墙", "街道"}
        # Also check: if name itself is a known non-person word
        known_non_person = {"钟塔", "高塔", "古塔", "星辰", "明月", "清风", "天空", "大地"}
        person_markers = {"他", "她", "说道", "心想", "看着", "转身", "眼中", "脸上",
                          "手中", "点头", "摇头", "开口", "站", "走", "跑", "说", "道",
                          "喊道", "问道", "怒吼", "冷笑", "微笑", "流泪", "颤抖",
                          "握拳", "拔剑", "抬头", "低头", "凝视", "闭眼", "睁眼",
                          "感到", "觉得", "心中", "内心", "身后", "身旁", "身边",
                          "望着", "盯着", "摸着", "握着", "跪", "抱", "推", "拉",
                          "看着她", "看着他", "对她", "对他"}

        sentences = re.split(r'[。！？\n]', text)
        person_score = 0
        non_person_score = 0

        # Immediate reject: known non-person words
        if name in known_non_person:
            return False

        for sent in sentences:
            if name not in sent:
                continue

            for marker in non_person_markers:
                if marker in sent:
                    non_person_score += 1

            for marker in person_markers:
                if marker in sent:
                    person_score += 1

        # Must have strictly more person indicators, and at least 2
        if non_person_score >= person_score:
            return False
        return person_score >= 2

    def _extract_pos_names(self, text: str) -> set[str]:
        """Strategy 1: jieba POS tagging for nr (person name) tags."""
        words = pseg.cut(text)
        names: set[str] = set()
        for word, flag in words:
            if flag == "nr" and len(word) >= 2:
                names.add(word)
        return names

    def _extract_title_roles(self, text: str) -> list[ChineseCharacter]:
        """Strategy 2: Find title/role descriptors and create character entities."""
        chars: list[ChineseCharacter] = []
        for title, role_type in self.TITLE_ROLES.items():
            if title in text:
                chars.append(ChineseCharacter(
                    name=title,
                    name_type="title_role",
                ))
        return chars

    def _extract_name_patterns(self, text: str) -> set[str]:
        """Strategy 3: Surname(1-2char) + Given(1-2char) pattern.

        Uses non-greedy matching first, then frequency analysis to resolve
        ambiguous boundaries (e.g., "苏璃抱" → prefer "苏璃" over "苏璃抱").
        """
        surname_pattern = "|".join(re.escape(s) for s in self.SURNAMES)

        # Match all surname+1char and surname+2char patterns
        pat_1 = re.compile(rf"({surname_pattern})([\u4e00-\u9fff])")
        pat_2 = re.compile(rf"({surname_pattern})([\u4e00-\u9fff]{{2}})")

        # Collect all raw matches with positions
        matches_1: dict[str, int] = Counter()
        matches_2: dict[str, int] = Counter()

        for m in pat_1.finditer(text):
            matches_1[m.group(0)] += 1
        for m in pat_2.finditer(text):
            matches_2[m.group(0)] += 1

        # Resolve: for each 3-char (surname+2), check if its 2-char prefix also exists.
        # If the 2-char prefix is more frequent, prefer it.
        resolved: dict[str, int] = {}

        # First pass: add all 2-char candidates
        for name, count in matches_1.items():
            resolved[name] = count

        # Second pass: for each 3-char candidate, decide whether to keep it
        for name, count in matches_2.items():
            prefix = name[:2]  # surname + 1 char given
            if prefix in resolved and resolved[prefix] >= count:
                # 2-char prefix is more frequent — merge counts into prefix
                resolved[prefix] += count
            elif self._given_name_valid(name):
                # 3-char is the actual name (or no competing 2-char prefix)
                resolved[name] = count

        # Filter and validate
        stop_given = {"我们", "他们", "你们", "可以", "什么", "怎么", "这个", "那个",
                      "已经", "没有", "自己", "知道", "起来", "出来", "过来",
                      "一定", "但是", "虽然", "因为", "所以", "如果", "而且",
                      "开始", "不过", "之后", "以后", "时候", "然后", "然"}

        non_person = {"星辰", "明月", "清风", "流云", "飞雪", "残月", "龙吟",
                      "风云", "天羽", "夜辰", "雪落", "寒霜", "逍遥", "无痕",
                      "灵犀", "凤歌", "云逸", "霜华", "天空", "大地", "世界",
                      "钟塔", "高塔", "古塔"}

        person_context = {"他", "她", "说道", "心想", "看着", "站", "走", "说", "道",
                         "点头", "摇头", "开口", "转身", "眼中", "脸上", "手中",
                         "握着", "抱着", "拿着", "望着", "盯着"}

        result: set[str] = set()
        for name, count in resolved.items():
            if count < 2:
                continue
            if name in non_person:
                continue

            # Validate given name part
            m = re.match(rf"^({surname_pattern})", name)
            if not m:
                continue
            given_part = name[m.end():]
            if given_part in stop_given or len(given_part) == 0:
                continue

            # Context validation
            sentences = re.split(r'[。！？\n]', text)
            valid_context = 0
            for sent in sentences:
                if name in sent:
                    for ctx in person_context:
                        if ctx in sent:
                            valid_context += 1
                            break
            if valid_context >= 1:
                result.add(name)

        return result

    @staticmethod
    def _given_name_valid(full_name: str) -> bool:
        """Quick check: the last character of a 3-char name candidate
        shouldn't be a common verb or function word."""
        if len(full_name) < 3:
            return True
        last = full_name[-1]
        invalid_lasts = {"看", "说", "道", "站", "走", "跑", "喊", "叫", "问",
                         "想", "笑", "哭", "坐", "躺", "跪", "打", "杀", "砍",
                         "飞", "跳", "落", "倒", "退", "进", "出", "来", "去",
                         "在", "是", "有", "让", "把", "将", "被", "给", "向",
                         "跟", "对", "从", "到", "着", "了", "过", "的", "得",
                         "抱", "拿", "推", "拉", "摸", "抓", "拍", "踢",
                         "闻", "听", "见", "望", "盯", "瞪", "瞄"}
        return last not in invalid_lasts

    def _extract_actions(self, text: str, name: str) -> list[str]:
        """Find action verbs associated with a character."""
        actions = []
        # Find sentences containing both name and action
        sentences = re.split(r'[。！？\n]+', text)
        for sent in sentences:
            if name in sent:
                for verb in self.ACTION_VERBS:
                    if verb in sent:
                        actions.append(verb)
        return list(set(actions))

    def _extract_emotions(self, text: str, name: str) -> list[str]:
        """Find emotion keywords near character mentions."""
        emotions = []
        sentences = re.split(r'[。！？\n]+', text)
        for sent in sentences:
            if name in sent:
                for keyword, emotion_en in self.EMOTION_KEYWORDS.items():
                    if keyword in sent:
                        emotions.append(f"{keyword}({emotion_en})")
        return list(set(emotions))

    def _extract_pronouns(self, text: str, name: str) -> list[str]:
        """Detect which pronouns refer to this character (heuristic)."""
        pronouns = []
        sentences = re.split(r'[。！？\n]+', text)
        for i, sent in enumerate(sentences):
            if name in sent and i + 1 < len(sentences):
                next_sent = sentences[i + 1]
                for p in ["他", "她", "其"]:
                    if p in next_sent:
                        pronouns.append(p)
        return list(set(pronouns))

    def get_character_summary(self, text: str) -> list[dict]:
        """Return structured dict for Director consumption."""
        chars = self.extract(text)
        return [
            {
                "name": ch.name,
                "type": ch.name_type,
                "frequency": ch.frequency,
                "aliases": ch.aliases,
                "actions": ch.associated_actions,
                "emotions": ch.associated_emotions,
                "pronouns": ch.pronouns,
            }
            for ch in chars
        ]
