"""
AI Manga Studio Pro V1.0 — Routes Package
"""

from .project import router as project_router
from .generation import router as generation_router
from .monitor import router as monitor_router
from .shot import router as shot_router
from .llm import router as llm_router

__all__ = [
    "project_router",
    "generation_router",
    "monitor_router",
    "shot_router",
    "llm_router",
]
