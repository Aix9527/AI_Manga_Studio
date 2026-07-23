"""
Workflow Nodes — DAG node definitions (Part 12)

Predefined node types for the manga/anime production pipeline:

    NovelInputNode      — Load and parse novel text
    StoryParserNode     — Parse novel into structured story
    CharacterAgentNode  — Extract/design characters
    SceneAgentNode      — Break story into scenes
    StoryboardNode      — Generate storyboard with shots
    ImageGenNode        — Generate keyframe images
    VideoGenNode        — Generate animated video clips
    AudioGenNode        — Generate voice / SFX / BGM
    CompositorNode     — Compose final output
    ExportNode          — Export to target format
    ReviewNode          — Human-in-the-loop review gate
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Coroutine, Generic, TypeVar

logger = __import__("logging").getLogger(__name__)

T = TypeVar("T")


class NodeStatus(str, Enum):
    """Execution status of a DAG node."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"
    CANCELLED = "cancelled"


class NodeCategory(str, Enum):
    """Category classification for nodes."""
    INPUT = "input"
    PARSING = "parsing"
    AGENT = "agent"
    GENERATION = "generation"
    COMPOSITING = "compositing"
    EXPORT = "export"
    REVIEW = "review"
    UTILITY = "utility"


@dataclass
class ResourceRequirements:
    """Resource requirements for a node."""
    gpu_memory_mb: int = 0
    cpu_cores: int = 1
    ram_mb: int = 512
    estimated_duration_seconds: float = 10.0


@dataclass
class NodeConfig:
    """Configuration for a specific node instance."""
    node_id: str
    node_type: str
    name: str = ""
    category: NodeCategory = NodeCategory.UTILITY
    resources: ResourceRequirements = field(default_factory=ResourceRequirements)
    timeout_seconds: float = 300.0
    allow_retry: bool = True
    max_retries: int = 3
    compensation_type: str = ""  # Type key for RollbackManager
    metadata: dict[str, Any] = field(default_factory=dict)


# ── Base Node ──────────────────────────────────────────────────────────


class BaseNode(ABC, Generic[T]):
    """
    Abstract base for all DAG nodes.

    Each node implements:
    - execute(): Run the node's core logic
    - validate(): Validate inputs before execution (optional override)
    - compensate(): Rollback/cleanup (optional override)
    """

    def __init__(self, config: NodeConfig) -> None:
        self.config = config
        self._status = NodeStatus.PENDING
        self._output: T | None = None
        self._error: str = ""
        self._progress: float = 0.0

    @property
    def status(self) -> NodeStatus:
        return self._status

    @property
    def output(self) -> T | None:
        return self._output

    @property
    def error(self) -> str:
        return self._error

    @property
    def progress(self) -> float:
        return self._progress

    async def run(self, inputs: dict[str, Any]) -> T:
        """
        Execute the node with status tracking.

        Calls validate() -> execute() with status transitions.
        Compensation is left to the RollbackManager to call separately.
        """
        self._status = NodeStatus.RUNNING
        logger.info(f"Node '{self.config.name}' ({self.config.node_id}) started")

        try:
            # Validate inputs
            await self.validate(inputs)

            # Execute core logic
            result = await self.execute(inputs)
            self._output = result
            self._status = NodeStatus.COMPLETED
            self._progress = 1.0
            logger.info(f"Node '{self.config.name}' completed")
            return result

        except Exception as e:
            self._status = NodeStatus.FAILED
            self._error = str(e)
            logger.error(f"Node '{self.config.name}' failed: {e}", exc_info=True)
            raise

    async def validate(self, inputs: dict[str, Any]) -> None:
        """Validate input data. Override in subclasses. Default: pass."""
        pass

    @abstractmethod
    async def execute(self, inputs: dict[str, Any]) -> T:
        """Core node logic. Must be implemented by subclasses."""
        ...

    async def compensate(self) -> None:
        """Compensation/rollback. Override in subclasses as needed. Default: no-op."""
        logger.debug(f"No compensation defined for '{self.config.name}'")
        pass

    def to_dict(self) -> dict[str, Any]:
        """Serialize node state for checkpointing."""
        return {
            "node_id": self.config.node_id,
            "node_type": self.config.node_type,
            "name": self.config.name,
            "status": self._status.value,
            "progress": self._progress,
            "error": self._error,
        }


