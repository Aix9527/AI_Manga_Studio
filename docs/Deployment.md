---
AIGC:
    Label: "1"
    ContentProducer: 001191440300708461136T1XGW3
    ProduceID: ac05b1368557ee08912a0f1b051adb10_2f5bc6c486a911f18766525400f8a581
    ReservedCode1: /tBlnmAaxqzl4lB8RdhYG/3Ng1ZxT9iyLTTXljG8cPtq8DAGXzwnwzAY/K87d73MV6jwE1Xab7/LPGQ6MWmFJ2h0uffi1fd7+VMcjcFEwQTc0JhTnB7x1qxehmL6hS1lCPl9t6Ld+63OkWH4Jo6Bg3DxEcSGkRx0eHLsjs4/O5pqzq08IKkzmNtt+kI=
    ContentPropagator: 001191440300708461136T1XGW3
    PropagateID: ac05b1368557ee08912a0f1b051adb10_2f5bc6c486a911f18766525400f8a581
    ReservedCode2: /tBlnmAaxqzl4lB8RdhYG/3Ng1ZxT9iyLTTXljG8cPtq8DAGXzwnwzAY/K87d73MV6jwE1Xab7/LPGQ6MWmFJ2h0uffi1fd7+VMcjcFEwQTc0JhTnB7x1qxehmL6hS1lCPl9t6Ld+63OkWH4Jo6Bg3DxEcSGkRx0eHLsjs4/O5pqzq08IKkzmNtt+kI=
---

# Deployment | 部署指南

## Overview

AI_Manga_Studio is designed to run on both Windows (primary development target) and Linux (server deployment). This document covers installation, configuration, and deployment options.

## System Requirements

### Minimum

| Component | Requirement |
|-----------|-------------|
| **OS** | Windows 10/11 or Ubuntu 22.04+ |
| **Python** | 3.11 or 3.12 |
| **RAM** | 8 GB |
| **Disk** | 10 GB free (more for model storage) |
| **GPU** | Optional (CPU-only mode supported for pipeline logic) |

### Recommended (for image/video generation)

| Component | Requirement |
|-----------|-------------|
| **GPU** | NVIDIA RTX 3060+ (12GB+ VRAM) or RTX 4090 (24GB) |
| **RAM** | 32 GB |
| **Disk** | 100 GB+ SSD (for models and outputs) |
| **ComfyUI** | Installed separately (or use remote ComfyUI) |

## Installation

### Windows (Local Development)

```powershell
# 1. Clone repository
git clone https://github.com/YOUR_USERNAME/AI_Manga_Studio.git
cd AI_Manga_Studio

# 2. Create virtual environment
python -m venv .venv
.venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Install dev dependencies (optional)
pip install -r requirements-dev.txt

# 5. Run
python run.py
```

### Linux (Server)

```bash
# 1. Clone repository
git clone https://github.com/YOUR_USERNAME/AI_Manga_Studio.git
cd AI_Manga_Studio

# 2. Create virtual environment
python3 -m venv .venv
source .venv/bin/activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Install system dependencies (Ubuntu/Debian)
sudo apt-get update
sudo apt-get install -y ffmpeg libgl1-mesa-glx

# 5. Run
python run.py
```

## Configuration

### Environment Variables

Create a `.env` file in the project root:

```bash
# AI_Manga_Studio Configuration

# Server
HOST=127.0.0.1
PORT=8000

# Database
DATABASE_URL=sqlite:///storage/ai_manga.db

# LLM Providers
OPENAI_API_KEY=sk-xxx
OPENROUTER_API_KEY=sk-xxx
OLLAMA_BASE_URL=http://localhost:11434

# Image Generation
COMFYUI_BASE_URL=http://127.0.0.1:8188

# Audio
ELEVENLABS_API_KEY=xxx
FISH_AUDIO_API_KEY=xxx

# Storage paths
OUTPUT_DIR=./output
TEMP_DIR=./temp
```

### ComfyUI Setup (Optional)

For local image/video generation:

1. Install ComfyUI separately: `git clone https://github.com/comfyanonymous/ComfyUI.git`
2. Download required models (Flux, Wan, etc.) into ComfyUI's `models/` directory
3. Load the AI_Manga_Studio workflow templates into ComfyUI
4. Start ComfyUI: `python main.py`
5. Configure `COMFYUI_BASE_URL` in AI_Manga_Studio's `.env`

### Ollama Setup (Optional)

For local LLM inference:

```bash
# Install Ollama
curl -fsSL https://ollama.com/install.sh | sh

# Pull models
ollama pull llama3.1:8b
ollama pull mistral:7b
```

## Deployment Options

### Option 1: Local Desktop (Current)

- Run directly on developer machine
- Best for: development, testing, single-user production
- ComfyUI runs on same machine
- No external dependencies required

### Option 2: Headless Server

- Run as a background service on Linux
- Best for: batch production, team shared instance
- ComfyUI can run on the same server or a separate GPU node

```bash
# Run as systemd service
sudo cp deploy/ai_manga_studio.service /etc/systemd/system/
sudo systemctl enable ai_manga_studio
sudo systemctl start ai_manga_studio
```

### Option 3: Docker (Planned)

```bash
# Docker support is planned for a future release
docker-compose up -d
# This will start: API server, database, and optional ComfyUI container
```

## Database

- **Development**: SQLite (file-based, zero configuration)
- **Production** (planned): PostgreSQL for concurrent access and reliability

Migration to PostgreSQL:

```bash
# Set environment variable
export DATABASE_URL=postgresql://user:password@localhost:5432/ai_manga

# Run migrations
alembic upgrade head
```

## Important Notes

### GPU is Optional

The workflow engine, story parser, character manager, and storyboard planner all run on CPU. GPU is only needed if you want to generate images/videos locally. You can use cloud API providers (OpenAI, OpenRouter) for LLM tasks and remote ComfyUI instances for image/video generation.

### ComfyUI is Optional

If you don't need local image/video generation, you can skip ComfyUI entirely and use cloud-based image/video APIs (when integrated).

### Local Models are Optional

All model-related features are optional. The pipeline logic, data management, and workflow orchestration work independently of any specific AI model.

## Troubleshooting

### Common Issues

| Issue | Solution |
|-------|----------|
| `ModuleNotFoundError` | Activate virtual environment and reinstall: `pip install -r requirements.txt` |
| ComfyUI connection refused | Ensure ComfyUI is running and `COMFYUI_BASE_URL` is correct |
| CUDA out of memory | Reduce batch size or use a smaller model variant |
| Encoding errors on Windows | Ensure Python 3.11+ with UTF-8 mode: `$env:PYTHONUTF8=1` |
| Database locked | Only one process can use SQLite at a time; stop other instances |

## Future

- Docker images with pre-configured ComfyUI
- Kubernetes deployment for horizontal scaling
- Cloud deployment templates (AWS, GCP, Azure)
- Managed hosting option
- Automatic model download and setup wizard
*（内容由AI生成，仅供参考）*
