"""
AI Manga Studio — Backend Package (Part 8-18)

DDD + Agent + Workflow + Provider + Event combination architecture.

Package structure:
    api/            REST + WebSocket + SSE endpoints (Part 14)
    core/           Shared kernel, value objects, exceptions (Part 8)
    orchestration/  Job manager, queue, worker, checkpoint (Part 12)
    agents/         AI agents (Story, Character, Scene, Prompt, Video, Voice) (Part 9)
    memory/         Character/Scene/Project memory system (Part 10)
    providers/      LLM/Image/Video/Audio provider abstraction (Part 11)
    workflow/       DAG workflow engine (Part 12)
    projects/       Project aggregate domain logic (Part 8)
    assets/         Asset pipeline & media processing (Part 16)
    exporter/       Export engine & timeline editor (Part 17)
    plugins/        Plugin SDK & extension architecture (Part 18)
    sdk/            Public SDK surface for plugin developers (Part 18)
    repositories/   Data access layer (Part 13)
    services/       Business logic orchestration (Part 8)
    events/         Event-driven communication bus (Part 8)
    scheduler/      Cron-based task scheduler (Part 8)
    config/         Central configuration management (Part 8)
    utils/          Shared utility functions (Part 8)
    database.py     ORM models & DatabaseManager (Part 13)
"""

__version__ = "1.0.0"
