---
AIGC:
    Label: "1"
    ContentProducer: 001191440300708461136T1XGW3
    ProduceID: ac05b1368557ee08912a0f1b051adb10_2992e8f586a911f18766525400f8a581
    ReservedCode1: Ft2iF8F5TXeCSJXox0IcGetjip5s6ESCaxcQBAUk3Gxgekaaox/XAuyKjhIohIKJo8EC5BdBsE6c+Xsh1DZIJApr5pNuD83V3tDPXnXpAIiArvipXYb9uJ93jWYqFR1ECPn1hE7lsF/DZv5ClOFeQ345dFJrPKy8gM6tbs5esTNsofCPfINJ+jre9GU=
    ContentPropagator: 001191440300708461136T1XGW3
    PropagateID: ac05b1368557ee08912a0f1b051adb10_2992e8f586a911f18766525400f8a581
    ReservedCode2: Ft2iF8F5TXeCSJXox0IcGetjip5s6ESCaxcQBAUk3Gxgekaaox/XAuyKjhIohIKJo8EC5BdBsE6c+Xsh1DZIJApr5pNuD83V3tDPXnXpAIiArvipXYb9uJ93jWYqFR1ECPn1hE7lsF/DZv5ClOFeQ345dFJrPKy8gM6tbs5esTNsofCPfINJ+jre9GU=
---

# Character Memory | 角色一致性系统

## Overview

The Character Memory system is one of AI_Manga_Studio's most critical innovations. It treats characters as **database objects** — not ad-hoc prompt strings — ensuring that every generated image and video consistently represents the same character across hundreds or thousands of frames.

## Responsibilities

- Maintain a persistent, versioned character database
- Define character identity cards with appearance, personality, costume, and background
- Lock visual traits after first image generation to enforce consistency
- Manage character relationships as a dynamic graph
- Track character state changes across the narrative timeline
- Provide context-aware character descriptions for prompt generation

## Design Philosophy

> **A character is a database object, not a prompt.**
>
> Prompts are ephemeral and context-dependent. A character database entry is authoritative, versioned, and queried consistently by every part of the pipeline.

## Character Card Structure

```json
{
  "character_id": "char_001",
  "name": "Ye Fan",
  "aliases": ["Little Fan", "The Sword Saint"],
  "identity_card": {
    "age": 19,
    "gender": "male",
    "role": "protagonist",
    "background": "A young cultivator from a declining clan who discovers an ancient sword..."
  },
  "appearance": {
    "height": "178cm",
    "build": "lean, athletic",
    "face": "sharp jawline, determined eyes, faint scar on left cheek",
    "hair": "black, shoulder-length, tied in a simple ponytail",
    "eyes": "deep blue, faintly glowing when using spiritual power",
    "skin": "fair, slightly tanned from training"
  },
  "costume": {
    "default": {
      "description": "Dark blue cultivator's robe with silver trim, worn leather boots, jade pendant at waist",
      "reference_image_id": "ref_img_042",
      "locked": true
    },
    "variants": {
      "battle_damaged": {
        "description": "Same robe but torn at left shoulder, dust and blood stains",
        "conditions": "after major battle scenes"
      },
      "ceremonial": {
        "description": "White silk robe with golden dragon embroidery, jade crown",
        "conditions": "formal occasions, end of story arc"
      }
    }
  },
  "expression_set": [
    {"name": "determined", "description": "Furrowed brows, slightly narrowed eyes, firm mouth"},
    {"name": "surprised", "description": "Wide eyes, slightly open mouth, raised eyebrows"},
    {"name": "calm", "description": "Relaxed face, neutral expression, eyes half-lidded in meditation"}
  ],
  "relationships": [
    {"target_id": "char_002", "name": "Lin Xue", "type": "love_interest", "dynamic": "developing"},
    {"target_id": "char_003", "name": "Master Zhang", "type": "mentor", "dynamic": "respectful"}
  ],
  "memory": {
    "key_events": [
      "Discovered the Heavenly Sword in Chapter 1",
      "First duel with Shadow Sect assassin in Chapter 5",
      "Reached Foundation Establishment realm in Chapter 18"
    ],
    "current_state": {
      "cultivation_level": "Foundation Establishment",
      "location": "Dark Forest",
      "emotional_state": "determined",
      "last_updated_chapter": 25
    }
  },
  "consistency_lock": {
    "appearance_locked": true,
    "appearance_locked_at": "2026-07-15T10:30:00Z",
    "appearance_locked_by": "generated_image_ch1_shot5",
    "reference_images": ["ref_img_042", "ref_img_043", "ref_img_044"]
  }
}
```

## Consistency Lock Mechanism

The consistency lock is the core mechanism that prevents character appearance drift:

1. **Initial Generation**: First batch of character images is generated based on the appearance description
2. **Human Review**: Creator reviews and selects the best representation
3. **Lock Applied**: Selected images are locked as reference; appearance description is frozen
4. **All Subsequent Generations**: Use the locked reference + description for prompt construction
5. **Lock Violation Detection** (future): Automated comparison of new outputs against reference images

## Input

- Character data from Story Parser (initial extraction)
- User edits and refinements via UI
- Reference images for appearance locking
- Narrative updates (character state changes from new chapters)

## Output

- Character Card JSON (full profile)
- Prompt-ready character descriptions (context-aware, formatted for specific AI providers)
- Relationship graph data
- Consistency-verified appearance references

## Workflow

```
1. Story Parser extracts character mentions → Raw character list
2. LLM generates detailed character profiles → Draft Character Cards
3. Creator reviews and edits → Final Character Cards
4. First image batch generated → Creator selects best representation
5. Appearance lock applied → Character is now "consistent"
6. All future prompts reference locked character data
7. Narrative events update character state (location, emotion, costume variants)
```

## Database Schema (Conceptual)

```
characters
├── id (PK)
├── name
├── identity_card (JSON)
├── appearance (JSON)
├── costume_default (JSON)
├── costume_variants (JSON)
├── expression_set (JSON)
├── consistency_locked (BOOL)
├── locked_at (TIMESTAMP)
├── reference_images (JSON)
├── created_at
└── updated_at

character_relationships
├── id (PK)
├── character_id (FK → characters)
├── target_id (FK → characters)
├── relationship_type
├── dynamic
└── metadata (JSON)

character_state_history
├── id (PK)
├── character_id (FK → characters)
├── chapter_id
├── state_snapshot (JSON)
└── recorded_at
```

## Future

- Automated consistency verification using image similarity models
- Voice profile locking for TTS consistency
- Emotion-driven expression blending
- Age progression across long time-skips
- Multi-artist style adaptation while preserving character identity
*（内容由AI生成，仅供参考）*
