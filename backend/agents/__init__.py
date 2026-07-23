"""
Agent System — AI Agent layer (Part 9)

The most important layer of the platform. Each agent is a specialized
AI module responsible for one stage of the creative pipeline:

    StoryAgent     — Novel parsing and story analysis
    CharacterAgent — Character extraction, design, and consistency
    SceneAgent     — Scene breakdown and continuity management
    PromptAgent    — Prompt engineering and optimization
    VideoAgent     — Video generation orchestration
    VoiceAgent     — Voice synthesis and audio management

All agents extend BaseAgent, which provides:
- LLM provider integration
- Memory system access
- Event publishing
- Checkpoint persistence
- Configurable retry logic
"""

from backend.agents.base_agent import BaseAgent

__all__ = ["BaseAgent"]
