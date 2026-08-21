from __future__ import annotations

import json
from enum import Enum

from pydantic import TypeAdapter

from backend.workspace.models import StageAutomation, StageKey


_QUALITY_REPORT_ADAPTER = TypeAdapter(dict[str, object])


class StageDecision(str, Enum):
    ADVANCE = "advance"
    RETRY = "retry"
    WAIT_FOR_REVIEW = "wait_for_review"


EXECUTION_TO_UI_STAGE = {
    "load_input": StageKey.IMPORT,
    "planning": StageKey.STORYBOARD,
    "character_design": StageKey.STORYBOARD,
    "visual_generate": StageKey.KEYFRAME,
    "hd_redraw": StageKey.KEYFRAME,
    "video_generate": StageKey.VIDEO,
    "audio_tts": StageKey.AUDIO,
    "audio_sfx": StageKey.AUDIO,
    "composition_compose": StageKey.COMPOSE,
    "export": StageKey.EXPORT,
}


def decide_after_success(policy: StageAutomation) -> StageDecision:
    return (
        StageDecision.ADVANCE
        if policy.auto_produce and policy.auto_advance
        else StageDecision.WAIT_FOR_REVIEW
    )


def decide_after_quality_failure(
    policy: StageAutomation,
    quality_attempt: int,
) -> StageDecision:
    if not policy.auto_produce:
        return StageDecision.WAIT_FOR_REVIEW
    return (
        StageDecision.RETRY
        if quality_attempt < policy.max_quality_retries
        else StageDecision.WAIT_FOR_REVIEW
    )


class QualityGateError(RuntimeError):
    def __init__(self, message: str, report: dict[str, object]):
        super().__init__(message)
        self.report = json.loads(_QUALITY_REPORT_ADAPTER.dump_json(report))
