"""
AI Manga Studio Pro V2.0 — Timeline Manager

Driven by StoryGraph.timeline. Produces beat-level timecodes with
precise second-level resolution, driving video pacing and transition timing.

Architecture:
  StoryGraph.timeline → TimelineManager → BeatSchedule
                                             ↓
                                    Video Engine / Render Stage
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple


# ============================================================
# Data Classes
# ============================================================

@dataclass
class TransitionEvent:
    """A scheduled transition between beats/scenes."""
    at_sec: float = 0.0
    type: str = "cut"             # cut/dissolve/fade/wipe/zoom
    from_beat: str = ""
    to_beat: str = ""
    duration: float = 0.5         # transition duration in seconds
    reason: str = ""              # why this transition type was chosen


@dataclass
class BeatSchedule:
    """A scheduled beat with exact timecodes."""
    beat_id: str = ""
    scene_id: str = ""
    chapter_idx: int = 0
    start_sec: float = 0.0
    end_sec: float = 0.0
    duration: float = 0.0
    transition_in: Optional[TransitionEvent] = None
    transition_out: Optional[TransitionEvent] = None
    pace_label: str = "normal"    # slow/normal/fast/rapid
    emphasis: bool = False        # highlight / key moment


@dataclass
class TimelineSchedule:
    """Complete timeline scheduling output."""
    project_id: str = ""
    beats: List[BeatSchedule] = field(default_factory=list)
    transitions: List[TransitionEvent] = field(default_factory=list)
    total_duration: float = 0.0
    chapter_boundaries: List[float] = field(default_factory=list)


# ============================================================
# Pacing rules
# ============================================================

# Beat type → base pacing (duration multiplier)
BEAT_PACE = {
    "dialogue":   1.0,    # normal
    "action":     0.8,    # slightly faster
    "monologue":  1.3,    # slower, contemplative
    "transition": 0.5,    # fast
    "narration":  1.2,    # slower, descriptive
}

# Emotion → pace modifier
EMOTION_PACE_MOD = {
    "angry":      0.85,   # faster cuts during anger
    "sad":        1.2,    # slower during sadness
    "happy":      0.9,    # slightly faster
    "fearful":    0.75,   # rapid during fear
    "surprised":  0.7,    # very fast
    "neutral":    1.0,
    "loving":     1.15,   # gentle pace
    "hateful":    0.8,
    "worried":    1.05,
}

# Scene change → transition type
SCENE_TRANSITION_MAP = {
    ("interior", "exterior"): "fade",       # going outside
    ("exterior", "interior"): "dissolve",   # coming inside
    ("action", "dialogue"): "cut",
    ("dialogue", "action"): "wipe",
    ("monologue", "dialogue"): "dissolve",
    ("dialogue", "monologue"): "fade",
}


# ============================================================
# Timeline Manager
# ============================================================

class TimelineManager:
    """Produces beat-level scheduling and transition planning.

    Usage:
        from backend.story_graph import StoryGraph
        from backend.pipeline.timeline_manager import TimelineManager

        tm = TimelineManager()
        schedule = tm.build_schedule(story_graph)
    """

    def __init__(self, default_beat_duration: float = 3.0):
        self.default_beat_duration = default_beat_duration

    def build_schedule(self, story_graph: "StoryGraph") -> TimelineSchedule:
        """Build a complete beat schedule with transitions.

        Args:
            story_graph: Fully populated StoryGraph.

        Returns:
            TimelineSchedule with beat-level timecodes and transitions.
        """
        timeline = story_graph.timeline
        if not timeline.beats:
            return TimelineSchedule(project_id=story_graph.project_id)

        schedule = TimelineSchedule(
            project_id=story_graph.project_id,
            total_duration=timeline.total_duration,
            chapter_boundaries=list(timeline.chapter_boundaries),
        )

        beat_schedules: List[BeatSchedule] = []
        transitions: List[TransitionEvent] = []

        for i, beat in enumerate(timeline.beats):
            # Determine pacing
            pace_label = self._determine_pace(beat.beat_type, beat.emotion)
            emphasis = self._is_key_moment(beat, i, timeline.beats)

            # Build transition in
            trans_in: Optional[TransitionEvent] = None
            if i > 0:
                prev_beat = timeline.beats[i - 1]
                trans_in = self._choose_transition(
                    prev_beat, beat, story_graph,
                    at_sec=beat.start_sec,
                )

            # Build transition out (will be overwritten by next beat's trans_in)
            trans_out: Optional[TransitionEvent] = None

            bs = BeatSchedule(
                beat_id=beat.beat_id,
                scene_id=beat.scene_id,
                chapter_idx=beat.chapter_idx,
                start_sec=beat.start_sec,
                end_sec=beat.start_sec + beat.duration_sec,
                duration=beat.duration_sec,
                transition_in=trans_in,
                transition_out=trans_out,
                pace_label=pace_label,
                emphasis=emphasis,
            )

            if trans_in:
                transitions.append(trans_in)

            beat_schedules.append(bs)

        # Back-link transition_out
        for i in range(len(beat_schedules) - 1):
            if beat_schedules[i + 1].transition_in:
                beat_schedules[i].transition_out = beat_schedules[i + 1].transition_in

        schedule.beats = beat_schedules
        schedule.transitions = transitions

        return schedule

    # ----------------------------------------------------------
    # Helpers
    # ----------------------------------------------------------

    def _determine_pace(self, beat_type: str, emotion: str) -> str:
        """Determine pace label from beat type and emotion."""
        base = BEAT_PACE.get(beat_type, 1.0)
        mod = EMOTION_PACE_MOD.get(emotion, 1.0)
        product = base * mod

        if product < 0.6:
            return "rapid"
        elif product < 0.85:
            return "fast"
        elif product < 1.15:
            return "normal"
        else:
            return "slow"

    def _is_key_moment(
        self, beat: "BeatNode", idx: int, all_beats: List["BeatNode"],
    ) -> bool:
        """Detect if this beat is a key narrative moment.

        Heuristics:
          - Chapter boundary (first beat of a chapter)
          - Emotion shift (different from previous beat)
          - High emotional intensity
          - Beat with monologue or dialogue (character-driven moments)
        """
        if idx == 0:
            return True  # opening beat is always key

        # Chapter boundary check
        if beat.chapter_idx != all_beats[idx - 1].chapter_idx:
            return True

        # Emotion shift
        if beat.emotion != all_beats[idx - 1].emotion:
            return True

        # High intensity
        if beat.intensity >= 0.8:
            return True

        # Monologue is a key moment
        if beat.beat_type == "monologue":
            return True

        return False

    def _choose_transition(
        self,
        from_beat: "BeatNode",
        to_beat: "BeatNode",
        story_graph: "StoryGraph",
        at_sec: float,
    ) -> TransitionEvent:
        """Choose the best transition type between two beats.

        Factors:
          - Scene change (same scene or different)
          - Beat type pair
          - Emotion shift
        """
        # Default: cut
        trans_type = "cut"
        duration = 0.5
        reasons: List[str] = []

        # Scene change → longer transition
        if from_beat.scene_id != to_beat.scene_id:
            from_ctx = story_graph.scene_map.get(from_beat.scene_id)
            to_ctx = story_graph.scene_map.get(to_beat.scene_id)
            if from_ctx and to_ctx:
                ie_pair = (from_ctx.interior_exterior, to_ctx.interior_exterior)
                trans_type = SCENE_TRANSITION_MAP.get(
                    ie_pair,
                    SCENE_TRANSITION_MAP.get(
                        (from_beat.beat_type, to_beat.beat_type), "dissolve"
                    ),
                )
                duration = 1.0
                reasons.append(f"scene change: {from_beat.scene_id}→{to_beat.scene_id}")

        # Beat type pair
        bt_pair = (from_beat.beat_type, to_beat.beat_type)
        if bt_pair in SCENE_TRANSITION_MAP:
            trans_type = SCENE_TRANSITION_MAP[bt_pair]
            duration = 0.5

        # Emotion shift → longer dissolve
        if from_beat.emotion != to_beat.emotion:
            if trans_type == "cut":
                trans_type = "dissolve"
            duration = max(duration, 0.8)
            reasons.append(f"emotion shift: {from_beat.emotion}→{to_beat.emotion}")

        # Chapter boundary → fade
        if from_beat.chapter_idx != to_beat.chapter_idx:
            trans_type = "fade"
            duration = 1.2
            reasons.append(f"chapter boundary: ch{from_beat.chapter_idx}→ch{to_beat.chapter_idx}")

        return TransitionEvent(
            at_sec=at_sec,
            type=trans_type,
            from_beat=from_beat.beat_id,
            to_beat=to_beat.beat_id,
            duration=duration,
            reason=", ".join(reasons) if reasons else "default cut",
        )

    def summary(self, schedule: TimelineSchedule) -> str:
        """Generate a human-readable summary of the timeline."""
        lines = [
            f"Timeline: {len(schedule.beats)} beats, "
            f"{schedule.total_duration:.1f}s total",
            f"  Chapter boundaries: {schedule.chapter_boundaries}",
            f"  Transitions: {len(schedule.transitions)}",
        ]

        # Count transition types
        type_counts: Dict[str, int] = {}
        for t in schedule.transitions:
            type_counts[t.type] = type_counts.get(t.type, 0) + 1
        for ttype, count in sorted(type_counts.items(), key=lambda x: -x[1]):
            lines.append(f"    {ttype}: {count}")

        # Count pace distribution
        pace_counts: Dict[str, int] = {}
        for b in schedule.beats:
            pace_counts[b.pace_label] = pace_counts.get(b.pace_label, 0) + 1
        lines.append("  Pacing:")
        for pace, count in sorted(pace_counts.items()):
            lines.append(f"    {pace}: {count} beats")

        return "\n".join(lines)
