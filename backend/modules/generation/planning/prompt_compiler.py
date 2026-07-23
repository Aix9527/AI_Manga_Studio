
"""Prompt compiler - structured assembly from sources."""

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class PromptNode:
    node_type: str
    key: str
    value: Any
    weight: float = 1.0
    required: bool = False
    negative: bool = False
    source_id: str | None = None
    source_priority: int = 0
    tags: frozenset[str] = frozenset()


@dataclass(frozen=True, slots=True)
class CharacterSnapshot:
    character_id: str
    character_version_id: str
    canonical_name: str
    identity: dict[str, Any]
    appearance: dict[str, Any]
    signature_traits: tuple[str, ...]
    negative_identity_traits: tuple[str, ...]
    snapshot_hash: str


@dataclass(frozen=True, slots=True)
class SceneSnapshot:
    scene_id: str
    location_name: str
    time_of_day: str | None
    weather: str | None
    season: str | None
    environment_description: str
    spatial_anchors: tuple[str, ...]
    key_props: tuple[str, ...]
    lighting_state: str | None
    snapshot_hash: str


@dataclass(frozen=True, slots=True)
class CanonicalPrompt:
    subjects: tuple[PromptNode, ...]
    environment: tuple[PromptNode, ...]
    actions: tuple[PromptNode, ...]
    camera: tuple[PromptNode, ...]
    lighting: tuple[PromptNode, ...]
    style: tuple[PromptNode, ...]
    quality: tuple[PromptNode, ...]
    constraints: tuple[PromptNode, ...]
    negatives: tuple[PromptNode, ...]
    provenance: tuple[dict[str, Any], ...]


@dataclass(frozen=True, slots=True)
class PromptCompilationResult:
    canonical_prompt: CanonicalPrompt
    positive_prompt: str
    negative_prompt: str
    provenance: tuple[dict[str, Any], ...]
    conflicts: tuple[dict[str, Any], ...]
    warnings: tuple[str, ...]
    prompt_hash: str