# ── Concrete Nodes ─────────────────────────────────────────────────────


class NovelInputNode(BaseNode[str]):
    """Input node: loads novel text from source."""

    async def execute(self, inputs: dict[str, Any]) -> str:
        novel_text = inputs.get("novel_text", "")
        novel_path = inputs.get("novel_path", "")
        if novel_path:
            with open(novel_path, "r", encoding="utf-8") as f:
                return f.read()
        if not novel_text:
            raise ValueError("No novel text or path provided")
        return novel_text


class StoryParserNode(BaseNode[dict[str, Any]]):
    """Parses novel text into structured story (chapters, scenes, etc.)."""

    async def execute(self, inputs: dict[str, Any]) -> dict[str, Any]:
        novel_text = inputs.get("novel_text", "")
        if not novel_text:
            raise ValueError("No novel text to parse")

        # In production, calls StoryAgent via LLM
        return {
            "title": "Parsed Story",
            "chapters": [],
            "characters_mentioned": [],
            "estimated_total_scenes": 0,
            "raw_length_chars": len(novel_text),
        }


class CharacterAgentNode(BaseNode[list[dict[str, Any]]]):
    """Extracts and designs characters."""

    async def execute(self, inputs: dict[str, Any]) -> list[dict[str, Any]]:
        story = inputs.get("story", {})
        characters_mentioned = story.get("characters_mentioned", [])
        if not characters_mentioned:
            return []

        # In production, calls CharacterAgent via LLM
        characters = []
        for name in characters_mentioned:
            characters.append({
                "name": name,
                "role": "supporting",
                "appearance": "",
                "personality": "",
            })
        return characters


class SceneAgentNode(BaseNode[list[dict[str, Any]]]):
    """Breaks story into individual scenes."""

    async def execute(self, inputs: dict[str, Any]) -> list[dict[str, Any]]:
        story = inputs.get("story", {})
        # In production, calls SceneAgent via LLM
        return [
            {
                "scene_number": 1,
                "chapter_number": 1,
                "description": "",
                "location": "",
                "time_of_day": "",
                "mood": "",
                "characters_present": [],
            }
        ]


class StoryboardNode(BaseNode[list[dict[str, Any]]]):
    """Generates storyboard with shot details."""

    async def execute(self, inputs: dict[str, Any]) -> list[dict[str, Any]]:
        scenes = inputs.get("scenes", [])
        characters = inputs.get("characters", [])

        shots = []
        for i, scene in enumerate(scenes):
            shots.append({
                "shot_number": i + 1,
                "scene_reference": scene.get("scene_number", 0),
                "description": scene.get("description", ""),
                "camera_angle": "medium",
                "duration_frames": 72,
                "characters": characters,
            })
        return shots


class ImageGenNode(BaseNode[dict[str, Any]]):
    """Generates keyframe images for shots."""

    async def execute(self, inputs: dict[str, Any]) -> dict[str, Any]:
        shot = inputs.get("shot", {})
        prompt = inputs.get("prompt", shot.get("description", ""))

        if not prompt:
            raise ValueError("No prompt available for image generation")

        # In production, calls ImageProvider
        return {
            "shot_number": shot.get("shot_number", 0),
            "prompt": prompt,
            "asset_path": "",
            "width": 1024,
            "height": 1024,
            "seed": 42,
            "status": "generated",
        }


class VideoGenNode(BaseNode[dict[str, Any]]):
    """Generates animated video clips from keyframes."""

    async def execute(self, inputs: dict[str, Any]) -> dict[str, Any]:
        image_result = inputs.get("image_result", {})
        image_path = image_result.get("asset_path", "")
        if not image_path:
            raise ValueError("No image path for video generation")

        # In production, calls VideoProvider (I2V)
        return {
            "shot_number": image_result.get("shot_number", 0),
            "source_image": image_path,
            "video_asset_path": "",
            "duration_seconds": 3.0,
            "fps": 24,
            "status": "generated",
        }


