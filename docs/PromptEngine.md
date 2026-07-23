---
AIGC:
    Label: "1"
    ContentProducer: 001191440300708461136T1XGW3
    ProduceID: ac05b1368557ee08912a0f1b051adb10_2b549f3186a911f18766525400f8a581
    ReservedCode1: WnrJs5m+yuB01JrKDEUpYf8pCB/l7YjCnaSf64I3u52AKirb7pO+m0DRpXiPXtrOa261XamOZFUbAAwuSVjS4c/Y4UHa4p4inqf226ptN3jmjs3uij5PWKOm+N0wCKplmvtniHnPYbztYC0TAUpCZfhIa9W00z3IjI15yvcS4awNZ+5+FYRDk94XsS8=
    ContentPropagator: 001191440300708461136T1XGW3
    PropagateID: ac05b1368557ee08912a0f1b051adb10_2b549f3186a911f18766525400f8a581
    ReservedCode2: WnrJs5m+yuB01JrKDEUpYf8pCB/l7YjCnaSf64I3u52AKirb7pO+m0DRpXiPXtrOa261XamOZFUbAAwuSVjS4c/Y4UHa4p4inqf226ptN3jmjs3uij5PWKOm+N0wCKplmvtniHnPYbztYC0TAUpCZfhIa9W00z3IjI15yvcS4awNZ+5+FYRDk94XsS8=
---

# Prompt Engine | Prompt 生成引擎

## Overview

The Prompt Engine automatically constructs AI-ready prompts from structured production data. Instead of requiring creators to manually write prompts for every shot, the Prompt Engine combines character data, scene context, style preferences, camera information, and action descriptions into optimized prompts for each AI provider.

## Responsibilities

- Generate Positive Prompts (what to include)
- Generate Negative Prompts (what to exclude, quality control)
- Generate Style Prompts (aesthetic direction)
- Generate Scene Prompts (environmental context)
- Generate Motion Prompts (for video/animation)
- Adapt prompts to provider-specific formats (ComfyUI, Flux, Wan, etc.)

## Prompt Composition

Each prompt is assembled from modular components:

```
Style Prompt + Character Prompt + Scene Prompt + Action Prompt + Camera Prompt
     ↓               ↓                ↓              ↓               ↓
  "cinematic     "Ye Fan,       "dark forest   "drawing      "wide shot,
   anime,        dark blue      at night,      sword,         high angle,
   16:9,         robe,          ancient        protective    slow pan"
   volumetric    shoulder-      ruins,         stance,
   lighting"     length         moonlight"     alert face"
                 black hair"
```

## Input

- **Storyboard Shot Data**: Shot type, camera specs, composition notes, dialogue, action
- **Character Cards**: Appearance, costume (current variant), expression, current state
- **Scene Data**: Location, time of day, atmosphere, environmental details
- **Style Configuration**: Global style guide (art style, color palette, quality parameters)

## Output

```json
{
  "shot_id": "ch12_shot_02",
  "prompts": {
    "positive": "cinematic anime style, 16:9 aspect ratio, volumetric lighting. Ye Fan, 19-year-old male, lean athletic build, sharp jawline, determined deep blue eyes with faint glow, shoulder-length black hair in simple ponytail, fair skin, faint scar on left cheek, wearing dark blue cultivator's robe with silver trim, jade pendant at waist. Medium two-shot composition, eye-level static camera. Dark forest at night, ancient ruins visible in background, moonlight filtering through dead branches. Ye Fan in foreground left, sword drawn with faint blue glow, protective stance, alert expression. Lin Xue in background right, fearful expression, reaching for a talisman. Rule of thirds composition, shallow depth of field.",
    "negative": "blurry, low quality, deformed face, extra limbs, bad anatomy, watermark, text, signature, different hair color, different eye color, missing scar, modern clothing, urban setting, bright daylight, cartoon style, 3D render, realistic photo, missing jade pendant",
    "style": "cinematic anime, studio quality, detailed background, dramatic lighting, high contrast, cool color palette, moonlight illumination",
    "motion": "Ye Fan: slight breathing movement, robe gently swaying, sword glow pulsing faintly. Lin Xue: subtle trembling, hand slowly reaching for talisman. Camera: static hold, no movement. Duration: 6 seconds at 24fps."
  },
  "provider_overrides": {
    "flux": {
      "positive": "...Flux-optimized prompt...",
      "negative": "...Flux-optimized negative..."
    },
    "wan": {
      "motion": "...Wan-optimized motion prompt..."
    }
  }
}
```

## Workflow

```
1. Gather Context → Combine storyboard shot data, character cards, scene data, style config
2. Build Prompt Segments → Generate each segment (style, character, scene, action, camera) independently
3. Assemble Full Prompt → Concatenate segments with proper weighting and syntax
4. Generate Negative Prompt → Auto-construct quality control terms + style-specific negatives
5. Build Motion Prompt → For video shots, construct temporal/motion description
6. Provider Adaptation → Adjust prompt format and keywords for target AI provider
7. Validate → Check prompt length limits, keyword conflicts, provider compatibility
8. Store → Save all prompts as structured JSON, linked to shot ID
```

## Prompt Templates (Conceptual)

```
# Positive Prompt Template
{style_prefix} {character_descriptions} {scene_description} {action_description} {camera_description} {quality_tags}

# Negative Prompt Template
{quality_negatives} {style_negatives} {character_specific_negatives} {provider_specific_negatives}

# Motion Prompt Template
{character_movements} {camera_movements} {environmental_motion} {timing_info}
```

## API

```python
class PromptEngine:
    async def generate_shot_prompts(
        self, shot: Shot, characters: List[CharacterCard], scene: Scene, style: StyleConfig
    ) -> ShotPrompts
    async def adapt_for_provider(self, prompts: ShotPrompts, provider: str) -> ShotPrompts
    async def batch_generate(self, storyboard: Storyboard, context: ProductionContext) -> List[ShotPrompts]
    async def validate_prompts(self, prompts: ShotPrompts, provider: str) -> ValidationResult
```

## Future

- Prompt A/B testing and quality scoring
- Character-specific embedding for semantic consistency
- Dynamic prompt weighting based on shot importance
- Style transfer prompts for multi-artist workflows
- Prompt caching and reuse for similar shots
- Automated prompt optimization via feedback loop from generated outputs
*（内容由AI生成，仅供参考）*
