---
AIGC:
    Label: "1"
    ContentProducer: 001191440300708461136T1XGW3
    ProduceID: ac05b1368557ee08912a0f1b051adb10_2a75f93386a911f18766525400f8a581
    ReservedCode1: stASqHgOY4uue5VXqXxtUopJp/4mNIXWaMMmEsQHblsj4gpZjV0c32yUyocM53kFk/H44JP3MlePxhWljKkVtGkcyCaKTLP40gETf2gP+dSzEWjGYm1R1E3ZiV6LxSBE8I9q9dNC4NoiWOeU2BCtD5HcStAfmcGyZRJ6+ACZrnSBKxs+sZS80LPetuo=
    ContentPropagator: 001191440300708461136T1XGW3
    PropagateID: ac05b1368557ee08912a0f1b051adb10_2a75f93386a911f18766525400f8a581
    ReservedCode2: stASqHgOY4uue5VXqXxtUopJp/4mNIXWaMMmEsQHblsj4gpZjV0c32yUyocM53kFk/H44JP3MlePxhWljKkVtGkcyCaKTLP40gETf2gP+dSzEWjGYm1R1E3ZiV6LxSBE8I9q9dNC4NoiWOeU2BCtD5HcStAfmcGyZRJ6+ACZrnSBKxs+sZS80LPetuo=
---

# Storyboard Planner | 分镜规划器

## Overview

The Storyboard Planner converts scene descriptions into detailed, production-ready shot lists. It is the bridge between narrative understanding and visual production — translating "what happens in the story" into "what the camera sees."

## Responsibilities

- Decompose scenes into individual shots with clear boundaries
- Assign camera language to each shot (shot type, angle, movement)
- Define composition guidelines for image generation
- Plan character positioning and action staging within each frame
- Estimate shot duration for video production timing
- Specify transitions between shots (cut, fade, dissolve, etc.)

## Input

- **Scene Data**: Structured scene JSON from Story Parser (location, characters, dialogues, actions, atmosphere)
- **Character Data**: Character Cards from Character Manager (appearance, costume, expressions)
- **Style Configuration**: Optional style guide (aspect ratio, color palette, visual style reference)

## Output

Storyboard JSON:

```json
{
  "storyboard_id": "sb_ch12",
  "chapter_id": 12,
  "style": "cinematic anime, 16:9",
  "total_shots": 24,
  "estimated_duration_seconds": 180,
  "shots": [
    {
      "shot_id": "ch12_shot_01",
      "shot_number": 1,
      "scene_id": 3,
      "shot_type": "wide_establishing",
      "camera": {
        "angle": "high_angle",
        "movement": "slow_pan_right",
        "focal_length": "wide_24mm"
      },
      "composition": {
        "rule_of_thirds": true,
        "focus_point": "center",
        "depth_of_field": "deep",
        "description": "The Dark Forest stretches across the frame, ancient ruins visible in the distance, moonlight filtering through dead branches"
      },
      "characters": [],
      "action": "Establishing shot of the Dark Forest at night",
      "dialogue": null,
      "duration_seconds": 5.0,
      "transition_in": "fade_from_black",
      "transition_out": "cut"
    },
    {
      "shot_id": "ch12_shot_02",
      "shot_number": 2,
      "scene_id": 3,
      "shot_type": "medium_two_shot",
      "camera": {
        "angle": "eye_level",
        "movement": "static",
        "focal_length": "medium_50mm"
      },
      "composition": {
        "rule_of_thirds": true,
        "focus_point": "left_third",
        "depth_of_field": "shallow",
        "description": "Ye Fan (left, foreground) with sword drawn, Lin Xue (right, slightly behind), both facing camera-right toward the ruins"
      },
      "characters": ["char_001", "char_002"],
      "action": "Ye Fan draws his sword protectively; Lin Xue reaches for her talisman",
      "dialogue": {
        "speaker": "Ye Fan",
        "line": "Stay behind me. I sense something ahead."
      },
      "duration_seconds": 6.0,
      "transition_in": "cut",
      "transition_out": "cut"
    }
  ]
}
```

## Shot Type Reference

| Type | Description | Typical Use |
|------|-------------|-------------|
| **Extreme Wide (EWS)** | Subject barely visible | Establishing location, epic scale |
| **Wide (WS)** | Full subject + environment | Scene setting, group shots |
| **Medium Wide (MWS)** | Subject from knees up | Action with environmental context |
| **Medium (MS)** | Subject from waist up | Dialogue, character interaction |
| **Medium Close-Up (MCU)** | Subject from chest up | Emotional dialogue, reactions |
| **Close-Up (CU)** | Face fills frame | Intense emotion, key object detail |
| **Extreme Close-Up (ECU)** | Eye, hand, specific detail | Maximum dramatic emphasis |
| **Two-Shot** | Two characters in frame | Conversations, confrontations |
| **Over-the-Shoulder (OTS)** | Behind one character | Dialogue, POV emphasis |

## Workflow

```
1. Scene Input → Receive parsed scene data with all metadata
2. Shot Decomposition → LLM analyzes scene and proposes shot boundaries
3. Camera Assignment → Assign shot type, angle, movement per shot
4. Composition Planning → Define framing, focus, depth of field
5. Character Staging → Position characters within each shot
6. Duration Estimation → Calculate timing based on dialogue length + action
7. Transition Design → Define shot-to-shot transitions
8. Human Review → Creator reviews and adjusts shot plan
9. Final Output → Locked storyboard JSON for prompt generation
```

## API

```python
class StoryboardPlanner:
    async def plan_chapter(
        self, novel_id: str, chapter_id: int, config: StoryboardConfig = None
    ) -> Storyboard
    async def plan_scene(self, scene: Scene, character_data: List[CharacterCard]) -> List[Shot]
    async def update_shot(self, shot_id: str, updates: ShotUpdate) -> Shot
    async def reorder_shots(self, storyboard_id: str, new_order: List[str]) -> Storyboard
    async def export_storyboard(self, storyboard_id: str, format: str = "json") -> Path
```

## Future

- Automatic pacing analysis (action vs. dialogue balance)
- Shot variety enforcement (prevent too many similar shots in sequence)
- Emotion arc visualization across shots
- Integration with 3D previsualization tools
- Automatic shot count estimation based on scene complexity
*（内容由AI生成，仅供参考）*
