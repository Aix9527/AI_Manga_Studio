"""
AI Manga Studio Pro V1.0 — Emotion AI

Analyzes narrative context and dialogue to generate detailed facial
expression and emotional state descriptions for character rendering.

Emotion AI translates emotional keywords and context into concrete
visual descriptors that guide image generation models to produce
accurate facial expressions, body language, and emotional cues.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional

from loguru import logger


# ============================================================
# Data Classes
# ============================================================

@dataclass
class EmotionDirective:
    """Structured emotion directive for a single shot."""
    shot_index: int = 0
    primary_emotion: str = "neutral"

    # Eyes
    eye_state: str = "open"
    eye_detail: str = "looking forward, normal eyes"
    eye_effect: str = ""  # tear, sparkle, glow, etc.

    # Eyebrows
    eyebrow_state: str = "neutral"

    # Mouth
    mouth_state: str = "closed"
    mouth_detail: str = "relaxed lips, slight smile"

    # Face overall
    face_state: str = "neutral expression"
    blush: bool = False
    face_detail: str = ""

    # Body language
    body_language: str = "neutral posture"

    # Composite
    combined_description: str = ""
    prompt_fragment: str = ""


# ============================================================
# Emotion AI Engine
# ============================================================

class EmotionAI:
    """Analyzes text to generate emotional expression descriptions.

    Maps emotional states to concrete visual cues for eyes, eyebrows,
    mouth, face, and body language, producing prompt fragments for
    character image generation.
    """

    # Emotion → eyes
    EYE_STATES: Dict[str, str] = {
        "neutral": "open, relaxed, looking forward",
        "happy": "slightly narrowed, curved upward, bright, sparkling eyes",
        "sad": "half-closed, downturned, moist eyes, slight redness",
        "angry": "wide open, sharp glare, intense stare, veins visible",
        "surprised": "wide open, dilated pupils, raised eyelids",
        "fearful": "wide open, trembling, darting pupils, small irises",
        "sorrowful": "half-closed, tears welling up, downcast gaze",
        "joyful": "closed in happy curve (^_^ shape), crinkled corners",
        "worried": "slightly narrowed, furrowed, anxious darting",
        "loving": "soft gaze, half-lidded, gentle warmth, doe eyes",
        "hateful": "narrowed, cold glare, sharp piercing eyes",
        "confused": "wide, unfocused, looking slightly up and to side",
        "determined": "sharp focus, furrowed slightly, intense forward gaze",
        "trembling": "wide, shaking, unfocused, fearful glint",
        "sighing": "half-closed, downcast, melancholic gaze",
        "crying": "closed tight, tears streaming, red and puffy",
        "shocked": "eyes bulging, extreme wide, pinprick pupils",
        "embarrassed": "averted gaze, looking away, nervous darting",
        "proud": "half-lidded confident gaze, looking slightly down",
        "bored": "half-closed, unfocused, looking away, disinterested",
    }

    # Emotion → mouth
    MOUTH_STATES: Dict[str, str] = {
        "neutral": "closed, relaxed, neutral line",
        "happy": "open smile, curved upward, teeth showing slightly",
        "sad": "downturned, trembling lower lip, slight frown",
        "angry": "tight grimace, clenched teeth, snarling",
        "surprised": "open in 'o' shape, gasping",
        "fearful": "open, trembling, gasping, teeth chattering",
        "sorrowful": "quivering downturned, suppressed sob",
        "joyful": "wide open laugh, hearty smile, teeth visible",
        "worried": "biting lower lip, tense, slight downturn",
        "loving": "gentle closed smile, warm curve, soft",
        "hateful": "tight sneer, curled lip, contemptuous smirk",
        "confused": "slightly open, pouting, tilted",
        "determined": "tight closed, firm line, jaw set",
        "crying": "wide open wailing, trembling, tears entering",
        "shocked": "wide open, jaw dropped, speechless",
        "embarrassed": "nervous smile, wry grin, sweat drop",
    }

    # Emotion → body language
    BODY_LANGUAGE: Dict[str, str] = {
        "neutral": "relaxed posture, arms at sides, balanced stance",
        "happy": "open posture, arms slightly raised, leaning forward",
        "sad": "slumped shoulders, head down, arms wrapped around self",
        "angry": "tense stance, clenched fists, leaning forward aggressively",
        "surprised": "body leaned back, hands raised slightly, startled pose",
        "fearful": "cowering, arms raised defensively, body trembling",
        "sorrowful": "knees drawn up, head buried, curled up posture",
        "joyful": "arms spread wide, jumping, energetic pose",
        "worried": "hand on chin, pacing, fidgeting fingers",
        "loving": "leaning in close, gentle touch, open arms",
        "hateful": "arms crossed, turning away, dismissive posture",
        "confused": "head tilted, hand on temple, uncertain stance",
        "determined": "firm stance, fist clenched at chest, forward lean",
        "trembling": "shaking all over, arms clutching body, unstable",
        "crying": "hands covering face, shoulders shaking, kneeling",
        "embarrassed": "scratching back of head, looking down, fidgeting",
    }

    # Emotion → face overall
    FACE_STATES: Dict[str, str] = {
        "neutral": "neutral expression, relaxed facial muscles",
        "happy": "bright expression, cheeks raised, warm glow",
        "sad": "downcast expression, slight redness around eyes and nose",
        "angry": "flushed face, vein marks, furrowed brow, tense muscles",
        "surprised": "eyes wide, eyebrows raised high, mouth open",
        "fearful": "pale face, cold sweat, trembling features",
        "sorrowful": "tear-streaked face, red nose, quivering features",
        "joyful": "beaming face, rosy cheeks, eyes closed in joy",
        "worried": "furrowed brow, tense jaw, slight sweat",
        "loving": "soft expression, gentle smile, warm glow, slight blush",
        "hateful": "dark expression, shadow over eyes, cold features",
        "confused": "tilted head, furrowed brow, question mark expression",
        "determined": "intense expression, sharp eyes, firm jaw, no hesitation",
        "crying": "tears streaming, red puffy eyes, runny nose, quivering",
    }

    def __init__(self) -> None:
        """Initialize Emotion AI."""
        self.intensity_scale: float = 1.0
        self.style: str = "realistic"

    # ----------------------------------------------------------
    # Public API
    # ----------------------------------------------------------

    def analyze(
        self,
        shot_index: int,
        emotion: str = "neutral",
        dialogue: str = "",
        context: str = "",
        character_name: str = "",
    ) -> EmotionDirective:
        """Analyze emotional context and generate visual expression directives.

        Args:
            shot_index: Shot index.
            emotion: Primary emotion keyword.
            dialogue: Dialogue text for additional cues.
            context: Surrounding narrative context.
            character_name: Character name for logging.

        Returns:
            EmotionDirective with all expression details.
        """
        # Normalize emotion
        primary = self._normalize_emotion(emotion, dialogue)

        directive = EmotionDirective(
            shot_index=shot_index,
            primary_emotion=primary,
        )

        # Eyes
        directive.eye_state, directive.eye_effect = self._analyze_eyes(primary, dialogue)

        # Mouth
        directive.mouth_state = self._analyze_mouth(primary, dialogue)

        # Face
        directive.face_state = self.FACE_STATES.get(primary, self.FACE_STATES["neutral"])
        directive.blush = primary in ("happy", "joyful", "loving", "embarrassed")

        # Body
        directive.body_language = self.BODY_LANGUAGE.get(
            primary, self.BODY_LANGUAGE["neutral"]
        )

        # Build composite
        directive.combined_description = self._build_description(directive)
        directive.prompt_fragment = self._build_prompt_fragment(directive)

        logger.debug(
            f"EmotionAI: Shot {shot_index} → {primary} "
            f"({'crying' if directive.eye_effect == 'tears' else 'normal'})"
        )

        return directive

    def analyze_batch(
        self,
        shots_data: List[dict],
    ) -> List[EmotionDirective]:
        """Analyze a batch of shots for emotional expressions.

        Args:
            shots_data: List of dicts with keys matching analyze() params.

        Returns:
            List of EmotionDirective objects.
        """
        results: List[EmotionDirective] = []

        for i, data in enumerate(shots_data):
            directive = self.analyze(
                shot_index=data.get("index", i),
                emotion=data.get("emotion", "neutral"),
                dialogue=data.get("dialogue", ""),
                context=data.get("context", ""),
                character_name=data.get("character", ""),
            )
            results.append(directive)

        logger.info(f"EmotionAI: Analyzed {len(results)} shots")
        return results

    # ----------------------------------------------------------
    # Analysis Methods
    # ----------------------------------------------------------

    def _normalize_emotion(self, emotion: str, dialogue: str) -> str:
        """Normalize emotion keyword, using dialogue as supplementary signal.

        Args:
            emotion: Raw emotion keyword.
            dialogue: Dialogue text.

        Returns:
            Normalized emotion keyword.
        """
        # Map Chinese emotion words to English keywords
        chinese_map: Dict[str, str] = {
            "笑": "happy",
            "哭": "crying",
            "怒": "angry",
            "惊": "surprised",
            "怕": "fearful",
            "悲": "sorrowful",
            "喜": "joyful",
            "忧": "worried",
            "恨": "hateful",
            "爱": "loving",
            "叹息": "sighing",
            "沉默": "neutral",
            "颤抖": "trembling",
            "尴尬": "embarrassed",
            "害羞": "embarrassed",
            "骄傲": "proud",
            "无聊": "bored",
            "困惑": "confused",
            "决心": "determined",
        }

        if emotion in chinese_map:
            emotion = chinese_map[emotion]

        # If emotion is still Chinese, try to map
        for cn, en in chinese_map.items():
            if cn in emotion:
                return en

        # Dialogue-based intensity boost
        if dialogue:
            exclamation_count = dialogue.count("！") + dialogue.count("!")
            if exclamation_count >= 3 and emotion == "neutral":
                return "surprised"

        # Validate against known emotions
        known = set(self.FACE_STATES.keys())
        if emotion not in known:
            return "neutral"

        return emotion

    def _analyze_eyes(self, emotion: str, dialogue: str) -> tuple:
        """Analyze eye state and effects.

        Args:
            emotion: Normalized emotion.
            dialogue: Dialogue text.

        Returns:
            Tuple of (eye_state_description, eye_effect).
        """
        eye_desc = self.EYE_STATES.get(emotion, self.EYE_STATES["neutral"])

        # Tear effects for crying-related emotions
        effect = ""
        if emotion in ("crying", "sad", "sorrowful", "trembling"):
            effect = "tears"
        elif emotion == "joyful":
            effect = "sparkle"
        elif emotion in ("angry", "hateful"):
            effect = "glare"
        elif emotion == "surprised":
            effect = "dilation"

        return eye_desc, effect

    def _analyze_mouth(self, emotion: str, dialogue: str) -> str:
        """Analyze mouth state.

        Args:
            emotion: Normalized emotion.
            dialogue: Dialogue text.

        Returns:
            Mouth state description.
        """
        mouth = self.MOUTH_STATES.get(emotion, self.MOUTH_STATES["neutral"])

        # If dialogue exists, mouth should be slightly open
        if dialogue and emotion in ("neutral", "happy", "loving"):
            mouth = "slightly open, speaking, lip sync"

        return mouth

    # ----------------------------------------------------------
    # Output Building
    # ----------------------------------------------------------

    def _build_description(self, directive: EmotionDirective) -> str:
        """Build a combined human-readable emotion description.

        Args:
            directive: The EmotionDirective.

        Returns:
            Description string.
        """
        return (
            f"Emotion: {directive.primary_emotion} | "
            f"Eyes: {directive.eye_state} | "
            f"Mouth: {directive.mouth_state} | "
            f"Face: {directive.face_state} | "
            f"Body: {directive.body_language}"
        )

    def _build_prompt_fragment(self, directive: EmotionDirective) -> str:
        """Build a prompt fragment for image generation.

        Args:
            directive: The EmotionDirective.

        Returns:
            Prompt fragment string.
        """
        parts: List[str] = []

        # Expression
        parts.append(f"expression: {directive.face_state}")

        # Eyes
        parts.append(directive.eye_state)
        if directive.eye_effect == "tears":
            parts.append("tears streaming down face, crying, wet cheeks")
        elif directive.eye_effect == "sparkle":
            parts.append("sparkling eyes, eye shimmer, anime eye highlights")

        # Mouth
        parts.append(directive.mouth_state)

        # Blush
        if directive.blush:
            parts.append("blush, rosy cheeks, embarrassed flush")

        # Body
        parts.append(directive.body_language)

        # Style-specific
        if self.style == "anime":
            parts.append("anime expression style, exaggerated emotion")

        return ", ".join(parts)
