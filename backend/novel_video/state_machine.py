from __future__ import annotations

from backend.novel_video.models import RunStatus, ShotStatus


class InvalidTransition(ValueError):
    """Raised when a production state is moved along an unsupported edge."""


RUN_TRANSITIONS: dict[RunStatus, set[RunStatus]] = {
    RunStatus.DRAFT: {RunStatus.PLANNING, RunStatus.CANCELLED},
    RunStatus.PLANNING: {
        RunStatus.AWAITING_REVIEW,
        RunStatus.RENDERING,
        RunStatus.INTERRUPTED,
        RunStatus.BLOCKED,
        RunStatus.CANCELLED,
    },
    RunStatus.AWAITING_REVIEW: {
        RunStatus.RENDERING,
        RunStatus.BLOCKED,
        RunStatus.CANCELLED,
    },
    RunStatus.RENDERING: {
        RunStatus.AWAITING_REVIEW,
        RunStatus.MIXING,
        RunStatus.PAUSED,
        RunStatus.INTERRUPTED,
        RunStatus.BLOCKED,
        RunStatus.CANCELLED,
    },
    RunStatus.MIXING: {
        RunStatus.VALIDATING,
        RunStatus.PAUSED,
        RunStatus.INTERRUPTED,
        RunStatus.BLOCKED,
        RunStatus.CANCELLED,
    },
    RunStatus.VALIDATING: {
        RunStatus.COMPLETED,
        RunStatus.PAUSED,
        RunStatus.INTERRUPTED,
        RunStatus.BLOCKED,
        RunStatus.CANCELLED,
    },
    RunStatus.PAUSED: {
        RunStatus.PLANNING,
        RunStatus.RENDERING,
        RunStatus.INTERRUPTED,
        RunStatus.BLOCKED,
        RunStatus.CANCELLED,
    },
    RunStatus.INTERRUPTED: {
        RunStatus.PLANNING,
        RunStatus.RENDERING,
        RunStatus.BLOCKED,
        RunStatus.CANCELLED,
    },
    RunStatus.BLOCKED: {
        RunStatus.PLANNING,
        RunStatus.RENDERING,
        RunStatus.CANCELLED,
    },
    RunStatus.CANCELLED: set(),
    RunStatus.COMPLETED: set(),
}


SHOT_TRANSITIONS: dict[ShotStatus, set[ShotStatus]] = {
    ShotStatus.DRAFT: {ShotStatus.LOCKED, ShotStatus.BLOCKED},
    ShotStatus.LOCKED: {ShotStatus.QUEUED, ShotStatus.BLOCKED},
    ShotStatus.QUEUED: {ShotStatus.RUNNING, ShotStatus.BLOCKED},
    ShotStatus.RUNNING: {ShotStatus.VALIDATING, ShotStatus.FAILED, ShotStatus.BLOCKED},
    ShotStatus.VALIDATING: {ShotStatus.APPROVED, ShotStatus.FAILED, ShotStatus.BLOCKED},
    # A later hash/media check can invalidate a once-approved asset.  It must
    # fail closed instead of leaving a corrupt checkpoint marked approved.
    ShotStatus.APPROVED: {ShotStatus.INCLUDED, ShotStatus.BLOCKED},
    ShotStatus.INCLUDED: set(),
    ShotStatus.FAILED: {ShotStatus.QUEUED, ShotStatus.BLOCKED},
    ShotStatus.BLOCKED: {ShotStatus.QUEUED},
}


def transition_run(current: RunStatus, target: RunStatus) -> RunStatus:
    if current == target or target in RUN_TRANSITIONS[current]:
        return target
    raise InvalidTransition(f"illegal run status transition: {current.value} -> {target.value}")


def transition_shot(current: ShotStatus, target: ShotStatus) -> ShotStatus:
    if current == target or target in SHOT_TRANSITIONS[current]:
        return target
    raise InvalidTransition(f"illegal shot status transition: {current.value} -> {target.value}")
