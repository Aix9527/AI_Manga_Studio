---
AIGC:
    Label: "1"
    ContentProducer: 001191440300708461136T1XGW3
    ProduceID: ac05b1368557ee08912a0f1b051adb10_2e4f3b5d86a911f18108525400287e28
    ReservedCode1: mtGO7P4LofilHAvP0mDMfnaaDL7oCFPK9EAmnCfLppNYJYZ/sQzsQ2XNONrbtADAbJLI98FtLyd85fsfl09eX9TnIQc8JdGgmQ/n6f7u7VkxYbwcJGWjAY9ak4Ph+eulesK/uCK6k1fxXarf7QHrRq53+fVYW9OZCJme384bWkaRWK8vDwgD6e9Qj/I=
    ContentPropagator: 001191440300708461136T1XGW3
    PropagateID: ac05b1368557ee08912a0f1b051adb10_2e4f3b5d86a911f18108525400287e28
    ReservedCode2: mtGO7P4LofilHAvP0mDMfnaaDL7oCFPK9EAmnCfLppNYJYZ/sQzsQ2XNONrbtADAbJLI98FtLyd85fsfl09eX9TnIQc8JdGgmQ/n6f7u7VkxYbwcJGWjAY9ak4Ph+eulesK/uCK6k1fxXarf7QHrRq53+fVYW9OZCJme384bWkaRWK8vDwgD6e9Qj/I=
---

# Database | 数据模型

## Overview

AI_Manga_Studio uses a relational database (SQLite for local development, PostgreSQL planned for production) to persist all project data, character profiles, workflow state, and asset metadata. The schema is designed around the production pipeline — from novel ingestion to final video output.

## Entity-Relationship Overview

```
Project (项目)
 ├── Characters (角色)
 │    ├── CharacterStateHistory (角色状态历史)
 │    └── CharacterRelationships (角色关系)
 ├── Scenes (场景)
 │    └── Dialogues (对话)
 ├── Storyboards (分镜)
 │    └── Shots (镜头)
 │         └── Prompts (Prompt)
 ├── Jobs (作业)
 │    ├── Stages (阶段)
 │    └── Tasks (任务)
 ├── Assets (素材)
 │    ├── Images
 │    ├── Videos
 │    └── Audio
 └── Outputs (产出)
```

## Core Entities

### Project

| Field | Type | Description |
|-------|------|-------------|
| `id` | UUID (PK) | Unique project identifier |
| `name` | String | Human-readable project name |
| `description` | Text | Project description |
| `novel_file_path` | String | Path to source novel file |
| `style_config` | JSON | Global style configuration |
| `status` | Enum | draft / parsing / storyboard / generating / reviewing / completed |
| `created_at` | Timestamp | Creation time |
| `updated_at` | Timestamp | Last modification time |

### Character

| Field | Type | Description |
|-------|------|-------------|
| `id` | UUID (PK) | Unique character identifier |
| `project_id` | UUID (FK) | Parent project |
| `name` | String | Character name |
| `aliases` | JSON | Alternative names/nicknames |
| `identity_card` | JSON | Age, gender, role, background |
| `appearance` | JSON | Height, build, face, hair, eyes, skin |
| `costume_default` | JSON | Default costume description + reference image |
| `costume_variants` | JSON | Alternative costumes with conditions |
| `expression_set` | JSON | Named expression definitions |
| `consistency_locked` | Boolean | Whether appearance is frozen |
| `locked_at` | Timestamp | When lock was applied |
| `reference_images` | JSON | Reference image file IDs |
| `created_at` | Timestamp | First appearance in narrative |
| `updated_at` | Timestamp | Last update |

### CharacterRelationship

| Field | Type | Description |
|-------|------|-------------|
| `id` | UUID (PK) | Unique identifier |
| `character_id` | UUID (FK) | Source character |
| `target_id` | UUID (FK) | Target character |
| `relationship_type` | Enum | mentor/student, love_interest, rival, family, friend, enemy |
| `dynamic` | String | Description of relationship dynamics |
| `metadata` | JSON | Additional relationship data |

### Scene

