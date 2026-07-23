---
AIGC:
    Label: "1"
    ContentProducer: 001191440300708461136T1XGW3
    ProduceID: ac05b1368557ee08912a0f1b051adb10_225570a186a911f18108525400287e28
    ReservedCode1: zShYIcC5xw8q8WRwDRcrHaW2V0O3c7ifSfZojGUwMuGlyktRT3M3qW88HbT9P7jvVKAucmB6m6IeXgf60QE8l+VpcqQCHQIkb3Te0ZufzkR8WYpGYSzFGT/m+h2rghcptl+oUAf/YGnPGjJQuq3UN2oNyqq8HsEdEmqNQHXdPpMNx+pOjKTNptS4hOc=
    ContentPropagator: 001191440300708461136T1XGW3
    PropagateID: ac05b1368557ee08912a0f1b051adb10_225570a186a911f18108525400287e28
    ReservedCode2: zShYIcC5xw8q8WRwDRcrHaW2V0O3c7ifSfZojGUwMuGlyktRT3M3qW88HbT9P7jvVKAucmB6m6IeXgf60QE8l+VpcqQCHQIkb3Te0ZufzkR8WYpGYSzFGT/m+h2rghcptl+oUAf/YGnPGjJQuq3UN2oNyqq8HsEdEmqNQHXdPpMNx+pOjKTNptS4hOc=
---

# AI_Manga_Studio

> **Open-source AI Story Production Infrastructure**
>
> Novel → Character → Storyboard → Manga → Video

