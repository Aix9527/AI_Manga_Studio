---
AIGC:
    Label: "1"
    ContentProducer: 001191440300708461136T1XGW3
    ProduceID: ac05b1368557ee08912a0f1b051adb10_3038f2b386a911f18766525400f8a581
    ReservedCode1: /i8lPsAjKW6zzixFgQRICN5JtKunGvXCjAEfkqqlyygV3Iupq7OMGqjBZ+8DBR3Yw9ByQ5eRcRgDVwls4TR5S1Gbq7Gc8Y7ByU7SLKdcsYI4WAup3nT8g+oL4fim/7vu1ZpA380b5UNJASyH8SjY+onBk/H6IClMaZMUJZrwKxc2aeXTAQOMgTo0t9U=
    ContentPropagator: 001191440300708461136T1XGW3
    PropagateID: ac05b1368557ee08912a0f1b051adb10_3038f2b386a911f18766525400f8a581
    ReservedCode2: /i8lPsAjKW6zzixFgQRICN5JtKunGvXCjAEfkqqlyygV3Iupq7OMGqjBZ+8DBR3Yw9ByQ5eRcRgDVwls4TR5S1Gbq7Gc8Y7ByU7SLKdcsYI4WAup3nT8g+oL4fim/7vu1ZpA380b5UNJASyH8SjY+onBk/H6IClMaZMUJZrwKxc2aeXTAQOMgTo0t9U=
---

# REST API | API 参考文档

## Overview

AI_Manga_Studio exposes a RESTful API built with FastAPI. All endpoints return JSON and use standard HTTP status codes. The API is versioned under `/api/v1/`.

## Base URL

```
http://127.0.0.1:8000/api/v1
```

## Authentication

Authentication is planned for a future release. Currently, the API is intended for local use.

## Common Response Format

```json
{
  "status": "success",
  "data": { ... },
  "error": null
}
```

```json
{
  "status": "error",
  "data": null,
  "error": {
    "code": "NOT_FOUND",
    "message": "Project not found"
  }
}
```

## Endpoints

### Projects

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/projects` | List all projects |
| `POST` | `/projects` | Create a new project |
| `GET` | `/projects/{id}` | Get project details |
| `PUT` | `/projects/{id}` | Update project |
| `DELETE` | `/projects/{id}` | Delete project |

#### Create Project

```
POST /api/v1/projects
Content-Type: application/json

{
  "name": "Heavenly Sword Adaptation",
  "description": "Full manga adaptation of the Heavenly Sword novel",
  "novel_file_path": "/novels/heavenly_sword.txt",
  "style_config": {
    "art_style": "cinematic_anime",
    "aspect_ratio": "16:9",
    "color_palette": "cool"
  }
}
```

### Characters

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/projects/{id}/characters` | List characters in project |
| `POST` | `/projects/{id}/characters` | Create character |
| `GET` | `/characters/{id}` | Get character details |
| `PUT` | `/characters/{id}` | Update character |
| `POST` | `/characters/{id}/lock` | Lock character appearance |

### Scenes

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/projects/{id}/scenes` | List all scenes |
| `GET` | `/scenes/{id}` | Get scene details |
| `GET` | `/projects/{id}/chapters/{num}/scenes` | List scenes in chapter |

### Storyboard

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/projects/{id}/storyboard/generate` | Generate storyboard |
| `GET` | `/storyboards/{id}` | Get storyboard details |
| `GET` | `/storyboards/{id}/shots` | List all shots |
| `PUT` | `/shots/{id}` | Update individual shot |

### Jobs

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/projects/{id}/jobs` | Submit a new job |
| `GET` | `/jobs/{id}` | Get job status |
| `GET` | `/jobs/{id}/progress` | Get job progress (SSE) |
| `POST` | `/jobs/{id}/cancel` | Cancel a running job |
| `POST` | `/jobs/{id}/resume` | Resume a failed job |

#### Submit Job

```
POST /api/v1/projects/{project_id}/jobs
Content-Type: application/json

{
  "job_type": "image_generation",
  "config": {
    "storyboard_id": "sb_abc123",
    "shot_ids": ["shot_001", "shot_002"],
    "provider": "comfyui",
    "parallel_tasks": 4
  }
}
```

### Assets

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/projects/{id}/assets` | List all assets |
| `GET` | `/assets/{id}` | Get asset metadata |
| `GET` | `/assets/{id}/download` | Download asset file |
| `DELETE` | `/assets/{id}` | Delete asset |

### Providers

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/providers` | List all registered providers |
| `GET` | `/providers/{type}` | List providers by type |
| `GET` | `/providers/{type}/{name}/capabilities` | Get provider capabilities |

### System

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/health` | Health check |
| `GET` | `/info` | System information |

## Job Progress (Server-Sent Events)

```
GET /api/v1/jobs/{job_id}/progress
Accept: text/event-stream

data: {"stage": "storyboard", "progress": 0.45, "message": "Generating shot 12/24"}

data: {"stage": "image_gen", "progress": 0.70, "message": "Rendering shot ch12_shot_12"}

data: {"stage": "complete", "progress": 1.0, "message": "Job completed successfully"}
```

## Error Codes

| Code | HTTP Status | Description |
|------|-------------|-------------|
| `NOT_FOUND` | 404 | Resource not found |
| `VALIDATION_ERROR` | 422 | Invalid request data |
| `PROVIDER_ERROR` | 502 | AI provider returned an error |
| `PROVIDER_TIMEOUT` | 504 | AI provider timed out |
| `JOB_ALREADY_RUNNING` | 409 | Cannot modify a running job |
| `STAGE_FAILED` | 500 | Workflow stage execution failed |
| `CHECKPOINT_CORRUPT` | 500 | Cannot resume from corrupted checkpoint |

## Rate Limiting

Currently, there is no rate limiting on the local API. This will be added when multi-user support is implemented.

## OpenAPI Documentation

Interactive API documentation is available at:

- Swagger UI: `http://127.0.0.1:8000/docs`
- ReDoc: `http://127.0.0.1:8000/redoc`

## Future

- Authentication with API keys and JWT
- Rate limiting per user/project
- Webhook callbacks for job completion
- GraphQL endpoint for complex queries
- SDK client libraries (Python, JavaScript)
*（内容由AI生成，仅供参考）*
