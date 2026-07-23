
"""Character identity and consistency domain models."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


class IdentityFieldLevel:
    IMMUTABLE = "immutable"
    STABLE = "stable"
    SCENE_DEPENDENT = "scene_dependent"
    OPTIONAL = "optional"


@dataclass(frozen=True, slots=True)
class IdentityBoard:
    """Frozen character identity - the immutable core."""
    character_id: str
    canonical_name: str
    gender_presentation: str
    age_stage: str
    ethnicity_style: str
    core_face_shape: str
    signature_traits: tuple[str, ...]
    board_hash: str


@dataclass(frozen=True, slots=True)
class AppearanceSheet:
    """Stable appearance attributes."""
    character_id: str
    character_version_id: str
    hair_color: str
    hair_style: str
    eye_color: str
    build: str
    skin_tone: str | None
    height_impression: str | None
    sheet_hash: str


@dataclass(frozen=True, slots=True)
class ExpressionSheet:
    """Catalog of approved expressions."""
    character_id: str
    character_version_id: str
    entries: tuple[dict[str, Any], ...]
    sheet_hash: str


@dataclass(frozen=True, slots=True)
class ActionSheet:
    """Catalog of approved actions/poses."""
    character_id: str
    character_version_id: str
    entries: tuple[dict[str, Any], ...]
    sheet_hash: str


@dataclass(frozen=True, slots=True)
class WardrobeSet:
    wardrobe_id: str
    character_id: str
    name: str
    garments: tuple[dict[str, Any], ...]
    accessories: tuple[dict[str, Any], ...]
    variants: tuple[dict[str, Any], ...]
    set_hash: str


@dataclass(frozen=True, slots=True)
class ConsistencyCheckResult:
    check_id: str
    character_id: str
    shot_id: str
    asset_version_id: str
    passed: bool
    drift_score: float
    discrepancies: tuple[dict[str, Any], ...]
    checked_at: datetime
    reference_asset_version_id: str | None
    used_reference_hashes: tuple[str, ...]


class IdentityDriftDetector:
    """Detects identity drift across generated assets."""

    IDENTITY_FIELDS = frozenset({
        "hair_color", "hair_style", "eye_color", "face_shape",
        "build", "skin_tone", "signature_trait",
    })

    def compare(
        self,
        reference: dict[str, Any],
        candidate: dict[str, Any],
        tolerance: float = 0.3,
    ) -> ConsistencyCheckResult:
        discrepancies: list[dict[str, Any]] = []
        total_fields = 0
        drifted_fields = 0

        for field in self.IDENTITY_FIELDS:
            ref_val = reference.get(field)
            cand_val = candidate.get(field)
            total_fields += 1

            if ref_val is not None and cand_val is not None and ref_val != cand_val:
                drifted_fields += 1
                discrepancies.append({
                    "field": field,
                    "referenceValue": ref_val,
                    "candidateValue": cand_val,
                    "severity": "high" if field in ("hair_color", "eye_color", "signature_trait") else "medium",
                })

        drift_score = drifted_fields / max(total_fields, 1)
        passed = drift_score <= tolerance

        return ConsistencyCheckResult(
            check_id=f"cc-{reference.get('character_id', 'unknown')}-{candidate.get('asset_version_id', 'unknown')}",
            character_id=str(reference.get("character_id", "")),
            shot_id=str(candidate.get("shot_id", "")),
            asset_version_id=str(candidate.get("asset_version_id", "")),
            passed=passed,
            drift_score=drift_score,
            discrepancies=tuple(discrepancies),
            checked_at=datetime.utcnow(),
            reference_asset_version_id=reference.get("asset_version_id"),
            used_reference_hashes=(reference.get("appearance_hash", ""),),
        )


@dataclass(frozen=True, slots=True)
class CharacterDNA:
    """Encoded character identity for cross-shot consistency."""
    character_id: str
    identity_hash: str
    appearance_hash: str
    wardrobe_hash: str
    expression_hash: str
    action_hash: str
    dna_version: int = 1
    frozen_at: datetime = field(default_factory=lambda: datetime.utcnow())

    def combined_hash(self) -> str:
        import hashlib
        parts = f"{self.identity_hash}|{self.appearance_hash}|{self.wardrobe_hash}|{self.dna_version}"
        return hashlib.sha256(parts.encode()).hexdigest()[:20]