class PromptCompiler:
    """Compiles structured sources into a canonical prompt and text."""

    COMPILER_VERSION = "1.0.0"

    def compile(
        self,
        character_snapshots: list[CharacterSnapshot],
        scene_snapshot: SceneSnapshot | None,
        shot_snapshot: dict[str, Any] | None,
        user_instruction: str | None,
        style_fragments: tuple[str, ...] = (),
        quality_fragments: tuple[str, ...] = (),
    ) -> PromptCompilationResult:
        subjects: list[PromptNode] = []
        environment_nodes: list[PromptNode] = []
        action_nodes: list[PromptNode] = []
        camera_nodes: list[PromptNode] = []
        lighting_nodes: list[PromptNode] = []
        style_nodes: list[PromptNode] = []
        quality_nodes: list[PromptNode] = []
        constraint_nodes: list[PromptNode] = []
        negative_nodes: list[PromptNode] = []
        provenance: list[dict[str, Any]] = []

        # Inject characters
        for cs in character_snapshots:
            self._inject_character(cs, subjects, negative_nodes, provenance)

        # Inject scene
        if scene_snapshot:
            self._inject_scene(scene_snapshot, environment_nodes, lighting_nodes, provenance)

        # Inject shot
        if shot_snapshot:
            self._inject_shot(shot_snapshot, action_nodes, camera_nodes, provenance)

        # Inject user instruction
        if user_instruction:
            self._inject_user(user_instruction, subjects, provenance)

        # Inject style
        for frag in style_fragments:
            style_nodes.append(PromptNode("style", "visual_style", frag, source_priority=450))

        # Inject quality
        for frag in quality_fragments:
            quality_nodes.append(PromptNode("quality", "quality_enhancer", frag, source_priority=100))

        canonical = CanonicalPrompt(
            subjects=tuple(subjects),
            environment=tuple(environment_nodes),
            actions=tuple(action_nodes),
            camera=tuple(camera_nodes),
            lighting=tuple(lighting_nodes),
            style=tuple(style_nodes),
            quality=tuple(quality_nodes),
            constraints=tuple(constraint_nodes),
            negatives=tuple(negative_nodes),
            provenance=tuple(provenance),
        )

        positive_text = self._compile_text(canonical, negative=False)
        negative_text = self._compile_text(canonical, negative=True)

        prompt_hash = self._compute_hash(positive_text, negative_text)

        return PromptCompilationResult(
            canonical_prompt=canonical,
            positive_prompt=positive_text,
            negative_prompt=negative_text,
            provenance=tuple(provenance),
            conflicts=(),
            warnings=(),
            prompt_hash=prompt_hash,
        )

    def _inject_character(
        self,
        cs: CharacterSnapshot,
        subjects: list[PromptNode],
        negatives: list[PromptNode],
        provenance: list[dict[str, Any]],
    ) -> None:
        src_id = f"character:{cs.character_id}:v{cs.character_version_id}"
        # Identity
        for key, value in cs.identity.items():
            node = PromptNode("identity", key, value, required=True, source_priority=850, source_id=src_id)
            subjects.append(node)
            provenance.append({"output_key": f"character.{key}", "output_value": value,
                              "source_type": "character_snapshot", "source_id": cs.character_id,
                              "source_version": cs.character_version_id})

        # Appearance
        for key, value in cs.appearance.items():
            if isinstance(value, dict):
                for subkey, subval in value.items():
                    node = PromptNode("appearance", f"{key}.{subkey}", subval, required=True,
                                      source_priority=850, source_id=src_id)
                    subjects.append(node)
            else:
                node = PromptNode("appearance", key, value, required=True, source_priority=850, source_id=src_id)
                subjects.append(node)

        # Signature traits
        for trait in cs.signature_traits:
            node = PromptNode("identity", "signature_trait", trait, required=True, source_priority=850, source_id=src_id)
            subjects.append(node)

        # Negative identity traits
        for nt in cs.negative_identity_traits:
            node = PromptNode("constraint", "negative_identity", nt, required=True, negative=True,
                              source_priority=850, source_id=src_id)
            negatives.append(node)

    def _inject_scene(
        self,
        ss: SceneSnapshot,
        environment: list[PromptNode],
        lighting: list[PromptNode],
        provenance: list[dict[str, Any]],
    ) -> None:
        src_id = f"scene:{ss.scene_id}"
        if ss.environment_description:
            environment.append(PromptNode("environment", "description", ss.environment_description,
                                          source_priority=550, source_id=src_id))
        if ss.location_name:
            environment.append(PromptNode("environment", "location", ss.location_name,
                                          source_priority=550, source_id=src_id))
        if ss.time_of_day:
            lighting.append(PromptNode("lighting", "time_of_day", ss.time_of_day,
                                       source_priority=500, source_id=src_id))
        if ss.weather:
            lighting.append(PromptNode("lighting", "weather", ss.weather,
                                       source_priority=500, source_id=src_id))
        for prop in ss.key_props:
            environment.append(PromptNode("environment", "key_prop", prop,
                                          source_priority=500, source_id=src_id))

    def _inject_shot(
        self,
        shot: dict[str, Any],
        actions: list[PromptNode],
        camera: list[PromptNode],
        provenance: list[dict[str, Any]],
    ) -> None:
        src_id = f"shot:{shot.get('shotId', 'unknown')}"
        if shot.get("action"):
            actions.append(PromptNode("action", "shot_action", shot["action"],
                                      source_priority=800, source_id=src_id))
        if shot.get("framing"):
            camera.append(PromptNode("camera", "framing", shot["framing"],
                                     source_priority=600, source_id=src_id))
        if shot.get("cameraAngle"):
            camera.append(PromptNode("camera", "angle", shot["cameraAngle"],
                                     source_priority=600, source_id=src_id))
        if shot.get("cameraMotion"):
            camera.append(PromptNode("camera", "motion", shot["cameraMotion"],
                                     source_priority=600, source_id=src_id))

    def _inject_user(self, instruction: str, subjects: list[PromptNode], provenance: list[dict[str, Any]]) -> None:
        node = PromptNode("instruction", "user_input", instruction, required=False,
                          source_priority=300, source_id="user")
        subjects.append(node)

    def _compile_text(self, canonical: CanonicalPrompt, *, negative: bool) -> str:
        if negative:
            nodes = canonical.negatives
        else:
            nodes = (
                canonical.subjects + canonical.environment + canonical.actions +
                canonical.camera + canonical.lighting + canonical.style + canonical.quality +
                canonical.constraints
            )
            nodes = tuple(n for n in nodes if not n.negative)

        return ", ".join(str(n.value) for n in nodes if n.value)

    def _compute_hash(self, positive: str, negative: str) -> str:
        import hashlib
        digest = hashlib.sha256(f"{positive}|{negative}|{self.COMPILER_VERSION}".encode()).hexdigest()[:12]
        return digest
