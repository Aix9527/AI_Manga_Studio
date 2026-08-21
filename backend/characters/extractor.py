"""Character extraction from novel text / chapter content.

Sprint 8.0: Added Chinese NLP layer integration. When text is primarily Chinese,
routes to ChineseExtractor for name detection.
"""

from __future__ import annotations

import re
from typing import Optional

from backend.characters.models import (
    Character,
    Appearance, FaceAppearance, BodyAppearance, HairAppearance,
    Personality, CombatStyle,
)


def _is_chinese_text(text: str) -> bool:
    """Detect if text is primarily Chinese."""
    cjk = sum(1 for c in text if '\u4e00' <= c <= '\u9fff')
    total = len(text.strip()) or 1
    return cjk / total > 0.3


class CharacterExtractor:
    """Extracts structured character data from prose text using heuristics + LLM pipeline.
    Sprint 8.0: Automatically routes Chinese text to ChineseExtractor."""

    # Known descriptors for heuristic extraction
    GENDER_INDICATORS = {
        "male": ["he", "him", "his", "man", "boy", "male", "prince", "king", "son", "brother", "father", "sir", "lord", "mr."],
        "female": ["she", "her", "hers", "woman", "girl", "female", "princess", "queen", "daughter", "sister", "mother", "lady", "mrs.", "ms."],
    }

    ROLE_KEYWORDS = {
        "protagonist": ["main character", "hero", "protagonist", "lead"],
        "antagonist": ["villain", "antagonist", "enemy", "foe", "nemesis"],
        "mentor": ["mentor", "teacher", "master", "guide", "sage"],
        "supporting": ["friend", "ally", "companion", "sidekick", "partner"],
    }

    def extract_names(self, text: str) -> list[str]:
        """Extract potential character names.
        Routes Chinese text to NLP layer (Sprint 8.0)."""
        if _is_chinese_text(text):
            from backend.nlp.chinese_ner import ChineseExtractor
            return ChineseExtractor().extract_names(text)

        # Pattern: 2-3 capitalized words in running text
        name_pattern = re.compile(r'(?:^|(?<=[.!?]\s))([A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,2})(?=\s)')
        names = name_pattern.findall(text)

        # Also catch single-word names mentioned frequently
        single_names = re.findall(r'(?<=["\s])([A-Z][a-z]{2,})(?=["\s,])', text)
        name_counts: dict = {}
        for n in single_names:
            if len(n) >= 3 and n.lower() not in {"the", "and", "but", "that", "with", "from", "this", "they", "their", "them", "then", "when", "where"}:
                name_counts[n] = name_counts.get(n, 0) + 1

        frequent_names = [n for n, c in name_counts.items() if c >= 3]
        all_names = list(set(names + frequent_names))
        return sorted(all_names)

    def guess_gender(self, name: str, text: str) -> str:
        """Heuristic gender guess based on surrounding pronouns."""
        # Find sentences containing the name
        sentences = re.split(r'[.!?]+', text)
        relevant = [s for s in sentences if name in s]

        male_score = sum(s.lower().count(ind) for s in relevant for ind in self.GENDER_INDICATORS["male"])
        female_score = sum(s.lower().count(ind) for s in relevant for ind in self.GENDER_INDICATORS["female"])

        if male_score > female_score:
            return "male"
        elif female_score > male_score:
            return "female"
        return ""

    def guess_role(self, name: str, text: str) -> str:
        """Heuristic role guess based on surrounding descriptors."""
        sentences = re.split(r'[.!?]+', text)
        relevant = [s.lower() for s in sentences if name.lower() in s.lower()]
        combined = " ".join(relevant)

        for role, keywords in self.ROLE_KEYWORDS.items():
            if any(kw in combined for kw in keywords):
                return role
        return "supporting"

    def extract_appearance_from_text(self, name: str, text: str) -> Appearance:
        """Extract appearance details using regex patterns around character mentions."""
        appearance = Appearance()

        sentences = re.split(r'[.!?]+', text)
        relevant = [s for s in sentences if name in s]
        combined = " ".join(relevant)

        # Hair
        hair_patterns = [
            (r'(long|short|medium)[-\s]?(length)?\s*(black|brown|blonde|white|red|silver|blue|golden)?\s*hair', "style"),
            (r'hair\s*(is|was|being)?\s*(long|short|tied|braided|wavy|straight|curly|spiky)', "style"),
        ]
        for pattern, attr in hair_patterns:
            m = re.search(pattern, combined, re.IGNORECASE)
            if m:
                appearance.hair.style = m.group(0)

        # Eyes
        eye_match = re.search(r'(blue|brown|green|red|gold|silver|black|hazel|amber|gray)\s*eyes', combined, re.IGNORECASE)
        if eye_match:
            appearance.eyes = eye_match.group(0)

        # Build
        build_match = re.search(r'\b(slim|athletic|muscular|heavy|lean|stocky|sturdy)\s+(build|physique|figure|body)', combined, re.IGNORECASE)
        if build_match:
            appearance.body.build = build_match.group(1)

        return appearance

    def extract_from_text(self, text: str, novel_id: str = "") -> list[Character]:
        """Full heuristic extraction pipeline. Returns list of Character dataclasses."""
        names = self.extract_names(text)
        characters: list[Character] = []

        for name in names:
            gender = self.guess_gender(name, text)
            role = self.guess_role(name, text)
            appearance = self.extract_appearance_from_text(name, text)

            ch = Character(
                name=name,
                gender=gender,
                role=role,
                appearance=appearance,
                species="human",
                novel_id=novel_id,
            )
            characters.append(ch)

        return characters
