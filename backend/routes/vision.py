"""
Vision Routes — Sprint 7.1 API endpoints for Vision Intelligence Layer.

Endpoints:
- POST /api/vision/analyze         — Analyze a single generated image
- POST /api/vision/analyze-batch   — Analyze multiple images
- POST /api/vision/score           — Score a panel against specifications
- POST /api/vision/feedback        — Generate prompt rewrite from quality report
- GET  /api/vision/health          — Vision module health check
"""

from __future__ import annotations

from threading import Lock
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from backend.vision import ImageAnalyzer, QualityScorer, FeedbackLoop
from backend.vision.image_analyzer import ImageProfile
from backend.vision.quality_score import QualityReport
from backend.vision.feedback import PromptFeedback
from backend.vision.consistency_check import ConsistencyReport, StyleDriftReport
from backend.pipeline.schemas import PipelineResponse, PipelineStage, StageResult

router = APIRouter(prefix="/api/vision", tags=["vision"])

# Heavy vision dependencies are initialized only by analysis requests. Health checks
# and application startup must stay lightweight.
_analyzer: ImageAnalyzer | None = None
_scorer: QualityScorer | None = None
_analyzer_lock = Lock()
_scorer_lock = Lock()
_feedback = FeedbackLoop(max_retries=2)


def _get_analyzer() -> ImageAnalyzer:
    global _analyzer
    if _analyzer is None:
        with _analyzer_lock:
            if _analyzer is None:
                _analyzer = ImageAnalyzer()
    return _analyzer


def _get_scorer() -> QualityScorer:
    global _scorer
    if _scorer is None:
        with _scorer_lock:
            if _scorer is None:
                _scorer = QualityScorer(pass_threshold=0.65)
    return _scorer


# ── Request/Response models ────────────────────────────────────

class AnalyzeRequest(BaseModel):
    image_path: str = Field(..., description="Absolute path to generated image")

class BatchAnalyzeRequest(BaseModel):
    image_paths: list[str] = Field(..., description="List of absolute image paths", min_length=1, max_length=50)

class ScoreRequest(BaseModel):
    image_path: str = Field(..., description="Path to generated image")
    shot_id: str = Field("", description="Shot ID for reference")
    shot_type: str = Field("medium", description="Expected shot type")
    camera_angle: str = Field("", description="Expected camera angle")
    emotion: str = Field("", description="Expected emotion")
    action: str = Field("", description="Expected action description")
    character_ids: list[str] = Field(default_factory=list)
    reference_path: Optional[str] = Field(None, description="Reference image for consistency comparison")

class FeedbackRequest(BaseModel):
    shot_id: str
    original_prompt: str
    original_negative: str = ""
    iteration: int = 0
    image_path: str = ""
    shot_type: str = "medium"
    camera_angle: str = ""
    emotion: str = ""
    action: str = ""
    character_ids: list[str] = Field(default_factory=list)


# ── Routes ─────────────────────────────────────────────────────

@router.post("/analyze")
async def analyze_image(req: AnalyzeRequest) -> dict:
    """Analyze a single generated image and return its profile."""
    profile: ImageProfile = _get_analyzer().analyze(req.image_path)

    return {
        "image_path": profile.image_path,
        "image_hash": profile.image_hash,
        "aesthetic_score": profile.aesthetic_score,
        "content_tags": profile.content_tags,
        "composition_type": profile.composition_type,
        "rule_of_thirds": profile.rule_of_thirds,
        "subject_centered": profile.subject_centered,
        "depth_perceived": profile.depth_perceived,
        "sharpness": profile.sharpness,
        "exposure": profile.exposure,
        "color_harmony": profile.color_harmony,
        "character_count": profile.character_count,
        "faces_detected": profile.faces_detected,
    }


@router.post("/analyze-batch")
async def analyze_batch(req: BatchAnalyzeRequest) -> list[dict]:
    """Analyze multiple images in batch."""
    profiles = _get_analyzer().batch_analyze(req.image_paths)
    return [
        {
            "image_path": p.image_path,
            "aesthetic_score": p.aesthetic_score,
            "content_tags": p.content_tags[:10],
            "composition_type": p.composition_type,
            "sharpness": p.sharpness,
        }
        for p in profiles
    ]


@router.post("/score")
async def score_panel(req: ScoreRequest) -> dict:
    """Score a generated panel against specifications."""
    analyzer = _get_analyzer()
    profile = analyzer.analyze(req.image_path)

    ref_profile = None
    if req.reference_path:
        ref_profile = analyzer.analyze(req.reference_path)

    shot_spec = {
        "shot_id": req.shot_id,
        "shot_type": req.shot_type,
        "camera_angle": req.camera_angle,
        "emotion": req.emotion,
        "action": req.action,
        "character_ids": req.character_ids,
    }

    report: QualityReport = _get_scorer().score(profile, shot_spec, ref_profile)

    return {
        "shot_id": report.shot_id,
        "overall_score": report.overall_score,
        "composition_score": report.composition_score,
        "style_consistency": report.style_consistency,
        "character_consistency": report.character_consistency,
        "expression_match": report.expression_match,
        "camera_match": report.camera_match,
        "technical_quality": report.technical_quality,
        "passed": report.passed,
        "issues": report.issues,
        "suggestions": report.suggestions,
    }


@router.post("/feedback")
async def generate_feedback(req: FeedbackRequest) -> dict:
    """Generate prompt rewrite from quality assessment."""
    profile = _get_analyzer().analyze(req.image_path)

    shot_spec = {
        "shot_id": req.shot_id,
        "shot_type": req.shot_type,
        "camera_angle": req.camera_angle,
        "emotion": req.emotion,
        "action": req.action,
        "character_ids": req.character_ids,
    }

    report = _get_scorer().score(profile, shot_spec)
    result: PromptFeedback = _feedback.generate_feedback(
        report,
        req.original_prompt,
        req.original_negative,
        req.iteration,
    )

    return {
        "shot_id": result.shot_id,
        "original_prompt": result.original_prompt,
        "rewritten_prompt": result.rewritten_prompt,
        "rewritten_negative": result.rewritten_negative,
        "score_before": result.score_before,
        "iteration": result.iteration,
        "should_retry": result.should_retry,
        "actions": [
            {"type": a.action_type, "target": a.target, "value": a.value}
            for a in result.actions
        ],
    }


@router.get("/health")
async def vision_health():
    """Vision module health check."""
    return {
        "module": "vision",
        "status": "healthy",
        "analyzer_initialized": _analyzer is not None,
        "scorer_initialized": _scorer is not None,
        "clip_available": _analyzer._clip_available if _analyzer is not None else None,
        "threshold": _scorer.threshold if _scorer else 0.65,
        "max_retries": _feedback.max_retries,
    }
