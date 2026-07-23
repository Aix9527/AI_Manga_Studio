"""
Settings & Configuration (Part 8)

Centralized configuration management using Pydantic Settings.
Loads from environment variables, .env files, and YAML config.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """
    Application-wide configuration.

    Sources (priority order):
    1. Environment variables (AI_MANGA_ prefix)
    2. .env file in project root
    3. Default values below
    """

    # ── Application ────────────────────────────────────────
    app_name: str = "AI Manga Studio"
    app_version: str = "1.0.0"
    debug: bool = False
    environment: str = "development"

    # ── Database ───────────────────────────────────────────
    database_url: str = "sqlite+aiosqlite:///./data/ai_manga.db"
    database_pool_size: int = 5
    database_echo: bool = False

    # ── API Server ─────────────────────────────────────────
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    api_workers: int = 1
    cors_origins: list[str] = ["http://localhost:3000"]

    # ── File Storage ───────────────────────────────────────
    workspace_root: str = str(Path(__file__).parent.parent.parent)
    data_dir: str = "data"
    assets_dir: str = "assets"
    temp_dir: str = "temp"
    export_dir: str = "exports"

    # ── Workflow Engine ────────────────────────────────────
    workflow_max_retries: int = 3
    workflow_retry_delay_seconds: int = 5
    workflow_timeout_seconds: int = 3600
    workflow_concurrency: int = 4

    # ── Provider Defaults ──────────────────────────────────
    default_llm_provider: str = "openai"
    default_image_provider: str = "flux"
    default_video_provider: str = "wan"
    default_audio_provider: str = "elevenlabs"
    enable_local_providers: bool = True
    enable_cloud_providers: bool = True

    # ── Provider API Keys ──────────────────────────────────
    openai_api_key: Optional[str] = None
    openrouter_api_key: Optional[str] = None
    elevenlabs_api_key: Optional[str] = None
    comfyui_url: str = "http://127.0.0.1:8188"
    ollama_url: str = "http://127.0.0.1:11434"

    # ── Resource Limits ────────────────────────────────────
    max_upload_mb: int = 500
    max_temp_space_gb: float = 20.0
    render_memory_limit_mb: int = 4096

    # ── Logging ────────────────────────────────────────────
    log_level: str = "INFO"
    log_format: str = "json"

    # ── Feature Flags ──────────────────────────────────────
    feature_lip_sync: bool = False
    feature_multi_user: bool = False
    feature_plugin_marketplace: bool = False

    class Config:
        env_prefix = "AI_MANGA_"
        env_file = ".env"
        env_file_encoding = "utf-8"


# Singleton
_settings: Optional[Settings] = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings
