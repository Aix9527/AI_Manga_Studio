---
AIGC:
    Label: "1"
    ContentProducer: 001191440300708461136T1XGW3
    ProduceID: ac05b1368557ee08912a0f1b051adb10_3110ff7c86a911f18766525400f8a581
    ReservedCode1: dLNd/cSRuwNiwtw7ZepMItT55SD/wdpXltoAm/OoHdz0+nU1GNogl4b9ugFdHKWk9SKmrQNjaheR+XL/3wLX4+RXLKLqWwJnjALRuiSvTCO1pQsJQIw//lSnoRCeaaICAujwpNzyam2YGjT+HxZrwdLGxmze3F68BVept/pfgjURzkY4k9AMIc8rjtU=
    ContentPropagator: 001191440300708461136T1XGW3
    PropagateID: ac05b1368557ee08912a0f1b051adb10_3110ff7c86a911f18766525400f8a581
    ReservedCode2: dLNd/cSRuwNiwtw7ZepMItT55SD/wdpXltoAm/OoHdz0+nU1GNogl4b9ugFdHKWk9SKmrQNjaheR+XL/3wLX4+RXLKLqWwJnjALRuiSvTCO1pQsJQIw//lSnoRCeaaICAujwpNzyam2YGjT+HxZrwdLGxmze3F68BVept/pfgjURzkY4k9AMIc8rjtU=
---

# Video Pipeline | 视频流水线

## Overview

The Video Pipeline is the final stage of AI_Manga_Studio's production workflow. It assembles generated images into a complete video with transitions, subtitles, voiceover, and background audio — transforming a storyboard into a watchable drama.

## Responsibilities

- Assemble frame sequences into video clips per shot
- Apply transitions between shots (cut, fade, dissolve, wipe)
- Synchronize dialogue audio with character mouth movements
- Overlay subtitles with precise timing
- Mix background music and sound effects
- Encode final video in standard formats (MP4, WebM)

## Pipeline Architecture

```
Generated Images (per shot)
        ↓
Frame Sequence Assembly
        ↓
Video Clip Generation (per shot)
        ↓
Transition Application
        ↓
Shot Concatenation
        ↓
Audio Track Mixing
   ├── Voiceover (TTS per dialogue)
   ├── Background Music
   └── Sound Effects
        ↓
Subtitle Overlay
        ↓
Final Encoding
        ↓
Output Video File
```

## Input

- **Generated Images**: Per-shot image files from image provider
- **Storyboard Data**: Shot list with durations, transitions, dialogue
- **Audio Files**: Character voice clips from audio provider (TTS)
- **Subtitle Data**: Dialogue text with start/end timestamps
- **Background Audio**: Music and sound effect files (optional)
- **Style Configuration**: Aspect ratio, resolution, FPS, encoding settings

## Output

```json
{
  "video_id": "vid_ch12_001",
  "file_path": "/output/heavenly_sword_ch12.mp4",
  "format": "mp4",
  "resolution": "1920x1080",
  "fps": 24,
  "duration_seconds": 180.5,
  "file_size_bytes": 52428800,
  "codec": {
    "video": "h264",
    "audio": "aac"
  },
  "tracks": [
    {"type": "video", "shots": 24, "transitions": 23},
    {"type": "voiceover", "characters": ["Ye Fan", "Lin Xue"], "total_dialogues": 8},
    {"type": "subtitle", "language": "zh-CN"},
    {"type": "background_music", "track_name": "epic_orchestral_01"}
  ]
}
```

## Video Generation Workflow

### Stage 1: Frame Sequence Assembly

Each shot generates a sequence of still frames (or uses a single image with Ken Burns effect for static shots):

```python
async def assemble_shot_frames(
    shot: Shot,
    images: List[Path],
    duration: float,
    fps: int = 24
) -> List[Path]:
    """Convert shot images into frame sequence.

    For static shots: single image stretched to duration
    For motion shots: interpolated frames or video generator output
    """
    frame_count = int(duration * fps)
    if shot.camera.movement == "static":
        # Repeat single image for all frames (or apply Ken Burns)
        return replicate_with_zoom(images[0], frame_count, shot.camera)
    else:
        # Generate interpolated frames for camera movement
        return generate_motion_frames(images, frame_count, shot.camera)
```

