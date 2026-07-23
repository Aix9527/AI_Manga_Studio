
"""API routes for character consistency operations."""

import json
import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from backend.modules.characters.domain.identity import (
    ConsistencyCheckResult,
    IdentityDriftDetector,
)

logger = logging.getLogger(__name__)

consistency_router = APIRouter(prefix="/characters", tags=["character-consistency"])

_drift_detector = IdentityDriftDetector()


class IdentityBoardRequest(BaseModel):
    character_id: str = Field(..., description="Character ID")
    canonical_name: str = Field(...)
    gender_presentation: str = Field(...)
    age_stage: str = Field(...)
    ethnicity_style: str = Field(...)
    core_face_shape: str = Field(...)
    signature_traits: list[str] = Field(default_factory=list)


class AppearanceSheetRequest(BaseModel):
    character_id: str = Field(...)
    character_version_id: str = Field(...)
    hair_color: str = Field(...)
    hair_style: str = Field(...)
    eye_color: str = Field(...)
    build: str = Field(...)
    skin_tone: str | None = None
    height_impression: str | None = None


class DriftCheckRequest(BaseModel):
    reference: dict[str, Any] = Field(..., description="Reference appearance data")
    candidate: dict[str, Any] = Field(..., description="Candidate appearance data")
    tolerance: float = Field(default=0.3, description="Maximum allowed drift score")


class DriftCheckResponse(BaseModel):
    check_id: str
    character_id: str
    passed: bool
    drift_score: float
    discrepancies: list[dict[str, Any]]


@consistency_router.post("/identity-board", status_code=201)
async def create_identity_board(req: IdentityBoardRequest):
    import hashlib

    board_data = {
        "character_id": req.character_id,
        "canonical_name": req.canonical_name,
        "gender_presentation": req.gender_presentation,
        "age_stage": req.age_stage,
        "ethnicity_style": req.ethnicity_style,
        "core_face_shape": req.core_face_shape,
        "signature_traits": req.signature_traits,
    }
    board_hash = hashlib.sha256(json.dumps(board_data, sort_keys=True).encode()).hexdigest()[:20]

    return {
        "characterId": req.character_id,
        "boardHash": board_hash,
        "fields": {
            "identity": {
                "genderPresentation": req.gender_presentation,
                "ageStage": req.age_stage,
                "ethnicityStyle": req.ethnicity_style,
            },
            "appearance": {
                "coreFaceShape": req.core_face_shape,
                "signatureTraits": req.signature_traits,
            },
        },
    }


@consistency_router.post("/appearance-sheet", status_code=201)
async def create_appearance_sheet(req: AppearanceSheetRequest):
    import hashlib

    sheet_data = {
        "character_id": req.character_id,
        "character_version_id": req.character_version_id,
        "hair_color": req.hair_color,
        "hair_style": req.hair_style,
        "eye_color": req.eye_color,
        "build": req.build,
        "skin_tone": req.skin_tone,
        "height_impression": req.height_impression,
    }
    sheet_hash = hashlib.sha256(json.dumps(sheet_data, sort_keys=True, default=str).encode()).hexdigest()[:20]

    return {
        **sheet_data,
        "sheetHash": sheet_hash,
    }


@consistency_router.post("/drift-check", response_model=DriftCheckResponse)
async def check_identity_drift(req: DriftCheckRequest):
    try:
        result: ConsistencyCheckResult = _drift_detector.compare(
            reference=req.reference,
            candidate=req.candidate,
            tolerance=req.tolerance,
        )
        return DriftCheckResponse(
            check_id=result.check_id,
            character_id=result.character_id,
            passed=result.passed,
            drift_score=result.drift_score,
            discrepancies=[dict(d) for d in result.discrepancies],
        )
    except Exception as e:
        logger.exception("Drift check failed")
        raise HTTPException(status_code=500, detail=str(e))


@consistency_router.get("/{character_id}/identity-dna")
async def get_character_dna(character_id: str):
    return {
        "characterId": character_id,
        "dna": {
            "identityHash": "",
            "appearanceHash": "",
            "wardrobeHash": "",
            "dnaVersion": 1,
            "message": "Character DNA not yet persisted (Part 45 WIP)",
        },
    }
