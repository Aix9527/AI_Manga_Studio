"""
AI Manga Studio Pro V1.0 — Pydantic Data Models

Request / response schemas used across the FastAPI application.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional
from enum import Enum

from pydantic import BaseModel, Field

# Re-export UnifiedShot as the canonical shot model
from backend.unified_shot import (
    UnifiedShot, ShotBatch, Camera, Emotion, Weather, TimeOfDay, Lighting,
    ShotStatus as UnifiedShotStatus,
)


# ============================================================
# Enums
# ============================================================

class ProjectStatus(str, Enum):
    pending = "pending"
    running = "running"
    completed = "completed"
    failed = "failed"


class ShotStatus(str, Enum):
    waiting = "waiting"
    generating = "generating"
    success = "success"
    failed = "failed"


class ShotType(str, Enum):
    close_up = "CloseUp"
    medium = "Medium"
    wide = "Wide"
    drone = "Drone"
    pov = "POV"
    tracking = "Tracking"
    dutch_angle = "DutchAngle"
    over_shoulder = "OverShoulder"
    two_shot = "TwoShot"


class TaskType(str, Enum):
    generate_image = "generate_image"
    generate_video = "generate_video"
    lipsync = "lipsync"
    voice = "voice"
    merge = "merge"


# ============================================================
# Project
# ============================================================

class ProjectCreate(BaseModel):
    name: str = Field(..., max_length=256)
    description: str = ""
    source_type: str = "novel"
    source_path: str = ""


class ProjectResponse(BaseModel):
    id: int
    name: str
    description: str
    status: ProjectStatus
    source_type: str
    source_path: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ProjectListResponse(BaseModel):
    projects: List[ProjectResponse]
    total: int


# ============================================================
# Chapter
# ============================================================

class ChapterResponse(BaseModel):
    id: int
    project_id: int
    index: int
    title: str
    status: str
    created_at: datetime

    model_config = {"from_attributes": True}


class ChapterDetailResponse(ChapterResponse):
    parsed_json: Optional[Dict[str, Any]] = None
    shots: List[ShotResponse] = []


# ============================================================
# Shot
# ============================================================

class ShotResponse(BaseModel):
    id: int
    chapter_id: int
    index: int
    shot_type: str
    camera_instruction: str
    motion_description: str
    emotion_description: str
    dialogue: str
    status: ShotStatus
    image_path: str
    video_path: str
    quality_score: float
    retry_count: int
    error_message: str
    created_at: datetime

    model_config = {"from_attributes": True}


class ShotRegenerateRequest(BaseModel):
    shot_id: int


# ============================================================
# Character
# ============================================================

class CharacterCreate(BaseModel):
    name: str = Field(..., max_length=128)
    alias: str = ""
    age: int = 0
    gender: str = "unknown"
    height_cm: float = 0.0
    body_type: str = ""
    hair_style: str = ""
    hair_color: str = ""
    eye_color: str = ""
    clothing: str = ""
    personality: str = ""
    voice_id: str = ""
    common_prompt: str = ""


class CharacterResponse(BaseModel):
    id: int
    project_id: int
    name: str
    alias: str
    age: int
    gender: str
    seed: int
    face_id: str
    lora_path: str
    voice_id: str
    created_at: datetime

    model_config = {"from_attributes": True}


class CharacterDetailResponse(CharacterResponse):
    height_cm: float
    body_type: str
    hair_style: str
    hair_color: str
    eye_color: str
    clothing: str
    personality: str
    voice_model: str
    common_prompt: str


# ============================================================
# Scene
# ============================================================

class SceneCreate(BaseModel):
    name: str = Field(..., max_length=256)
    description: str = ""
    weather: str = "clear"
    time_of_day: str = "day"
    lighting: str = ""


class SceneResponse(BaseModel):
    id: int
    project_id: int
    name: str
    description: str
    prompt_positive: str
    prompt_negative: str
    weather: str
    time_of_day: str
    lighting: str
    created_at: datetime

    model_config = {"from_attributes": True}


# ============================================================
# Task
# ============================================================

class TaskResponse(BaseModel):
    id: int
    shot_id: int
    task_type: str
    priority: int
    status: str
    error_message: str
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    created_at: datetime

    model_config = {"from_attributes": True}


# ============================================================
# AI Director
# ============================================================

class DirectorParseResult(BaseModel):
    """Output from AI Director after parsing a novel."""
    chapters: List[Dict[str, Any]] = []
    characters: List[Dict[str, Any]] = []
    scenes: List[Dict[str, Any]] = []
    total_shots: int = 0


class ShotPlan(BaseModel):
    """A planned shot from AI Director."""
    index: int
    shot_type: ShotType = ShotType.medium
    camera_instruction: str = ""
    prompt_positive: str = ""
    prompt_negative: str = ""
    motion_description: str = ""
    emotion_description: str = ""
    character_ids: List[int] = []
    scene_id: Optional[int] = None
    dialogue: str = ""


# ============================================================
# Monitor
# ============================================================

class GPUInfo(BaseModel):
    name: str
    memory_total_mb: float
    memory_used_mb: float
    memory_free_mb: float
    utilization_pct: float
    temperature_c: float


class SystemMonitorResponse(BaseModel):
    cpu_percent: float
    ram_total_gb: float
    ram_used_gb: float
    ram_free_gb: float
    gpus: List[GPUInfo]
    disk_total_gb: float
    disk_used_gb: float
    active_tasks: int
    queued_tasks: int


# ============================================================
# Generation
# ============================================================

class GenerationRequest(BaseModel):
    project_id: int
    chapter_ids: Optional[List[int]] = None
    max_shots: Optional[int] = None


class GenerationResponse(BaseModel):
    message: str
    project_id: int
    tasks_created: int


# ============================================================
# WebSocket
# ============================================================

class WSMessage(BaseModel):
    event: str
    data: Dict[str, Any] = {}
