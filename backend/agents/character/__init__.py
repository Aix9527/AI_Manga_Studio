"""
Character Agent (Part 9)

Creates, refines, and maintains character definitions throughout
the production pipeline. Generates consistent character profiles
including appearance, personality, backstory, and visual references.

Key responsibilities:
- Character extraction and creation from story analysis
- Identity consistency across scenes and shots
- Visual reference generation / prompt construction
- Character relationship mapping
"""

from __future__ import annotations

from typing import Any

from backend.agents.base_agent import (
    BaseAgent,
    AgentContext,
    AgentResult,
    AgentStatus,
)


class CharacterAgent(BaseAgent[AgentResult]):
    """
    Character creation and management agent.

    Input: Story analysis output + optional character hints
    Output: Structured character profiles

    Capabilities:
    - Character extraction from story
    - Identity generation (appearance, personality, backstory)
    - Visual prompt construction
    - Relationship graph generation
    """

    def __init__(
        self,
        agent_id: str = "character_agent",
        agent_type: str = "character",
    ) -> None:
        super().__init__(agent_id=agent_id, agent_type=agent_type)
        self.capabilities = [
            "character_extraction",
            "identity_generation",
            "visual_prompt_construction",
            "relationship_graph",
        ]

    async def _execute_impl(
        self, context: AgentContext, **kwargs: Any
    ) -> AgentResult:
        """
        Generate character profiles from story analysis.

        Args:
            characters_mentioned: List of character names from StoryAgent
            story_context: Parsed story structure
            style: Art style preference (anime, realistic, etc.)

        Returns:
            AgentResult with list of character profiles
        """
        characters_mentioned = kwargs.get("characters_mentioned", [])
        story_context = kwargs.get("story_context", {})
        style = kwargs.get("style", "anime")

        profiles = []
        for i, name in enumerate(characters_mentioned[:20]):  # Limit for MVP
            profile = self._generate_profile(name, i, style, story_context)
            profiles.append(profile)

        return AgentResult(
            agent_id=self.agent_id,
            agent_type=self.agent_type,
            status=AgentStatus.COMPLETED,
            output={
                "characters": profiles,
                "character_count": len(profiles),
                "relationships": self._build_relationship_graph(profiles),
                "style": style,
            },
        )

    @classmethod
    def input_schema(cls) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "characters_mentioned": {
                    "type": "array",
                    "items": {"type": "string"},
                },
                "story_context": {"type": "object"},
                "style": {"type": "string"},
            },
            "required": ["characters_mentioned"],
        }

    @classmethod
    def output_schema(cls) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "characters": {"type": "array"},
                "character_count": {"type": "integer"},
                "relationships": {"type": "array"},
            },
        }

    # ── Internal methods ─────────────────────────────────────

    def _generate_profile(
        self,
        name: str,
        index: int,
        style: str,
        story_context: dict[str, Any],
    ) -> dict[str, Any]:
        """Generate a character profile from name and context."""
        roles = ["protagonist", "antagonist", "supporting", "mentor", "rival", "sidekick"]
        role = roles[index % len(roles)] if index < 6 else "supporting"

        return {
            "character_id": f"char_{index:03d}",
            "name": name,
            "role": role,
            "archetype": role,
            "appearance": self._generate_appearance(name, role, style),
            "personality": self._generate_personality(name, role),
            "backstory": f"{name}的背景故事待展开。",
            "visual_prompt": self._build_visual_prompt(name, role, style),
            "voice_profile": "",
            "reference_keywords": [name, role, style],
        }

    def _generate_appearance(
        self, name: str, role: str, style: str
    ) -> str:
        """Generate character appearance description."""
        appearances = {
            "protagonist": "主角外观：中等身材，目光坚定，穿着与故事背景相符的服装。",
            "antagonist": "反派外观：气场强大，面容冷峻，服饰设计突出压迫感。",
            "supporting": "配角外观：特征鲜明的辅助角色，与主角形成互补。",
            "mentor": "导师外观：年长者气质，衣着朴素但有智慧感。",
        }
        return appearances.get(role, f"{name}的详细外观待设定。")

    def _generate_personality(self, name: str, role: str) -> str:
        """Generate personality traits based on role."""
        traits = {
            "protagonist": "勇敢、执着、有成长弧光",
            "antagonist": "强大、复杂、有自身逻辑",
            "supporting": "忠诚、有特色、推动剧情",
            "mentor": "智慧、耐心、关键时刻引导",
        }
        return traits.get(role, "性格待设定")

    def _build_visual_prompt(
        self, name: str, role: str, style: str
    ) -> str:
        """Build a visual generation prompt for this character."""
        return (
            f"({style} style), character portrait of {name}, "
            f"{role} type, detailed features, consistent design, "
            f"reference sheet, multiple angles, white background"
        )

    def _build_relationship_graph(
        self, profiles: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """Build a simple relationship graph between characters."""
        relationships = []
        for i, p1 in enumerate(profiles):
            for j, p2 in enumerate(profiles):
                if i >= j:
                    continue
                relationships.append({
                    "source": p1["name"],
                    "target": p2["name"],
                    "type": "associated" if abs(i - j) <= 2 else "distant",
                })
        return relationships