class AudioGenNode(BaseNode[dict[str, Any]]):
    """Generates voice, SFX, or BGM."""

    async def execute(self, inputs: dict[str, Any]) -> dict[str, Any]:
        audio_type = inputs.get("audio_type", "voice")
        text = inputs.get("text", "")
        character_id = inputs.get("character_id", "")

        # In production, routes to ElevenLabs / Fish Audio / etc.
        return {
            "audio_type": audio_type,
            "audio_path": "",
            "duration_seconds": 0.0,
            "character_id": character_id,
            "status": "generated",
        }


class CompositorNode(BaseNode[dict[str, Any]]):
    """Composes video, audio, effects into final output."""

    async def execute(self, inputs: dict[str, Any]) -> dict[str, Any]:
        video_clips = inputs.get("video_clips", [])
        audio_tracks = inputs.get("audio_tracks", [])

        # In production, calls Exporter/Compositor
        return {
            "composed_path": "",
            "duration_seconds": sum(v.get("duration_seconds", 0) for v in video_clips),
            "video_count": len(video_clips),
            "audio_count": len(audio_tracks),
            "status": "composed",
        }


class ExportNode(BaseNode[dict[str, Any]]):
    """Exports final composed output to target format."""

    async def execute(self, inputs: dict[str, Any]) -> dict[str, Any]:
        composed = inputs.get("composed", {})
        output_format = inputs.get("output_format", "mp4")

        # In production, calls ExportOrchestrator
        return {
            "export_path": f"output/export.{output_format}",
            "format": output_format,
            "file_size_bytes": 0,
            "status": "exported",
        }


class ReviewNode(BaseNode[dict[str, Any]]):
    """Human-in-the-loop review gate."""

    async def validate(self, inputs: dict[str, Any]) -> None:
        if not inputs.get("target_id"):
            raise ValueError("Review target_id is required")

    async def execute(self, inputs: dict[str, Any]) -> dict[str, Any]:
        # In production, this would pause the workflow and wait for
        # human approval through the API/UI.
        auto_approve = inputs.get("auto_approve", False)

        return {
            "target_id": inputs["target_id"],
            "target_type": inputs.get("target_type", "shot"),
            "decision": "approved" if auto_approve else "pending",
            "reviewer_notes": inputs.get("notes", ""),
        }


# ── Node Registry ──────────────────────────────────────────────────────


# Maps node_type strings to node classes
NODE_REGISTRY: dict[str, type[BaseNode]] = {
    "novel_input": NovelInputNode,
    "story_parser": StoryParserNode,
    "character_agent": CharacterAgentNode,
    "scene_agent": SceneAgentNode,
    "storyboard": StoryboardNode,
    "image_gen": ImageGenNode,
    "video_gen": VideoGenNode,
    "audio_gen": AudioGenNode,
    "compositor": CompositorNode,
    "export": ExportNode,
    "review": ReviewNode,
}


def create_node(node_type: str, node_id: str, name: str = "", category: NodeCategory | None = None, **kwargs: Any) -> BaseNode:
    """
    Factory function to create a node by type.

    Args:
        node_type: Type key from NODE_REGISTRY.
        node_id: Unique node identifier.
        name: Human-readable node name.
        category: Node category (auto-detected if not provided).
        **kwargs: Additional fields passed to NodeConfig.

    Returns:
        An instance of the corresponding BaseNode subclass.

    Raises:
        ValueError: If node_type is not found in registry.
    """
    node_cls = NODE_REGISTRY.get(node_type)
    if node_cls is None:
        raise ValueError(
            f"Unknown node type: '{node_type}'. Available: {list(NODE_REGISTRY.keys())}"
        )

    if category is None:
        # Auto-detect category based on naming convention
        if "input" in node_type:
            category = NodeCategory.INPUT
        elif "parser" in node_type:
            category = NodeCategory.PARSING
        elif "agent" in node_type:
            category = NodeCategory.AGENT
        elif "gen" in node_type:
            category = NodeCategory.GENERATION
        elif "compositor" in node_type:
            category = NodeCategory.COMPOSITING
        elif "export" in node_type:
            category = NodeCategory.EXPORT
        elif "review" in node_type:
            category = NodeCategory.REVIEW

    config = NodeConfig(
        node_id=node_id,
        node_type=node_type,
        name=name or node_type,
        category=category or NodeCategory.UTILITY,
        **kwargs,
    )

    return node_cls(config)
