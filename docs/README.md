---
AIGC:
    Label: "1"
    ContentProducer: 001191440300708461136T1XGW3
    ProduceID: ac05b1368557ee08912a0f1b051adb10_25f0f74686a911f18766525400f8a581
    ReservedCode1: 9MUTD84s7V6tHD3+vEj80bxus+ZfeKwuoyior4/jkP0CK54+9r0MjCpU3m7zhgKNKpfp5RHMlgC/zR1OuzjsZjilOLucEKC4bwe3JBNKI/deV2ZvkE4mDBeOGpLZKIxT9SJcU78s81DsO07OTLFObmyT1AAFNOipfDNh4f/YITsYA+wxbA2IAfD4gj8=
    ContentPropagator: 001191440300708461136T1XGW3
    PropagateID: ac05b1368557ee08912a0f1b051adb10_25f0f74686a911f18766525400f8a581
    ReservedCode2: 9MUTD84s7V6tHD3+vEj80bxus+ZfeKwuoyior4/jkP0CK54+9r0MjCpU3m7zhgKNKpfp5RHMlgC/zR1OuzjsZjilOLucEKC4bwe3JBNKI/deV2ZvkE4mDBeOGpLZKIxT9SJcU78s81DsO07OTLFObmyT1AAFNOipfDNh4f/YITsYA+wxbA2IAfD4gj8=
---

# AI_Manga_Studio Documentation | 文档导航

Welcome to the AI_Manga_Studio documentation. This index helps you navigate the project's architecture, design decisions, and development guides.

## Getting Started

- [README.md](../README.md) — Project overview, features, and quick start
- [Architecture.md](Architecture.md) — System architecture (six-layer design)
- [Deployment.md](Deployment.md) — Installation and deployment guide

## Core Systems

- [Workflow.md](Workflow.md) — Workflow engine: DAG orchestration, retry, checkpoint
- [StoryParser.md](StoryParser.md) — Novel parsing: chapter, scene, dialogue, timeline
- [CharacterMemory.md](CharacterMemory.md) — Character consistency system and memory
- [StoryboardPlanner.md](StoryboardPlanner.md) — Shot-by-shot storyboard planning
- [PromptEngine.md](PromptEngine.md) — Automatic prompt generation pipeline

## Production

- [VideoPipeline.md](VideoPipeline.md) — Video assembly, subtitle, voice, rendering

## Integration & Extension

- [ProviderSDK.md](ProviderSDK.md) — AI provider interface definitions
- [PluginSDK.md](PluginSDK.md) — Plugin development guide and lifecycle
- [API.md](API.md) — REST API reference

## Data

- [Database.md](Database.md) — Data models and entity relationships

## Document Format

All documents follow a consistent structure:
1. **Overview** — What this module does and why it exists
2. **Responsibilities** — Core responsibilities and boundaries
3. **Input** — Expected inputs and formats
4. **Output** — Produced outputs and formats
5. **Workflow** — Step-by-step process description
6. **API** — Interface definitions (where applicable)
7. **Future** — Planned improvements and roadmap items
*（内容由AI生成，仅供参考）*
