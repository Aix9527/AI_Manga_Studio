"""
Deployment — Docker, Kubernetes, and Environment Configuration (Part 22)

Provides deployment templates and configuration management
for production deployment of AI_Manga_Studio.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class DeploymentConfig:
    """Configuration for a deployment target."""
    environment: str = "production"  # production | staging | development
    host: str = "0.0.0.0"
    port: int = 8000
    workers: int = 4
    gpu_enabled: bool = False
    gpu_devices: list[int] = field(default_factory=lambda: [0])

    # Database
    database_url: str = "sqlite:///./data/ai_manga_studio.db"
    redis_url: str = ""

    # Storage
    asset_storage_path: str = "./data/assets"
    export_storage_path: str = "./data/exports"

    # Logging
    log_level: str = "INFO"
    log_json: bool = True

    # External APIs
    openai_api_key: str = ""
    comfyui_url: str = "http://localhost:8188"

    # Resource limits
    max_job_concurrency: int = 8
    max_asset_size_mb: int = 512
    rate_limit_per_minute: int = 60


# ── Docker Compose Generator ──────────────────────────────────────────

def generate_docker_compose(config: DeploymentConfig) -> str:
    """Generate a docker-compose.yml content string."""
    return f"""version: "3.9"

services:
  api:
    build:
      context: .
      dockerfile: Dockerfile
    ports:
      - "{config.port}:8000"
    environment:
      - DATABASE_URL={config.database_url}
      - LOG_LEVEL={config.log_level}
      - LOG_JSON={"true" if config.log_json else "false"}
    volumes:
      - {config.asset_storage_path}:/app/data/assets
      - {config.export_storage_path}:/app/data/exports
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: {len(config.gpu_devices)}
              capabilities: [gpu]
    restart: unless-stopped

  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"
    volumes:
      - redis_data:/data
    restart: unless-stopped

volumes:
  redis_data:
"""


def generate_dockerfile(base_image: str = "python:3.12-slim") -> str:
    """Generate a Dockerfile content string."""
    return f"""FROM {base_image}

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \\
    ffmpeg \\
    libgl1-mesa-glx \\
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application
COPY backend/ ./backend/
COPY frontend/dist/ ./frontend/dist/

# Create data directory
RUN mkdir -p /app/data/assets /app/data/exports

EXPOSE 8000

CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
"""


# ── Environment Generator ─────────────────────────────────────────────

def generate_env_file(config: DeploymentConfig) -> str:
    """Generate a .env file content string."""
    lines = [
        f"ENVIRONMENT={config.environment}",
        f"HOST={config.host}",
        f"PORT={config.port}",
        f"WORKERS={config.workers}",
        f"DATABASE_URL={config.database_url}",
        f"REDIS_URL={config.redis_url}",
        f"ASSET_STORAGE_PATH={config.asset_storage_path}",
        f"EXPORT_STORAGE_PATH={config.export_storage_path}",
        f"LOG_LEVEL={config.log_level}",
        f"LOG_JSON={'true' if config.log_json else 'false'}",
        f"COMFYUI_URL={config.comfyui_url}",
        f"MAX_JOB_CONCURRENCY={config.max_job_concurrency}",
        f"MAX_ASSET_SIZE_MB={config.max_asset_size_mb}",
        f"RATE_LIMIT_PER_MINUTE={config.rate_limit_per_minute}",
        "",
        "# API Keys (set these securely!)",
        "OPENAI_API_KEY=",
        "ELEVENLABS_API_KEY=",
    ]
    return "\n".join(lines)