| Field | Type | Description |
|-------|------|-------------|
| `id` | UUID (PK) | Unique scene identifier |
| `project_id` | UUID (FK) | Parent project |
| `chapter_id` | Integer | Chapter number |
| `scene_number` | Integer | Scene number within chapter |
| `location` | String | Scene location |
| `time_of_day` | String | Morning / afternoon / evening / night |
| `atmosphere` | Text | Atmospheric description |
| `characters_present` | JSON | List of character IDs in this scene |
| `narrative_summary` | Text | Scene summary |
| `raw_text` | Text | Original novel text for this scene |

### Dialogue

| Field | Type | Description |
|-------|------|-------------|
| `id` | UUID (PK) | Unique identifier |
| `scene_id` | UUID (FK) | Parent scene |
| `speaker_id` | UUID (FK) | Speaking character |
| `line_number` | Integer | Order within scene |
| `text` | Text | Dialogue content |
| `emotion` | String | Inferred emotion |
| `context` | Text | Surrounding narrative context |

### Storyboard

| Field | Type | Description |
|-------|------|-------------|
| `id` | UUID (PK) | Unique identifier |
| `project_id` | UUID (FK) | Parent project |
| `chapter_id` | Integer | Chapter number |
| `style` | String | Visual style description |
| `aspect_ratio` | String | e.g., "16:9", "9:16" |
| `total_shots` | Integer | Number of shots |
| `estimated_duration` | Float | Total duration in seconds |
| `status` | Enum | draft / review / approved |

### Shot

| Field | Type | Description |
|-------|------|-------------|
| `id` | UUID (PK) | Unique identifier |
| `storyboard_id` | UUID (FK) | Parent storyboard |
| `scene_id` | UUID (FK) | Source scene |
| `shot_number` | Integer | Order in storyboard |
| `shot_type` | String | wide / medium / close-up / etc. |
| `camera` | JSON | Angle, movement, focal length |
| `composition` | JSON | Framing, focus, depth of field |
| `character_ids` | JSON | Characters in shot |
| `action_description` | Text | What happens in this shot |
| `dialogue_id` | UUID (FK, nullable) | Associated dialogue |
| `duration_seconds` | Float | Estimated duration |
| `transition_in` | String | cut / fade / dissolve |
| `transition_out` | String | cut / fade / dissolve |

### Prompt

| Field | Type | Description |
|-------|------|-------------|
| `id` | UUID (PK) | Unique identifier |
| `shot_id` | UUID (FK) | Target shot |
| `provider` | String | Target AI provider |
| `positive` | Text | Positive prompt |
| `negative` | Text | Negative prompt |
| `style` | Text | Style-specific prompt |
| `motion` | Text | Motion prompt (video only) |
| `generated_at` | Timestamp | When prompt was created |

### Job

| Field | Type | Description |
|-------|------|-------------|
| `id` | UUID (PK) | Unique identifier |
| `project_id` | UUID (FK) | Parent project |
| `job_type` | String | parse / character_extract / storyboard / image_gen / video_gen |
| `status` | Enum | draft / queued / running / waiting_review / completed / failed |
| `config` | JSON | Job configuration |
| `checkpoint_data` | JSON | Resume checkpoint |
| `progress` | Float | 0.0 to 1.0 |
| `error` | JSON | Error details if failed |
| `created_at` | Timestamp | Creation time |
| `started_at` | Timestamp | Execution start |
| `completed_at` | Timestamp | Completion time |

### Asset

| Field | Type | Description |
|-------|------|-------------|
| `id` | UUID (PK) | Unique identifier |
| `project_id` | UUID (FK) | Parent project |
| `job_id` | UUID (FK) | Generating job |
| `shot_id` | UUID (FK, nullable) | Associated shot |
| `asset_type` | Enum | image / video / audio / subtitle |
| `file_path` | String | Absolute path to file |
| `file_size` | Integer | File size in bytes |
| `metadata` | JSON | Resolution, duration, codec, etc. |
| `status` | Enum | generated / reviewed / approved / rejected |
| `created_at` | Timestamp | Generation time |

## State Machine (Job)

```
Draft → Queued → Running → Waiting Review → Completed
  ↓        ↓        ↓
Failed   Failed   Failed
  └────────┴────────┘
           ↓
       Retrying
```

## Future

- PostgreSQL migration for multi-user production deployments
- Asset deduplication with content hashing
- Full-text search across novel text and dialogue
- Audit log for all data mutations
- Data export/import for project portability
- Automatic backup scheduling
*（内容由AI生成，仅供参考）*