### Stage 2: Clip Generation

Individual shot clips are rendered with FFmpeg:

```bash
ffmpeg -framerate 24 -i shot_%04d.png -c:v libx264 -pix_fmt yuv420p shot_clip.mp4
```

### Stage 3: Transition Application

Transitions are applied between consecutive shot clips:

| Transition | Implementation | Use Case |
|------------|----------------|----------|
| **Cut** | Direct concatenation | Fast pacing, action scenes |
| **Fade to Black** | `fade=t=out:st=X:d=0.5` | Scene change, chapter end |
| **Cross Dissolve** | `xfade=transition=fade:duration=0.5:offset=X` | Time passage, mood shift |
| **Wipe** | `xfade=transition=wiperight:duration=0.3` | Dynamic scene change |

### Stage 4: Audio Track Mixing

```bash
# Mix voiceover, background music, and sound effects
ffmpeg -i video.mp4 \
       -i voiceover.wav \
       -i background_music.mp3 \
       -i sfx.wav \
       -filter_complex "[1:a]volume=1.0[v];[2:a]volume=0.3[m];[3:a]volume=0.5[s];[v][m][s]amix=inputs=3:duration=first" \
       -c:v copy output_with_audio.mp4
```

### Stage 5: Subtitle Overlay

Subtitles are burned into the video using ASS/SSA format for styled subtitles:

```python
async def generate_subtitles(
    dialogues: List[Dialogue],
    character_styles: Dict[str, CharacterVoiceStyle]
) -> Path:
    """Generate ASS subtitle file with character-colored text."""
    ass = ASSWriter()
    for dialogue in dialogues:
        style = character_styles.get(dialogue.speaker_id)
        ass.add_event(
            start=dialogue.start_time,
            end=dialogue.end_time,
            text=dialogue.text,
            style=style.subtitle_style
        )
    return ass.write()
```

### Stage 6: Final Encoding

```bash
ffmpeg -i video_with_audio.mp4 \
       -vf "ass=subtitles.ass" \
       -c:v libx264 -crf 18 -preset medium \
       -c:a aac -b:a 192k \
       final_output.mp4
```

## Subtitle Specifications

| Parameter | Default | Description |
|-----------|---------|-------------|
| Format | ASS | Advanced SubStation Alpha |
| Font | Noto Sans CJK | Default Chinese font |
| Character Colors | Per-character | Each character has a unique subtitle color |
| Position | Bottom center | Standard subtitle placement |
| Max chars per line | 20 (Chinese) / 40 (English) | Readability limit |

## Voice Synchronization

Character voice data includes timing information:

```json
{
  "dialogue_id": "dial_ch12_03",
  "speaker": "Ye Fan",
  "text": "Stay behind me. I sense something ahead.",
  "voice_clip": "/output/audio/ye_fan_dial_03.wav",
  "duration_seconds": 3.2,
  "start_offset": 0.0,
  "emotion": "alert"
}
```

The audio duration determines both the shot duration adjustment and subtitle timing.

## API

```python
class VideoPipeline:
    async def generate_video(
        self,
        storyboard: Storyboard,
        assets: Dict[str, List[Asset]],
        config: VideoConfig
    ) -> VideoOutput

    async def generate_shot_clip(
        self,
        shot: Shot,
        images: List[Path],
        audio: Optional[Path]
    ) -> Path

    async def apply_transitions(
        self,
        clips: List[Path],
        transitions: List[Transition]
    ) -> Path

    async def mix_audio(
        self,
        voiceover: List[Path],
        background_music: Optional[Path],
        sfx: Optional[List[Path]]
    ) -> Path

    async def burn_subtitles(
        self,
        video: Path,
        subtitles: Path
    ) -> Path
```

## Future

- Real-time preview with scrubbing
- Multi-track timeline editor
- Automatic lip-sync using Wav2Lip or similar
- Motion interpolation for smoother animation
- HDR and 10-bit color support
- Adaptive bitrate streaming output
- Batch export with multiple resolutions
*（内容由AI生成，仅供参考）*
