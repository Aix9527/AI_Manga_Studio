"""
Audio Production — Voice, dialogue, sound design (Part 34)

Extended VoiceAgent with:
- Dialogue generation and timing
- Multi-character voice casting
- SFX event mapping
- BGM mood matching
- Audio clip assembly and mixing
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class AudioType(str, Enum):
    VOICE = "voice"
    SFX = "sfx"
    BGM = "bgm"
    AMBIENT = "ambient"


class VoiceGender(str, Enum):
    MALE = "male"
    FEMALE = "female"
    NEUTRAL = "neutral"


@dataclass
class DialogueLine:
    """A single line of dialogue."""
    line_id: str = ""
    scene_number: int = 0
    shot_number: int = 0
    speaker_name: str = ""
    text: str = ""
    emotion: str = "neutral"  # neutral/happy/sad/angry/fearful/whisper
    start_second: float = 0.0
    duration_seconds: float = 1.0
    priority: int = 0  # 0 = normal, 1 = important


@dataclass
class VoiceProfile:
    """A character's voice profile for TTS generation."""
    character_id: str = ""
    character_name: str = ""
    provider: str = "elevenlabs"
    voice_id: str = ""
    gender: VoiceGender = VoiceGender.NEUTRAL
    age_range: str = "adult"
    accent: str = ""
    speaking_rate: float = 1.0
    pitch_shift: float = 0.0
    reference_audio_path: str = ""


@dataclass
class SFXEvent:
    """A sound effect event."""
    event_id: str = ""
    scene_number: int = 0
    shot_number: int = 0
    sfx_name: str = ""  # e.g., "door_slam", "footsteps", "explosion"
    sfx_category: str = ""  # foley/ambient/ui/impact
    start_second: float = 0.0
    duration_seconds: float = 1.0
    volume: float = 1.0
    spatial_position: str = "center"  # center/left/right/surround


@dataclass
class BGMTrack:
    """A background music track."""
    track_id: str = ""
    name: str = ""
    mood: str = ""  # epic/calm/tense/romantic/sad/happy
    genre: str = ""  # orchestral/electronic/ambient/rock
    start_second: float = 0.0
    end_second: float = 0.0
    volume: float = 0.4  # Background, so lower volume
    loop: bool = False
    fade_in_seconds: float = 1.0
    fade_out_seconds: float = 2.0


@dataclass
class AudioTimeline:
    """
    Complete audio timeline for a scene or project.

    Contains all audio layers: voice, SFX, BGM, ambient.
    """
    timeline_id: str = ""
    project_id: str = ""
    total_duration_seconds: float = 0.0

    dialogue_lines: list[DialogueLine] = field(default_factory=list)
    sfx_events: list[SFXEvent] = field(default_factory=list)
    bgm_tracks: list[BGMTrack] = field(default_factory=list)
    voice_profiles: list[VoiceProfile] = field(default_factory=list)

    def add_dialogue(self, line: DialogueLine) -> None:
        self.dialogue_lines.append(line)

    def add_sfx(self, sfx: SFXEvent) -> None:
        self.sfx_events.append(sfx)

    def add_bgm(self, bgm: BGMTrack) -> None:
        self.bgm_tracks.append(bgm)

    def get_mixed_duration(self) -> float:
        """Calculate total mixed duration."""
        max_duration = self.total_duration_seconds
        for line in self.dialogue_lines:
            end = line.start_second + line.duration_seconds
            if end > max_duration:
                max_duration = end
        for sfx in self.sfx_events:
            end = sfx.start_second + sfx.duration_seconds
            if end > max_duration:
                max_duration = end
        for bgm in self.bgm_tracks:
            if bgm.end_second > max_duration:
                max_duration = bgm.end_second
        return max_duration


# ── Audio Director ───────────────────────────────────────────────────

class AudioDirector:
    """
    Orchestrates the entire audio production pipeline.

    Flow:
        1. Extract dialogue from storyboard
        2. Cast voices for each character
        3. Identify SFX cues from scene descriptions
        4. Select BGM based on mood analysis
        5. Build mixed audio timeline
        6. Render final audio track
    """

    def __init__(self) -> None:
        self._voice_profiles: dict[str, VoiceProfile] = {}

    def register_voice(self, profile: VoiceProfile) -> None:
        self._voice_profiles[profile.character_id] = profile

    def cast_character(
        self,
        character_id: str,
        character_name: str,
        gender: VoiceGender = VoiceGender.NEUTRAL,
    ) -> VoiceProfile:
        """Cast a voice for a character."""
        profile = VoiceProfile(
            character_id=character_id,
            character_name=character_name,
            gender=gender,
        )
        self._voice_profiles[character_id] = profile
        return profile

    def extract_dialogue(
        self,
        storyboard: Any,
    ) -> list[DialogueLine]:
        """Extract dialogue lines from a storyboard."""
        lines: list[DialogueLine] = []
        return lines

    def detect_sfx_cues(self, scene_descriptions: list[str]) -> list[SFXEvent]:
        """Detect sound effect cues from scene descriptions."""
        sfx_keywords = {
            "door": "door_open_close",
            "footstep": "footsteps",
            "explosion": "explosion",
            "rain": "rain_ambient",
            "thunder": "thunder",
            "gun": "gunshot",
            "sword": "sword_clash",
            "car": "car_engine",
        }

        cues: list[SFXEvent] = []
        for desc in scene_descriptions:
            for keyword, sfx_name in sfx_keywords.items():
                if keyword.lower() in desc.lower():
                    cues.append(SFXEvent(sfx_name=sfx_name))
        return cues

    def select_bgm(
        self,
        mood: str,
        duration_seconds: float,
    ) -> BGMTrack:
        """Select background music based on mood."""
        mood_map = {
            "epic": "orchestral_epic",
            "tense": "suspense_drone",
            "romantic": "piano_romance",
            "sad": "melancholic_strings",
            "happy": "upbeat_acoustic",
            "calm": "ambient_pads",
        }
        genre = mood_map.get(mood, "ambient_pads")

        return BGMTrack(
            name=f"BGM_{mood}",
            mood=mood,
            genre=genre,
            end_second=duration_seconds,
            fade_out_seconds=2.0,
        )

    def build_timeline(
        self,
        dialogue: list[DialogueLine],
        sfx: list[SFXEvent],
        bgm: BGMTrack,
        scene_duration: float,
    ) -> AudioTimeline:
        """Build a complete audio timeline."""
        timeline = AudioTimeline(total_duration_seconds=scene_duration)
        for line in dialogue:
            timeline.add_dialogue(line)
        for event in sfx:
            timeline.add_sfx(event)
        timeline.add_bgm(bgm)
        return timeline
