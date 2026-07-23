"""Application settings via pydantic-settings."""

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class AppSettings(BaseSettings):
    """Central configuration for AI Manga Studio backend."""

    model_config = SettingsConfigDict(
        env_prefix="AIMS_",
        env_file=".env",
        extra="ignore",
    )

    environment: str = "development"

    database_url: str = "sqlite+aiosqlite:///./data/app.db"
    projects_root: Path = Path("./data/projects")

    auto_migrate: bool = False
    worker_count: int = 1
    job_poll_interval_seconds: float = 0.5

    log_level: str = "INFO"

    fake_provider_enabled: bool = True
