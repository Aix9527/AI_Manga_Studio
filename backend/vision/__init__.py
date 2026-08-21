"""Sprint 7.1 — Vision Intelligence Layer.

Modules:
- image_analyzer: CLIP/PIL-based image analysis
- quality_score: Multi-dimensional quality assessment
- consistency_check: Cross-frame character/style consistency
- feedback: Score → prompt rewrite feedback loop
"""

from backend.vision.image_analyzer import ImageAnalyzer, ImageProfile
from backend.vision.quality_score import QualityScorer, QualityReport
from backend.vision.consistency_check import ConsistencyChecker, ConsistencyReport, StyleDriftReport
from backend.vision.feedback import FeedbackLoop, PromptFeedback, FeedbackAction

__all__ = [
    "ImageAnalyzer",
    "ImageProfile",
    "QualityScorer",
    "QualityReport",
    "ConsistencyChecker",
    "ConsistencyReport",
    "StyleDriftReport",
    "FeedbackLoop",
    "PromptFeedback",
    "FeedbackAction",
]
