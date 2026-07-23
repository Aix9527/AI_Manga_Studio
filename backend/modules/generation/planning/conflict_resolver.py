
"""Prompt conflict detection and resolution."""

from dataclasses import dataclass
from typing import Any


class ConflictType:
    IDENTITY = "identity"
    WARDROBE = "wardrobe"
    SCENE = "scene"
    CAMERA = "camera"
    STYLE = "style"
    CONTINUITY = "continuity"
    SAFETY = "safety"
    PARAMETER = "parameter"
    REFERENCE = "reference"


@dataclass(frozen=True, slots=True)
class ResolvedValueSource:
    key: str
    value: Any
    source_type: str
    source_id: str
    priority: int


class ConflictResolver:
    """Resolves conflicts between prompt sources based on priority."""

    IDENTITY_PRIORITY = 850
    SHOT_PRIORITY = 800
    USER_HARD_PRIORITY = 900
    USER_SOFT_PRIORITY = 300

    IDENTITY_KEYS = frozenset({
        "hair.color", "eye.color", "identity.genderPresentation",
        "identity.ageStage", "appearance.faceShape",
        "identity.signature_trait", "signature_trait",
    })

    def detect_conflicts(
        self,
        character_sources: list[dict[str, Any]],
        user_overrides: dict[str, Any],
        shot_constraints: dict[str, Any],
    ) -> list[dict[str, Any]]:
        conflicts: list[dict[str, Any]] = []

        for key, user_val in user_overrides.items():
            for cs in character_sources:
                char_val = self._get_nested(cs, key)
                if char_val is not None and char_val != user_val:
                    if key in self.IDENTITY_KEYS:
                        conflicts.append({
                            "conflictId": f"identity-{key}",
                            "conflictType": ConflictType.IDENTITY,
                            "key": key,
                            "existingValue": char_val,
                            "incomingValue": user_val,
                            "existingSourceId": f"character:{cs.get('characterId')}",
                            "incomingSourceId": "user",
                            "resolution": "keep_higher_priority",
                            "selectedValue": char_val,
                            "requiresUserAction": True,
                        })

        for key, shot_val in shot_constraints.items():
            for cs in character_sources:
                char_val = self._get_nested(cs, key)
                if char_val is not None and char_val != shot_val:
                    if key.startswith("camera"):
                        conflicts.append({
                            "conflictId": f"camera-{key}",
                            "conflictType": ConflictType.CAMERA,
                            "key": key,
                            "existingValue": shot_val,
                            "incomingValue": char_val,
                            "existingSourceId": "shot",
                            "incomingSourceId": f"character:{cs.get('characterId')}",
                            "resolution": "keep_higher_priority",
                            "selectedValue": shot_val,
                            "requiresUserAction": True,
                        })

        return conflicts

    @staticmethod
    def _get_nested(data: dict[str, Any], key: str) -> Any:
        parts = key.split(".")
        current = data
        for part in parts:
            if isinstance(current, dict):
                current = current.get(part)
            else:
                return None
        return current
