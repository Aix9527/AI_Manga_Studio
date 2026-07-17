"""
AI Manga Studio Pro V1.0 — Scene Memory

Persistent scene / background memory that stores reusable scene
profiles including prompt templates, ControlNet references,
lighting conditions, and LoRA paths.

Each scene is a distinct location that appears across shots;
scene memory ensures consistent backgrounds and environments.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from loguru import logger
from sqlalchemy.orm import Session

from backend.database import Scene as SceneORM, get_session


# ============================================================
# Data Class
# ============================================================

@dataclass
class SceneMemoryEntry:
    """In-memory scene profile."""
    name: str
    description: str = ""
    prompt_positive: str = ""
    prompt_negative: str = ""
    weather: str = "clear"
    time_of_day: str = "day"
    lighting: str = ""
    controlnet_type: str = ""
    controlnet_path: str = ""
    lora_path: str = ""
    reference_images: List[str] = field(default_factory=list)
    db_id: Optional[int] = None


# ============================================================
# Scene Memory Manager
# ============================================================

class SceneMemory:
    """Manages persistent scene / background profiles.

    Each scene captures location, environment, lighting, and
    ControlNet settings for reproducible background generation.
    """

    # Weather prompt fragments
    WEATHER_PROMPTS: Dict[str, str] = {
        "clear": "clear sky, sunny day, bright sunlight",
        "cloudy": "overcast sky, soft diffused light, cloudy atmosphere",
        "rain": "heavy rain, wet surfaces, raindrops, puddles reflecting light",
        "snow": "snowfall, white ground cover, frost, cold atmosphere",
        "fog": "dense fog, low visibility, ethereal atmosphere, mist",
        "storm": "thunderstorm, lightning flashes, dark storm clouds, dramatic",
        "sunset": "golden hour, warm sunset glow, orange and pink sky",
        "night": "starry night sky, moonlight, dark ambient, nocturnal",
    }

    # Time of day prompt fragments
    TIME_PROMPTS: Dict[str, str] = {
        "dawn": "early morning, dawn light, soft sunrise, dew",
        "morning": "morning light, fresh atmosphere, crisp shadows",
        "noon": "midday sun, harsh overhead lighting, strong shadows",
        "afternoon": "afternoon light, warm tones, golden cast",
        "dusk": "twilight, dusk ambiance, fading light, purple sky",
        "night": "nighttime, moonlit, dark shadows, artificial lighting",
    }

    # Common lighting styles
    LIGHTING_STYLES: Dict[str, str] = {
        "natural": "natural lighting, realistic shadows",
        "cinematic": "cinematic lighting, dramatic shadows, volumetric light",
        "studio": "studio lighting, three-point light setup, soft shadows",
        "rim": "rim lighting, backlit, hair light, dramatic silhouette",
        "neon": "neon lighting, cyberpunk glow, colored ambient light",
        "candle": "candlelight, warm flickering illumination, intimate",
        "god_rays": "god rays, volumetric sunbeams, atmospheric scattering",
    }

    def __init__(self, project_id: int) -> None:
        """Initialize scene memory for a specific project.

        Args:
            project_id: The database ID of the owning project.
        """
        self.project_id = project_id
        self._cache: Dict[str, SceneMemoryEntry] = {}

    # ----------------------------------------------------------
    # CRUD
    # ----------------------------------------------------------

    def create_scene(
        self,
        name: str,
        description: str = "",
        weather: str = "clear",
        time_of_day: str = "day",
        lighting: str = "",
        controlnet_type: str = "",
        controlnet_path: str = "",
        lora_path: str = "",
    ) -> SceneMemoryEntry:
        """Create a new scene profile.

        Args:
            name: Scene name / location identifier.
            description: Natural language description.
            weather: Weather condition keyword.
            time_of_day: Time of day keyword.
            lighting: Lighting style keyword.
            controlnet_type: ControlNet preprocessor type.
            controlnet_path: Path to ControlNet reference image.
            lora_path: Path to scene-specific LoRA.

        Returns:
            Created SceneMemoryEntry.
        """
        # Build prompts
        prompt_positive = self._build_positive_prompt(
            name=name,
            description=description,
            weather=weather,
            time_of_day=time_of_day,
            lighting=lighting,
        )
        prompt_negative = self._build_negative_prompt()

        entry = SceneMemoryEntry(
            name=name,
            description=description,
            prompt_positive=prompt_positive,
            prompt_negative=prompt_negative,
            weather=weather,
            time_of_day=time_of_day,
            lighting=lighting,
            controlnet_type=controlnet_type,
            controlnet_path=controlnet_path,
            lora_path=lora_path,
        )

        # Persist
        session: Session = get_session()
        try:
            orm = SceneORM(
                project_id=self.project_id,
                name=entry.name,
                description=entry.description,
                prompt_positive=entry.prompt_positive,
                prompt_negative=entry.prompt_negative,
                weather=entry.weather,
                time_of_day=entry.time_of_day,
                lighting=entry.lighting,
                controlnet_type=entry.controlnet_type,
                controlnet_path=entry.controlnet_path,
                lora_path=entry.lora_path,
            )
            session.add(orm)
            session.commit()
            session.refresh(orm)
            entry.db_id = orm.id
            logger.info(f"SceneMemory: Created scene '{name}' (id={orm.id})")
        except Exception as exc:
            session.rollback()
            logger.error(f"SceneMemory: Failed to create scene '{name}': {exc}")
            raise
        finally:
            session.close()

        self._cache[name] = entry
        return entry

    def get_scene(self, name: str) -> Optional[SceneMemoryEntry]:
        """Retrieve a scene by name.

        Args:
            name: Scene name.

        Returns:
            SceneMemoryEntry or None.
        """
        if name in self._cache:
            return self._cache[name]

        session: Session = get_session()
        try:
            orm: Optional[SceneORM] = (
                session.query(SceneORM)
                .filter(
                    SceneORM.project_id == self.project_id,
                    SceneORM.name == name,
                )
                .first()
            )
            if orm:
                entry = self._orm_to_entry(orm)
                self._cache[name] = entry
                return entry
        finally:
            session.close()

        return None

    def get_all_scenes(self) -> List[SceneMemoryEntry]:
        """Get all scenes for the project.

        Returns:
            List of SceneMemoryEntry objects.
        """
        session: Session = get_session()
        try:
            orms = (
                session.query(SceneORM)
                .filter(SceneORM.project_id == self.project_id)
                .all()
            )
            entries = [self._orm_to_entry(orm) for orm in orms]
            for entry in entries:
                self._cache[entry.name] = entry
            return entries
        finally:
            session.close()

    def update_scene(self, name: str, **kwargs: Any) -> Optional[SceneMemoryEntry]:
        """Update a scene's fields.

        Args:
            name: Scene name.
            **kwargs: Fields to update.

        Returns:
            Updated entry or None.
        """
        session: Session = get_session()
        try:
            orm: Optional[SceneORM] = (
                session.query(SceneORM)
                .filter(
                    SceneORM.project_id == self.project_id,
                    SceneORM.name == name,
                )
                .first()
            )
            if not orm:
                return None

            for key, value in kwargs.items():
                if hasattr(orm, key):
                    setattr(orm, key, value)

            # Rebuild prompts if environmental fields changed
            env_fields = {"description", "weather", "time_of_day", "lighting"}
            if env_fields & set(kwargs.keys()):
                orm.prompt_positive = self._build_positive_prompt(
                    name=orm.name,
                    description=orm.description or "",
                    weather=orm.weather or "clear",
                    time_of_day=orm.time_of_day or "day",
                    lighting=orm.lighting or "",
                )
                orm.prompt_negative = self._build_negative_prompt()

            session.commit()
            session.refresh(orm)
            entry = self._orm_to_entry(orm)
            self._cache[name] = entry
            return entry
        except Exception as exc:
            session.rollback()
            logger.error(f"SceneMemory: Failed to update scene '{name}': {exc}")
            raise
        finally:
            session.close()

    def delete_scene(self, name: str) -> bool:
        """Delete a scene profile."""
        session: Session = get_session()
        try:
            orm: Optional[SceneORM] = (
                session.query(SceneORM)
                .filter(
                    SceneORM.project_id == self.project_id,
                    SceneORM.name == name,
                )
                .first()
            )
            if not orm:
                return False
            session.delete(orm)
            session.commit()
            self._cache.pop(name, None)
            return True
        except Exception as exc:
            session.rollback()
            logger.error(f"SceneMemory: Failed to delete scene '{name}': {exc}")
            raise
        finally:
            session.close()

    # ----------------------------------------------------------
    # Prompt Building
    # ----------------------------------------------------------

    def _build_positive_prompt(
        self,
        name: str,
        description: str,
        weather: str,
        time_of_day: str,
        lighting: str,
    ) -> str:
        """Build a high-quality positive prompt for the scene.

        Args:
            name: Scene name.
            description: Scene description.
            weather: Weather condition.
            time_of_day: Time of day.
            lighting: Lighting style.

        Returns:
            Positive prompt string.
        """
        parts: List[str] = ["masterpiece", "best quality", "cinematic"]

        # Scene description
        if description:
            parts.append(description)
        else:
            parts.append(f"background of {name}")

        # Environment
        weather_prompt = self.WEATHER_PROMPTS.get(weather, weather)
        parts.append(weather_prompt)

        time_prompt = self.TIME_PROMPTS.get(time_of_day, time_of_day)
        parts.append(time_prompt)

        # Lighting
        if lighting:
            light_prompt = self.LIGHTING_STYLES.get(lighting, lighting)
            parts.append(light_prompt)

        # Quality boosters
        parts.extend([
            "highly detailed background",
            "8K resolution",
            "sharp focus",
            "professional composition",
        ])

        return ", ".join(parts)

    def _build_negative_prompt(self) -> str:
        """Build a standard negative prompt to avoid common artifacts.

        Returns:
            Negative prompt string.
        """
        return (
            "lowres, bad anatomy, bad hands, text, error, missing fingers, "
            "extra digit, fewer digits, cropped, worst quality, low quality, "
            "normal quality, jpeg artifacts, signature, watermark, username, "
            "blurry, ugly, deformed, noisy"
        )

    def get_scene_prompts(self, name: str) -> tuple:
        """Get both positive and negative prompts for a scene.

        Args:
            name: Scene name.

        Returns:
            Tuple of (positive_prompt, negative_prompt). Defaults if not found.
        """
        scene = self.get_scene(name)
        if scene:
            return scene.prompt_positive, scene.prompt_negative
        return "", self._build_negative_prompt()

    # ----------------------------------------------------------
    # Helpers
    # ----------------------------------------------------------

    def _orm_to_entry(self, orm: SceneORM) -> SceneMemoryEntry:
        """Convert ORM model to runtime entry."""
        return SceneMemoryEntry(
            name=orm.name,
            description=orm.description or "",
            prompt_positive=orm.prompt_positive or "",
            prompt_negative=orm.prompt_negative or "",
            weather=orm.weather or "clear",
            time_of_day=orm.time_of_day or "day",
            lighting=orm.lighting or "",
            controlnet_type=orm.controlnet_type or "",
            controlnet_path=orm.controlnet_path or "",
            lora_path=orm.lora_path or "",
            reference_images=orm.reference_images or [],
            db_id=orm.id,
        )

    def export_to_dict(self) -> Dict[str, Any]:
        """Export all scenes to a serializable dict."""
        return {
            "project_id": self.project_id,
            "scenes": [
                {
                    "name": s.name,
                    "description": s.description,
                    "prompt_positive": s.prompt_positive,
                    "prompt_negative": s.prompt_negative,
                    "weather": s.weather,
                    "time_of_day": s.time_of_day,
                    "lighting": s.lighting,
                    "controlnet_type": s.controlnet_type,
                    "controlnet_path": s.controlnet_path,
                    "lora_path": s.lora_path,
                }
                for s in self.get_all_scenes()
            ],
        }

    def export_json(self, filepath: str) -> None:
        """Export scenes to a JSON file."""
        data = self.export_to_dict()
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        logger.info(f"SceneMemory: Exported to {filepath}")
