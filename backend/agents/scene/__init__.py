"""
Scene Agent (Part 9)

Analyzes and generates scene descriptions including location,
atmosphere, time-of-day, camera directions, and visual composition
guidance for downstream image/video generation.

Works closely with StoryAgent output and CharacterAgent profiles
to ensure scene-level consistency.
"""

from __future__ import annotations

from typing import Any

from backend.agents.base_agent import (
    BaseAgent,
    AgentContext,
    AgentResult,
    AgentStatus,
)


class SceneAgent(BaseAgent[AgentResult]):
    """
    Scene analysis and generation agent.

    Input: Story scenes + character profiles + location data
    Output: Enriched scene descriptions with visual guidance

    Capabilities:
    - Scene enrichment (atmosphere, lighting, camera)
    - Location consistency check
    - Character placement within scenes
    - Visual composition suggestions
    """

    def __init__(
        self,
        agent_id: str = "scene_agent",
        agent_type: str = "scene",
    ) -> None:
        super().__init__(agent_id=agent_id, agent_type=agent_type)
        self.capabilities = [
            "scene_enrichment",
            "location_consistency",
            "character_placement",
            "visual_composition",
        ]

    async def _execute_impl(
        self, context: AgentContext, **kwargs: Any
    ) -> AgentResult:
        """
        Enrich scene descriptions with visual guidance.

        Args:
            scenes: Raw scenes from StoryAgent
            characters: Character profiles
            locations: Extracted locations

        Returns:
            AgentResult with enriched scene descriptions
        """
        scenes = kwargs.get("scenes", [])
        characters = kwargs.get("characters", [])
        locations = kwargs.get("locations", [])

        enriched_scenes = []
        for i, scene in enumerate(scenes[:30]):  # Limit for MVP
            enriched = self._enrich_scene(scene, i, characters, locations)
            enriched_scenes.append(enriched)

        return AgentResult(
            agent_id=self.agent_id,
            agent_type=self.agent_type,
            status=AgentStatus.COMPLETED,
            output={
                "scenes": enriched_scenes,
                "scene_count": len(enriched_scenes),
                "locations_used": locations[: min(len(locations), 10)],
            },
        )

    @classmethod
    def input_schema(cls) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "scenes": {"type": "array"},
                "characters": {"type": "array"},
                "locations": {"type": "array"},
            },
            "required": ["scenes"],
        }

    @classmethod
    def output_schema(cls) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "scenes": {"type": "array"},
                "scene_count": {"type": "integer"},
            },
        }

    # ── Internal methods ─────────────────────────────────────

    def _enrich_scene(
        self,
        scene: dict[str, Any],
        index: int,
        characters: list[dict[str, Any]],
        locations: list[str],
    ) -> dict[str, Any]:
        """Add visual guidance to a raw scene."""
        time_options = ["dawn", "morning", "noon", "afternoon", "evening", "night"]
        mood_options = ["peaceful", "tense", "mysterious", "dramatic", "melancholic"]
        camera_options = [
            "wide shot",
            "medium shot",
            "close-up",
            "dutch angle",
            "overhead",
            "tracking",
        ]

        # Assign characters to this scene (simple round-robin)
        scene_chars = characters[max(0, index - 1) : index + 2] if characters else []

        return {
            **scene,
            "enriched": {
                "time_of_day": time_options[index % len(time_options)],
                "mood": mood_options[index % len(mood_options)],
                "lighting": self._suggest_lighting(index),
                "camera_direction": camera_options[index % len(camera_options)],
                "color_palette": self._suggest_palette(index),
                "characters_present": [c.get("name", "") for c in scene_chars],
                "location": (
                    locations[index % len(locations)]
                    if locations
                    else "unknown"
                ),
                "visual_prompt": self._build_scene_prompt(
                    scene, index, scene_chars, locations
                ),
            },
        }

    def _suggest_lighting(self, index: int) -> dict[str, Any]:
        """Suggest lighting parameters for scene."""
        lighting_options = [
            {"type": "natural", "direction": "front", "intensity": "medium"},
            {"type": "dramatic", "direction": "side", "intensity": "high"},
            {"type": "ambient", "direction": "top", "intensity": "low"},
            {"type": "rim", "direction": "back", "intensity": "high"},
            {"type": "soft", "direction": "diffuse", "intensity": "medium"},
        ]
        return lighting_options[index % len(lighting_options)]

    def _suggest_palette(self, index: int) -> list[str]:
        """Suggest color palette for scene."""
        palettes = [
            ["#2C3E50", "#E74C3C", "#ECF0F1"],
            ["#27AE60", "#F1C40F", "#FFFFFF"],
            ["#8E44AD", "#3498DB", "#1ABC9C"],
            ["#E67E22", "#C0392B", "#2C3E50"],
            ["#1ABC9C", "#F39C12", "#ECF0F1"],
        ]
        return palettes[index % len(palettes)]

    def _build_scene_prompt(
        self,
        scene: dict[str, Any],
        index: int,
        characters: list[dict[str, Any]],
        locations: list[str],
    ) -> str:
        """Build a visual generation prompt for this scene."""
        location = locations[index % len(locations)] if locations else "an unknown location"
        char_names = ", ".join(c.get("name", "") for c in characters[:3])

        return (
            f"scene {index + 1}, {location}, "
            + (f"featuring {char_names}, " if char_names else "")
            + f"manga style, detailed background, cinematic composition"
        )
