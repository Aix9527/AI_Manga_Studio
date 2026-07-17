"""
AI Manga Studio Pro V1.0 — Motion AI

Analyzes narrative text and character actions to generate detailed
motion descriptions for image-to-video (I2V) generation.

Motion AI translates textual action descriptions into structured
motion directives that guide video generation models (AnimateDiff,
SVD, etc.) to produce natural character movements.

Output motion descriptions include:
- Body movement (turn, walk, run, jump, etc.)
- Head movement (rotate, tilt, nod, look back, etc.)
- Hair movement (sway, blow, float, etc.)
- Clothing movement (flutter, drape, wave, etc.)
- Accessory movement (swing, dangle, etc.)
- Environmental interaction (dust, wind, water, etc.)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from loguru import logger


# ============================================================
# Data Classes
# ============================================================

@dataclass
class MotionDirective:
    """Structured motion directive for a single shot."""
    shot_index: int = 0

    # Body
    body_motion: str = "static"
    body_intensity: float = 0.0  # 0.0 (none) to 1.0 (intense)

    # Head
    head_motion: str = "static"
    head_direction: str = "front"

    # Hair
    hair_motion: str = "static"
    hair_intensity: float = 0.0

    # Clothing
    clothing_motion: str = "static"
    clothing_intensity: float = 0.0

    # Environment
    environment_motion: str = "none"
    environment_intensity: float = 0.0

    # Composite
    combined_description: str = ""
    i2v_prompt: str = ""


# ============================================================
# Motion AI Engine
# ============================================================

class MotionAI:
    """Analyzes text to generate motion descriptions for video generation.

    Extracts action verbs, direction cues, and environmental context
    to build detailed motion prompts suitable for image-to-video
    generation pipelines.
    """

    # Body action → motion description
    BODY_MOTIONS: Dict[str, str] = {
        "静止": "standing still, no body movement",
        "站立": "standing, slight weight shift",
        "走": "walking forward, natural gait, arm swing",
        "跑": "running, dynamic body lean, pumping arms",
        "追": "chasing, sprinting, intense forward motion",
        "飞": "flying, body horizontal, limbs extended",
        "跳": "jumping, body launched upward, knees bent",
        "冲": "dashing forward, explosive movement, speed lines",
        "奔": "sprinting, full body extension, powerful stride",
        "转身": "turning body, torso rotation, weight transfer",
        "回头": "looking back, head turning over shoulder",
        "抬头": "lifting head up, chin raising, neck extension",
        "低头": "lowering head, chin tucking, looking down",
        "蹲下": "crouching down, knees bending, lowering center of gravity",
        "站起": "standing up, body rising, legs straightening",
        "坐下": "sitting down, body lowering, bending at waist",
        "躺下": "lying down, body reclining, horizontal transition",
        "挥手": "waving hand, arm raised, hand oscillating",
        "拔剑": "drawing sword, arm sweeping motion, dynamic unsheathing",
        "握拳": "clenching fist, hand tensing, arm tensing",
        "推": "pushing forward, arms extending, body leaning",
        "拉": "pulling back, arms retracting, body bracing",
        "抱": "embracing, arms wrapping around, leaning in",
        "跌倒": "falling down, body tumbling, loss of balance",
        "爬": "crawling, body low to ground, alternating limbs",
        "攀爬": "climbing upward, reaching up, pulling body weight",
        "坠落": "falling downward, body vertical, hair and clothes rising",
        "游泳": "swimming, body horizontal in water, limbs stroking",
    }

    # Head motion descriptions
    HEAD_MOTIONS: Dict[str, str] = {
        "static": "head stationary, facing forward",
        "nod": "head nodding up and down, affirmative motion",
        "shake": "head shaking side to side, negative motion",
        "tilt": "head tilting to one side, curious or questioning",
        "rotate": "head rotating horizontally, scanning environment",
        "look_back": "head turning to look behind, over-the-shoulder glance",
        "look_up": "head tilting upward, looking at sky or above",
        "look_down": "head tilting downward, looking at ground or below",
        "look_left": "head turning left, glancing sideways",
        "look_right": "head turning right, glancing sideways",
    }

    # Hair motion
    HAIR_MOTIONS: Dict[str, str] = {
        "static": "hair still, no movement",
        "gentle_sway": "hair gently swaying, subtle movement",
        "wind_blow": "hair blowing in the wind, strands flowing",
        "dramatic": "hair dramatically flowing, anime-style dynamic movement",
        "bounce": "hair bouncing with body movement, rhythmic motion",
        "float": "hair floating upward, anti-gravity effect",
        "toss": "hair being tossed back, sweeping motion",
    }

    # Clothing motion
    CLOTHING_MOTIONS: Dict[str, str] = {
        "static": "clothing stationary, no movement",
        "gentle_flutter": "clothing gently fluttering, subtle fabric movement",
        "wind_effect": "clothing billowing in wind, fabric rippling",
        "dramatic_cape": "cape dramatically flowing, hero pose fabric motion",
        "dress_sway": "dress swaying with movement, fabric flowing",
        "scarf_flow": "scarf trailing behind, flowing in motion",
    }

    # Environment motion
    ENVIRONMENT_MOTIONS: Dict[str, str] = {
        "none": "static environment, no ambient motion",
        "wind": "wind blowing, dust particles floating, leaves rustling",
        "rain": "rain falling, droplets splashing, wet surfaces",
        "snow": "snowflakes falling gently, white particles drifting",
        "dust": "dust particles floating in light, atmospheric haze",
        "water_ripple": "water surface rippling, gentle wave motion",
        "fire": "flickering flames, dancing firelight, embers floating",
        "leaves": "leaves falling from trees, autumn drift, swirling",
        "fog": "fog drifting, mist rolling, ethereal atmosphere motion",
        "sparks": "sparks flying, embers bursting, particle effects",
    }

    def __init__(self) -> None:
        """Initialize Motion AI with default settings."""
        self.motion_scale: float = 1.0  # Global intensity multiplier
        self.style: str = "realistic"  # anime / realistic / cinematic

    # ----------------------------------------------------------
    # Public API
    # ----------------------------------------------------------

    def analyze(
        self,
        shot_index: int,
        action_text: str,
        emotion: str = "neutral",
        scene_weather: str = "clear",
        is_dialogue: bool = False,
        character_count: int = 1,
    ) -> MotionDirective:
        """Analyze text and generate a motion directive.

        Args:
            shot_index: Shot index.
            action_text: Action description text.
            emotion: Emotional state.
            scene_weather: Weather condition.
            is_dialogue: Whether dialogue is present (less movement).
            character_count: Number of characters (affects complexity).

        Returns:
            MotionDirective with all motion settings.
        """
        directive = MotionDirective(shot_index=shot_index)

        # 1. Body motion
        directive.body_motion, directive.body_intensity = self._analyze_body(action_text)

        # 2. Head motion
        directive.head_motion, directive.head_direction = self._analyze_head(action_text)

        # 3. Hair motion
        directive.hair_motion, directive.hair_intensity = self._analyze_hair(
            action_text=action_text,
            body_intensity=directive.body_intensity,
            scene_weather=scene_weather,
        )

        # 4. Clothing motion
        directive.clothing_motion, directive.clothing_intensity = self._analyze_clothing(
            action_text=action_text,
            body_intensity=directive.body_intensity,
            scene_weather=scene_weather,
        )

        # 5. Environment motion
        directive.environment_motion, directive.environment_intensity = (
            self._analyze_environment(scene_weather, action_text)
        )

        # 6. Dialogue dampening: reduce motion when characters are talking
        if is_dialogue:
            directive.body_intensity *= 0.3
            directive.hair_intensity *= 0.3
            directive.clothing_intensity *= 0.3

        # Apply global scale
        directive.body_intensity = min(1.0, directive.body_intensity * self.motion_scale)
        directive.hair_intensity = min(1.0, directive.hair_intensity * self.motion_scale)
        directive.clothing_intensity = min(1.0, directive.clothing_intensity * self.motion_scale)

        # 7. Build combined description
        directive.combined_description = self._build_description(directive)

        # 8. Build I2V prompt
        directive.i2v_prompt = self._build_i2v_prompt(directive)

        return directive

    def analyze_batch(
        self,
        shots_data: List[dict],
    ) -> List[MotionDirective]:
        """Analyze a batch of shots.

        Args:
            shots_data: List of dicts with keys matching analyze() params.

        Returns:
            List of MotionDirective objects.
        """
        results: List[MotionDirective] = []

        for i, data in enumerate(shots_data):
            directive = self.analyze(
                shot_index=data.get("index", i),
                action_text=data.get("action", ""),
                emotion=data.get("emotion", "neutral"),
                scene_weather=data.get("weather", "clear"),
                is_dialogue=data.get("is_dialogue", False),
                character_count=data.get("character_count", 1),
            )
            results.append(directive)

        logger.info(f"MotionAI: Analyzed {len(results)} shots")
        return results

    # ----------------------------------------------------------
    # Analysis Methods
    # ----------------------------------------------------------

    def _analyze_body(self, action_text: str) -> tuple:
        """Analyze body motion from action text.

        Args:
            action_text: Action description.

        Returns:
            Tuple of (motion_description, intensity).
        """
        if not action_text or action_text == "静止":
            return self.BODY_MOTIONS.get("静止", "static"), 0.0

        # Check for matching action keywords
        for action_key, description in self.BODY_MOTIONS.items():
            if action_key in action_text:
                # Intensity based on action type
                high_intensity = {"跑", "追", "冲", "奔", "飞", "跳", "坠落"}
                medium_intensity = {"转身", "拔剑", "推", "拉", "跌倒", "攀爬"}
                low_intensity = {"走", "回头", "抬头", "低头", "挥手", "握拳"}

                if action_key in high_intensity:
                    return description, 0.9
                elif action_key in medium_intensity:
                    return description, 0.6
                elif action_key in low_intensity:
                    return description, 0.4
                else:
                    return description, 0.3

        # Default: static with subtle movement
        return "subtle body sway, breathing motion, idle animation", 0.1

    def _analyze_head(self, action_text: str) -> tuple:
        """Analyze head motion from action text.

        Args:
            action_text: Action description.

        Returns:
            Tuple of (head_motion_key, head_direction).
        """
        head_mapping = {
            "回头": ("look_back", "back"),
            "抬头": ("look_up", "up"),
            "低头": ("look_down", "down"),
        }

        for action_key, (motion, direction) in head_mapping.items():
            if action_key in action_text:
                return self.HEAD_MOTIONS.get(motion, "static"), direction

        return self.HEAD_MOTIONS["static"], "front"

    def _analyze_hair(
        self,
        action_text: str,
        body_intensity: float,
        scene_weather: str,
    ) -> tuple:
        """Analyze hair motion.

        Args:
            action_text: Action description.
            body_intensity: Body motion intensity.
            scene_weather: Weather condition.

        Returns:
            Tuple of (hair_motion_key, intensity).
        """
        # Weather-driven hair motion
        if scene_weather in ("storm", "wind"):
            return self.HAIR_MOTIONS["dramatic"], 0.9
        if scene_weather in ("rain", "snow"):
            return self.HAIR_MOTIONS["wind_blow"], 0.6

        # Body-driven hair motion
        if body_intensity > 0.7:
            return self.HAIR_MOTIONS["dramatic"], 0.8
        if body_intensity > 0.4:
            return self.HAIR_MOTIONS["bounce"], 0.5
        if body_intensity > 0.1:
            return self.HAIR_MOTIONS["gentle_sway"], 0.2

        # Flying / falling → float
        if any(kw in action_text for kw in ["飞", "坠落", "跳"]):
            return self.HAIR_MOTIONS["float"], 0.7

        return self.HAIR_MOTIONS["static"], 0.0

    def _analyze_clothing(
        self,
        action_text: str,
        body_intensity: float,
        scene_weather: str,
    ) -> tuple:
        """Analyze clothing motion.

        Args:
            action_text: Action description.
            body_intensity: Body motion intensity.
            scene_weather: Weather condition.

        Returns:
            Tuple of (clothing_motion_key, intensity).
        """
        if scene_weather in ("storm",):
            return self.CLOTHING_MOTIONS["dramatic_cape"], 0.9
        if scene_weather in ("wind", "rain"):
            return self.CLOTHING_MOTIONS["wind_effect"], 0.7

        if body_intensity > 0.7:
            return self.CLOTHING_MOTIONS["dramatic_cape"], 0.8
        if body_intensity > 0.4:
            return self.CLOTHING_MOTIONS["gentle_flutter"], 0.4
        if body_intensity > 0.1:
            return self.CLOTHING_MOTIONS["gentle_flutter"], 0.2

        return self.CLOTHING_MOTIONS["static"], 0.0

    def _analyze_environment(
        self, weather: str, action_text: str
    ) -> tuple:
        """Analyze environment motion.

        Args:
            weather: Weather condition.
            action_text: Action description.

        Returns:
            Tuple of (environment_motion_key, intensity).
        """
        weather_to_env: Dict[str, tuple] = {
            "clear": ("none", 0.0),
            "cloudy": ("dust", 0.2),
            "rain": ("rain", 0.7),
            "snow": ("snow", 0.6),
            "fog": ("fog", 0.5),
            "storm": ("wind", 1.0),
            "wind": ("wind", 0.8),
        }

        if weather in weather_to_env:
            key, intensity = weather_to_env[weather]
            return self.ENVIRONMENT_MOTIONS.get(key, "none"), intensity

        # Action-driven environment
        if any(kw in action_text for kw in ["爆炸", "火焰", "燃烧"]):
            return self.ENVIRONMENT_MOTIONS["fire"], 0.8

        return self.ENVIRONMENT_MOTIONS["none"], 0.0

    # ----------------------------------------------------------
    # Output Building
    # ----------------------------------------------------------

    def _build_description(self, directive: MotionDirective) -> str:
        """Build a combined human-readable motion description.

        Args:
            directive: The MotionDirective.

        Returns:
            Description string.
        """
        parts: List[str] = []

        if directive.body_intensity > 0:
            parts.append(f"Body: {directive.body_motion}")
        if directive.head_motion != "static":
            parts.append(f"Head: {self.HEAD_MOTIONS.get(directive.head_motion, directive.head_motion)}")
        if directive.hair_intensity > 0:
            parts.append(f"Hair: {self.HAIR_MOTIONS.get(directive.hair_motion, directive.hair_motion)}")
        if directive.clothing_intensity > 0:
            parts.append(f"Clothing: {self.CLOTHING_MOTIONS.get(directive.clothing_motion, directive.clothing_motion)}")
        if directive.environment_intensity > 0:
            parts.append(f"Environment: {self.ENVIRONMENT_MOTIONS.get(directive.environment_motion, directive.environment_motion)}")

        return "; ".join(parts) if parts else "No motion"

    def _build_i2v_prompt(self, directive: MotionDirective) -> str:
        """Build an image-to-video prompt from the directive.

        Args:
            directive: The MotionDirective.

        Returns:
            I2V prompt string.
        """
        prompts: List[str] = []

        # Body
        if directive.body_intensity > 0.2:
            prompts.append(directive.body_motion)

        # Hair
        if directive.hair_intensity > 0.3:
            prompts.append(self.HAIR_MOTIONS.get(directive.hair_motion, ""))

        # Clothing
        if directive.clothing_intensity > 0.3:
            prompts.append(self.CLOTHING_MOTIONS.get(directive.clothing_motion, ""))

        # Environment
        if directive.environment_intensity > 0.2:
            prompts.append(self.ENVIRONMENT_MOTIONS.get(directive.environment_motion, ""))

        # Style tag
        if self.style == "anime":
            prompts.append("smooth animation, fluid motion, anime interpolation")
        elif self.style == "cinematic":
            prompts.append("cinematic motion blur, 24fps film look")

        return ", ".join(p for p in prompts if p)
