#!/usr/bin/env python3
"""
AI Manga Studio Pro V1.0 — Environment Setup Script

Installs all Python dependencies, checks system requirements,
clones ComfyUI if needed, and creates project directory structure.

Usage:
    python setup.py                  # Full setup
    python setup.py --skip-comfyui   # Skip ComfyUI clone
    python setup.py --skip-frontend  # Skip frontend npm install
    python setup.py --check-only     # Check only, no install
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent

# Required directories
REQUIRED_DIRS = [
    "launcher",
    "backend",
    "backend/routes",
    "frontend",
    "comfyui",
    "workflow",
    "models",
    "models/checkpoints",
    "models/loras",
    "models/vae",
    "models/controlnet",
    "models/upscale_models",
    "models/animatediff_models",
    "database",
    "project",
    "cache",
    "output",
    "plugin",
    "logs",
    "config",
]

# Required Python packages
REQUIRED_PACKAGES = [
    "fastapi>=0.110.0",
    "uvicorn[standard]>=0.29.0",
    "pydantic>=2.6.0",
    "pydantic-settings>=2.1.0",
    "sqlalchemy>=2.0.0",
    "aiosqlite>=0.19.0",
    "python-multipart>=0.0.9",
    "requests>=2.31.0",
    "websockets>=12.0",
    "aiofiles>=23.2.0",
    "loguru>=0.7.0",
    "pyyaml>=6.0",
    "rich>=13.0.0",
    "typer>=0.9.0",
    "httpx>=0.26.0",
    "psutil>=5.9.0",
    "numpy>=1.26.0",
    "Pillow>=10.0.0",
    "opencv-python>=4.9.0",
    "watchfiles>=0.21.0",
    "python-dotenv>=1.0.0",
    "orjson>=3.9.0",
    "redis>=5.0.0",
    "celery>=5.3.0",
]


def print_header(text: str) -> None:
    """Print a section header."""
    print(f"\n{'='*60}")
    print(f"  {text}")
    print(f"{'='*60}")


def check_python() -> bool:
    """Check Python version >= 3.10."""
    v = sys.version_info
    ok = v.major == 3 and v.minor >= 10
    status = "OK" if ok else "FAIL"
    print(f"  Python {v.major}.{v.minor}.{v.micro}  [{status}]")
    if not ok:
        print("  ERROR: Python 3.10+ is required.")
    return ok


def check_git() -> bool:
    """Check if git is available."""
    try:
        subprocess.run(["git", "--version"], capture_output=True, check=True)
        print("  git          [OK]")
        return True
    except (FileNotFoundError, subprocess.CalledProcessError):
        print("  git          [MISSING]")
        return False


def check_nvidia() -> bool:
    """Check NVIDIA GPU and CUDA."""
    try:
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode == 0:
            gpu_name = result.stdout.strip()
            print(f"  GPU          [OK] {gpu_name}")
            return True
    except FileNotFoundError:
        pass
    print("  GPU          [WARN] NVIDIA GPU not detected (some features limited)")
    return False


def create_directory_structure() -> None:
    """Create all required project directories."""
    print_header("Creating directory structure")
    for d in REQUIRED_DIRS:
        path = PROJECT_ROOT / d
        path.mkdir(parents=True, exist_ok=True)
        print(f"  [OK] {d}")

    # Create package __init__.py files
    for pkg_dir in ["backend", "backend/routes"]:
        init_file = PROJECT_ROOT / pkg_dir / "__init__.py"
        if not init_file.exists():
            init_file.touch()
            print(f"  [OK] {pkg_dir}/__init__.py")


def install_python_deps(pip_args: str = "") -> bool:
    """Install Python dependencies from requirements.txt.

    Args:
        pip_args: Extra pip arguments.

    Returns:
        True if successful.
    """
    print_header("Installing Python dependencies")

    req_path = PROJECT_ROOT / "requirements.txt"
    if not req_path.exists():
        print("  [FAIL] requirements.txt not found")
        return False

    cmd = [sys.executable, "-m", "pip", "install", "-r", str(req_path)]
    if pip_args:
        cmd.extend(pip_args.split())

    try:
        subprocess.run(cmd, check=True, cwd=str(PROJECT_ROOT))
        print("  [OK] Dependencies installed")
        return True
    except subprocess.CalledProcessError as e:
        print(f"  [FAIL] pip install failed: {e}")
        return False


def clone_comfyui(comfyui_dir: str = "") -> bool:
    """Clone ComfyUI if not present.

    Args:
        comfyui_dir: Target directory.

    Returns:
        True if ComfyUI is available.
    """
    print_header("Setting up ComfyUI")

    target = Path(comfyui_dir) if comfyui_dir else PROJECT_ROOT / "comfyui"

    if (target / "main.py").exists():
        print(f"  [OK] ComfyUI already present at {target}")
        return True

    if not check_git():
        print("  [SKIP] git not available — please install ComfyUI manually")
        print(f"         git clone https://github.com/comfyanonymous/ComfyUI.git {target}")
        return False

    print(f"  Cloning ComfyUI into {target}...")
    try:
        subprocess.run(
            ["git", "clone", "https://github.com/comfyanonymous/ComfyUI.git", str(target)],
            check=True,
        )
        print("  [OK] ComfyUI cloned")

        # Install ComfyUI dependencies
        comfyui_req = target / "requirements.txt"
        if comfyui_req.exists():
            subprocess.run(
                [sys.executable, "-m", "pip", "install", "-r", str(comfyui_req)],
                check=True,
            )
            print("  [OK] ComfyUI dependencies installed")

        return True
    except subprocess.CalledProcessError as e:
        print(f"  [FAIL] Clone failed: {e}")
        return False


def setup_frontend() -> bool:
    """Install frontend npm dependencies.

    Returns:
        True if successful.
    """
    print_header("Setting up Frontend")

    fe_dir = PROJECT_ROOT / "frontend"
    package_json = fe_dir / "package.json"

    if not package_json.exists():
        print("  [SKIP] package.json not found")
        return False

    try:
        subprocess.run(["node", "--version"], capture_output=True, check=True)
    except (FileNotFoundError, subprocess.CalledProcessError):
        print("  [SKIP] Node.js not available")
        return False

    try:
        subprocess.run(["npm", "install"], cwd=str(fe_dir), check=True)
        print("  [OK] Frontend dependencies installed")
        return True
    except subprocess.CalledProcessError as e:
        print(f"  [FAIL] npm install failed: {e}")
        return False


def main() -> None:
    """Main setup entry point."""
    parser = argparse.ArgumentParser(
        description="AI Manga Studio Pro V1.0 Setup"
    )
    parser.add_argument("--skip-comfyui", action="store_true", help="Skip ComfyUI clone")
    parser.add_argument("--skip-frontend", action="store_true", help="Skip frontend setup")
    parser.add_argument("--check-only", action="store_true", help="Only check, don't install")
    parser.add_argument("--pip-args", default="", help="Extra pip install arguments")
    parser.add_argument("--comfyui-dir", default="", help="Custom ComfyUI directory")
    args = parser.parse_args()

    print("=" * 60)
    print("  AI Manga Studio Pro V1.0 — Setup")
    print("=" * 60)

    # System check
    print_header("System Requirements")
    ok = check_python()
    check_nvidia()
    if not ok:
        sys.exit(1)

    if args.check_only:
        print("\n  [INFO] Check complete. Run without --check-only to install.")
        return

    # Create directories
    create_directory_structure()

    # Install Python deps
    install_python_deps(args.pip_args)

    # ComfyUI
    if not args.skip_comfyui:
        clone_comfyui(args.comfyui_dir)

    # Frontend
    if not args.skip_frontend:
        setup_frontend()

    print_header("Setup Complete")
    print(f"  Run:  python {PROJECT_ROOT / 'launcher' / 'start.py'}")
    print(f"  Docs: http://127.0.0.1:8800/docs")


if __name__ == "__main__":
    main()
