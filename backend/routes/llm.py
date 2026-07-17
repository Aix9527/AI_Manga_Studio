"""
AI Manga Studio Pro V1.0 — LLM Service Routes

REST API endpoints for the LLM narrative parsing service.
"""

from fastapi import APIRouter, HTTPException
from loguru import logger

from backend.llm_service import (
    LLMStatusResponse,
    StoryParseRequest,
    StoryParseResponse,
    get_llm_service,
)

router = APIRouter(prefix="/llm", tags=["LLM Service"])


@router.get("/status", response_model=LLMStatusResponse)
async def llm_status() -> LLMStatusResponse:
    """Check LLM service availability and provider status.

    Returns current provider type, latency, and availability.
    """
    service = get_llm_service()
    return await service.check_status()


@router.post("/parse", response_model=StoryParseResponse)
async def parse_story(request: StoryParseRequest) -> StoryParseResponse:
    """Parse a novel into structured Story JSON.

    Accepts full novel text and returns chapter-by-chapter storyboard
    with characters, scenes, shots, camera directives, and prompts.

    Uses LLM if available, otherwise falls back to rule-based AIDirector.
    """
    if not request.text.strip():
        raise HTTPException(status_code=400, detail="Novel text is required")

    if len(request.text) < 50:
        raise HTTPException(status_code=400, detail="Text too short (minimum 50 characters)")

    service = get_llm_service()
    logger.info(
        f"LLM parse request: title={request.title}, chars={len(request.text)}, "
        f"use_llm={request.use_llm}"
    )
    return await service.parse_story(request)


@router.get("/health")
async def llm_health() -> dict:
    """Quick health check for the LLM service."""
    service = get_llm_service()
    status = await service.check_status()
    return {
        "service": "llm_service",
        "online": status.available,
        "provider": status.provider.value,
        "model": status.model,
    }
