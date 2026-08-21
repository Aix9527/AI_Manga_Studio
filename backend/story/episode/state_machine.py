"""Episode state machine (Phase 13.1, GPT spec).

States (GPT): DRAFT → PLANNING → SCRIPT_READY → STORYBOARD_READY →
ASSET_READY → PRODUCTION → REVIEW → APPROVED → PUBLISHED.

Rules:
- forward transitions advance one stage (approve gate: REVIEW → APPROVED)
- rollback only restores the previous state (recoverable, audited)
- illegal jumps (e.g. DRAFT → PUBLISHED) are rejected
- every transition is recorded in the episode audit chain
"""

from __future__ import annotations

from enum import Enum


class EpisodeState(str, Enum):
    DRAFT = "draft"
    PLANNING = "planning"
    SCRIPT_READY = "script_ready"
    STORYBOARD_READY = "storyboard_ready"
    ASSET_READY = "asset_ready"
    PRODUCTION = "production"
    REVIEW = "review"
    APPROVED = "approved"
    PUBLISHED = "published"


# Forward edges: the only legal way to move forward.
FORWARD: dict[EpisodeState, set[EpisodeState]] = {
    EpisodeState.DRAFT: {EpisodeState.PLANNING},
    EpisodeState.PLANNING: {EpisodeState.SCRIPT_READY},
    EpisodeState.SCRIPT_READY: {EpisodeState.STORYBOARD_READY},
    EpisodeState.STORYBOARD_READY: {EpisodeState.ASSET_READY},
    EpisodeState.ASSET_READY: {EpisodeState.PRODUCTION},
    EpisodeState.PRODUCTION: {EpisodeState.REVIEW},
    EpisodeState.REVIEW: {EpisodeState.APPROVED},
    EpisodeState.APPROVED: {EpisodeState.PUBLISHED},
    EpisodeState.PUBLISHED: set(),
}

# Rollback edges: recover to the immediately previous state.
ROLLBACK: dict[EpisodeState, set[EpisodeState]] = {
    EpisodeState.PLANNING: {EpisodeState.DRAFT},
    EpisodeState.SCRIPT_READY: {EpisodeState.PLANNING},
    EpisodeState.STORYBOARD_READY: {EpisodeState.SCRIPT_READY},
    EpisodeState.ASSET_READY: {EpisodeState.STORYBOARD_READY},
    EpisodeState.PRODUCTION: {EpisodeState.ASSET_READY},
    EpisodeState.REVIEW: {EpisodeState.PRODUCTION},
    EpisodeState.APPROVED: {EpisodeState.REVIEW},
    EpisodeState.PUBLISHED: {EpisodeState.APPROVED},
}

# Special review feedback: back to production for rework (audited).
REWORK: dict[EpisodeState, set[EpisodeState]] = {
    EpisodeState.REVIEW: {EpisodeState.PRODUCTION},
}

VALID: set[EpisodeState] = set(EpisodeState)


class EpisodeStateMachine:
    """Validates every state transition before it is persisted."""

    def __init__(self, initial: EpisodeState = EpisodeState.DRAFT):
        self.current = initial

    @staticmethod
    def allowed(from_state: str | EpisodeState, to_state: str | EpisodeState) -> bool:
        source = EpisodeState(from_state)
        target = EpisodeState(to_state)
        return (
            target in FORWARD[source]
            or target in ROLLBACK.get(source, set())
            or target in REWORK.get(source, set())
        )

    @staticmethod
    def next_of(from_state: str | EpisodeState) -> str | None:
        source = EpisodeState(from_state)
        targets = FORWARD[source]
        return next(iter(targets)).value if len(targets) == 1 else None

    @staticmethod
    def validate_transition(from_state: str | EpisodeState, to_state: str | EpisodeState) -> str:
        """Return 'forward' | 'rollback' | 'rework' or raise ValueError."""
        source = EpisodeState(from_state)
        target = EpisodeState(to_state)
        if target in FORWARD[source]:
            return "forward"
        if target in REWORK.get(source, set()):
            return "rework"
        if target in ROLLBACK.get(source, set()):
            return "rollback"
        raise ValueError(f"illegal episode transition: {source.value} -> {target.value}")

    @staticmethod
    def previous_of(from_state: str | EpisodeState) -> str | None:
        source = EpisodeState(from_state)
        if source == EpisodeState.DRAFT:
            return None
        # the unique immediate predecessor under forward edges
        for prev, targets in FORWARD.items():
            if source in targets:
                return prev.value
        return None