[![CI](https://github.com/Aix9527/AI_Manga_Studio/actions/workflows/ci.yml/badge.svg)](https://github.com/Aix9527/AI_Manga_Studio/actions/workflows/ci.yml)
[![Python](https://img.shields.io/badge/Python-3.11%2B-blue)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.109%2B-009688)](https://fastapi.tiangolo.com/)
[![ComfyUI](https://img.shields.io/badge/ComfyUI-Experimental-orange)](https://github.com/comfyanonymous/ComfyUI)
[![License](https://img.shields.io/badge/License-Apache%202.0-green)](LICENSE)
[![Open Source](https://img.shields.io/badge/Open%20Source-Yes-brightgreen)]()
[![AI Workflow](https://img.shields.io/badge/AI%20Workflow-Alpha-blueviolet)]()
[![Platform](https://img.shields.io/badge/Platform-Windows%20%7C%20Linux-lightgrey)]()
[![Status](https://img.shields.io/badge/Status-v0.1%20Alpha-yellow)]()

---

## Project Introduction | 项目简介

**English:**

AI_Manga_Studio is an open-source production platform that transforms long-form stories into visual content through an AI-native workflow. It bridges the gap between standalone AI tools (ChatGPT, ComfyUI, Flux, Wan, ElevenLabs) and actual content production by orchestrating them into a unified, recoverable, and extensible pipeline — from novel parsing to character management, storyboard planning, prompt generation, image/video synthesis, and final assembly.

**中文：**

AI_Manga_Studio 是一个面向 AI 漫剧、漫画和视频创作的开源生产平台，能够将长篇小说自动转换为角色、分镜、画面和视频等结构化成果。它将分散的 AI 工具（ChatGPT、ComfyUI、Flux、Wan、ElevenLabs 等）整合为统一、可恢复、可扩展的生产流水线——覆盖从小说解析、角色管理、分镜规划、Prompt 生成到图像/视频合成与最终成片的完整流程。

---

## Why AI_Manga_Studio | 为什么需要这个项目

Today, most AI tools can only perform single steps:

- ChatGPT writes stories
- ComfyUI generates images
- Flux generates images
- Wan generates videos
- ElevenLabs provides voiceover

What's missing is a system that **organizes these capabilities into a complete production workflow**. Creators are forced to manually chain tools together, losing track of character consistency, scene continuity, and narrative coherence along the way.

AI_Manga_Studio is designed to fill this gap. It is not a collection of tools — it is a **production infrastructure** that treats the entire creative process as a structured, recoverable, and reviewable pipeline.

---

## Current Implementation Status | 当前实现状态

AI_Manga_Studio is currently an **alpha-stage architecture and backend implementation**.
The table below distinguishes runnable foundations from experimental and planned capabilities.

| Capability | Status |
|---|---|
| FastAPI application bootstrap and health API | Available |
| SQLite/SQLAlchemy persistence foundation | Available |
| Project, narrative, character, storyboard, media, generation and workflow module skeletons | Available |
| Fake image provider | Experimental |
| Job runtime and recovery | Experimental |
| ComfyUI adapter | Experimental |
| Full browser UI | Planned |
| End-to-end video, voice and final rendering | Planned |

---

## Core Features | 核心功能

The sections below describe the target product architecture. Refer to the status table above for current availability.

### Story Intelligence | 故事智能
- **Novel Parsing** — Parse long-form novels into structured chapters, scenes, and segments
- **Scene Detection** — Automatically identify scene boundaries, locations, and time shifts
- **Dialogue Extraction** — Extract character dialogues with speaker attribution and context
- **Timeline Analysis** — Build chronological event timelines from narrative text

### Character Engine | 角色引擎
- **Character Memory** — Persistent character database across the entire production pipeline
- **Identity Card** — Structured profile including appearance, personality, background, and role
- **Relationship Graph** — Dynamic relationship mapping between all characters
- **Appearance Lock** — Lock visual traits to ensure consistency across all generated images
- **Consistency** — Characters are database objects, not ad-hoc prompts

### Storyboard | 分镜系统
- **Automatic Shot Planning** — AI-driven shot decomposition from scenes
- **Camera Language** — Shot types (close-up, medium, wide), angles, and movement
- **Composition** — Frame composition guidelines for each shot
- **Shot Duration** — Timing estimation for video production
- **Action Planning** — Character positioning and movement within shots

### Generation | 生成引擎
- **Prompt Generation** — Auto-generate prompts from character, scene, style, and action data
- **Negative Prompt** — Automatic negative prompt construction for quality control
- **Style Prompt** — Style-specific prompt templates and modifiers
- **Scene Prompt** — Context-aware scene description generation
- **Motion Prompt** — Motion and animation prompt generation for video

### Production | 内容生产
- **Image Generation** — Multi-provider image synthesis (ComfyUI, Flux, etc.)
- **Video Generation** — Frame sequence to video with transitions
- **Subtitles** — Automatic subtitle generation and synchronization
- **Voice** — Text-to-speech integration for dialogue and narration
- **Rendering** — Final assembly with audio, subtitles, and effects

---

## Demo Workflow | 演示流程

```
Novel (小说)
  ↓
Story Parser (故事解析)
  ↓
Character Memory (角色记忆)
  ↓
Scene Split (场景切分)
  ↓
Storyboard Planner (分镜规划)
  ↓
Prompt Generator (Prompt 生成)
  ↓
Image Provider (图像生成)
  ↓
Video Provider (视频生成)
  ↓
Editor (编辑合成)
  ↓
Final Drama (最终成片)
```

---

## Architecture | 系统架构

AI_Manga_Studio uses a **six-layer architecture**:

| Layer | Responsibility | Description |
|-------|---------------|-------------|
| **UI Layer** | Human interaction | Web UI, Project Manager, Timeline, Preview, Review |
| **API Layer** | Service interface | REST API, Job API, Project API, Authentication (future) |
| **Workflow Layer** | Orchestration brain | DAG scheduling, Queue management, Retry/Resume/Checkpoint |
| **AI Layer** | Intelligence core | Story Parser, Character Agent, Storyboard Agent, Prompt Agent, Video Agent |
| **Memory Layer** | Context persistence | Character Memory, Scene Memory, Project Memory, Long Story Context |
| **Provider Layer** | Model abstraction | OpenAI, Ollama, OpenRouter, ComfyUI, Flux, Wan, ElevenLabs, Fish Audio |

```
UI Layer (Web UI / Project Manager / Timeline / Preview)
  ↓
API Layer (REST API / Job API)
  ↓
Workflow Layer (DAG / Queue / Retry / Resume / Checkpoint)
  ↓
AI Layer (Story Parser / Character Agent / Storyboard Agent / Prompt Agent / Video Agent)
  ↓
Memory Layer (Character Memory / Scene Memory / Project Memory / Global Context)
  ↓
Provider Layer (OpenAI / Ollama / ComfyUI / Flux / Wan / ElevenLabs / Fish Audio)
```

---

## Core Modules | 核心模块

### Story Parser | 故事解析器
The Story Parser ingests novels in various formats and produces structured data: chapter boundaries, scene segmentation, character appearances, dialogue blocks, action descriptions, and temporal markers. It is the entry point of the entire pipeline.

### Character Manager | 角色管理器
The Character Manager maintains a persistent, queryable database of all characters. Each character is a rich object with appearance descriptors, personality traits, costume definitions, relationship links, and historical memory. This ensures visual and narrative consistency throughout the production.

### Storyboard Planner | 分镜规划器
The Storyboard Planner converts scene descriptions into detailed shot lists with camera language (shot type, angle, movement), composition notes, action staging, and timing estimates. Output is a structured Storyboard JSON ready for prompt generation.

### Workflow Engine | 工作流引擎
The Workflow Engine orchestrates the entire production as a DAG (Directed Acyclic Graph) of stages and tasks. It supports queuing, retry with backoff, checkpoint-based resume, and rollback — ensuring long-running productions can recover from failures at any stage.

---

## Installation | 安装

```bash
# Clone the repository
git clone https://github.com/YOUR_USERNAME/AI_Manga_Studio.git
cd AI_Manga_Studio

# Create virtual environment
python -m venv .venv

# Activate (Windows)
.venv\Scripts\activate

# Activate (Linux/macOS)
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Run
python run.py
```

---

## Quick Start | 快速开始

```
1. Install dependencies
2. Start the FastAPI service with `python run.py`
3. Open `/docs` to inspect the currently available API
4. Use the Fake Provider for development and integration testing
5. Track production-pipeline milestones in the Roadmap
```

---

## Project Structure | 项目结构

```
AI_Manga_Studio/
├── backend/          # FastAPI backend server and API routes
├── frontend/         # Web UI (future)
├── workflow/         # Workflow engine: DAG, queue, retry, checkpoint
├── plugins/          # Plugin system: AI providers, exporters, validators
├── sdk/              # SDK for third-party plugin development
├── docs/             # Architecture and development documentation
├── tests/            # Unit and integration tests
├── examples/         # Example novels, configurations, and workflows
├── assets/           # Static assets (icons, images, templates)
├── novels/           # Sample novels and test data
├── storage/          # Persistent storage (database, character memory)
├── output/           # Generated outputs (images, videos, subtitles)
└── scripts/          # Utility and maintenance scripts
```

---

## Roadmap | 开发路线图

| Version | Goal | Key Deliverables |
|---------|------|------------------|
| **v0.1** | Novel Parser + Character Manager | Story parsing, character extraction, basic memory, project database |
| **v0.2** | Storyboard + Prompt Engine | Scene-to-shot decomposition, camera language, auto-prompt generation |
| **v0.3** | ComfyUI + Image Generation | ComfyUI adapter, multi-provider image pipeline, style control |
| **v0.4** | Video Pipeline | Frame-to-video assembly, transitions, subtitle overlay, voice sync |
| **v0.5** | Plugin SDK | Plugin lifecycle, custom provider registration, export plugins |
| **v1.0** | Production Studio | Full UI, batch production, review system, cloud deployment support |

---

## Plugin System | 插件系统

AI_Manga_Studio is designed for extensibility. All AI providers are plugins implementing standard interfaces:

- **ComfyUI** — Local and remote ComfyUI workflow execution
- **OpenAI** — GPT-4, GPT-4o, and future models
- **OpenRouter** — Unified access to 200+ models
- **Ollama** — Local LLM execution (Llama, Mistral, etc.)
- **Flux** — Image generation (via ComfyUI or direct API)
- **Wan** — Video generation
- **ElevenLabs** — Neural voice synthesis
- **Fish Audio** — Open-source TTS
- **Stable Audio** — Music and sound effects generation

Plugins can be added without modifying core code. Each provider implements a standard interface (`ImageProvider`, `VideoProvider`, `LLMProvider`, `AudioProvider`).

---

## Supported AI Providers | AI Provider 支持状态

| Provider / Type | Status |
|---|---|
| Fake image provider | Experimental |
| ComfyUI image adapter | Experimental |
| OpenAI / OpenRouter / Ollama LLM adapters | Planned |
| Flux / SDXL production workflows | Planned |
| Wan / Runway / Pika / Sora video adapters | Planned |
| ElevenLabs / Fish Audio / Stable Audio | Planned |

---

## Demo Walkthrough

> All steps below use the **Fake Image Provider** — no external API key required.

```bash
# 1. Start the server
python run.py

# 2. Create a project
curl -X POST http://127.0.0.1:8000/api/v1/projects \
  -H "Content-Type: application/json" \
  -d '{"title": "星海迷途", "description": "一个关于星际旅行的故事"}'

# 3. Import a novel chapter
curl -X POST http://127.0.0.1:8000/api/v1/projects/{project_id}/narrative \
  -H "Content-Type: application/json" \
  -d '{"title": "Chapter 1", "content": "林深醒来时，发现自己躺在一艘废弃的星际飞船里。舷窗外是陌生的星系，记忆一片空白。她摸索着站起身，手腕上的生物芯片闪烁着微弱的蓝光..."}'

# 4. Extract characters
curl -X POST http://127.0.0.1:8000/api/v1/projects/{project_id}/characters/extract

# 5. List extracted characters (structured data)
curl http://127.0.0.1:8000/api/v1/projects/{project_id}/characters

# 6. Generate storyboard from narrative
curl -X POST http://127.0.0.1:8000/api/v1/projects/{project_id}/storyboard/generate

# 7. Create a generation task (Fake Provider returns a placeholder)
curl -X POST http://127.0.0.1:8000/api/v1/generation/tasks \
  -H "Content-Type: application/json" \
  -d '{"storyboard_id": "{storyboard_id}", "provider": "fake-image"}'

# 8. Query task result
curl http://127.0.0.1:8000/api/v1/generation/tasks/{task_id}
```

### What this demonstrates

| Step | Module | What happens |
|------|--------|-------------|
| 1 | Bootstrap | FastAPI app starts, SQLite DB created, container wired |
| 2 | Projects | Project entity persisted to SQLite |
| 3 | Narrative | Novel text stored and associated with project |
| 4 | Characters | Character extraction pipeline runs (structured output) |
| 5 | Characters | Extracted characters returned as typed data |
| 6 | Storyboard | Scene decomposition from narrative |
| 7 | Generation | Task created, Fake Provider enqueued |
| 8 | Generation | Task status and result retrieved |

## Contributing | 贡献指南

We welcome contributions of all kinds — code, documentation, bug reports, feature requests, and plugin development.

```
Fork → Branch → Commit → Pull Request
```

See [CONTRIBUTING.md](CONTRIBUTING.md) for detailed guidelines.

---

## License | 许可证

AI_Manga_Studio is licensed under the [Apache License 2.0](LICENSE).

**Important note:** Third-party models, weights, datasets, and media assets may be subject to their own licenses. Using AI_Manga_Studio does not automatically grant rights to use third-party models or their outputs for commercial purposes. Please verify the license terms of each AI provider and model you use.

---

## Acknowledgments | 致谢

AI_Manga_Studio builds upon the incredible work of the open-source community:

- [ComfyUI](https://github.com/comfyanonymous/ComfyUI) — Visual workflow engine
- [FastAPI](https://fastapi.tiangolo.com/) — Web framework
- [Flux](https://github.com/black-forest-labs/flux) — Image generation
- [Wan](https://github.com/Wan-Video/Wan2.1) — Video generation
- And all the model creators, dataset curators, and open-source contributors who make AI content creation possible.
