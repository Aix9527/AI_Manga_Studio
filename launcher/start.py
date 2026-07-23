#!/usr/bin/env python3
"""
AI Manga Studio Pro V1.0 — One-Click Launcher

Usage:
    python start.py                     # Start all services
    python start.py --backend-only      # Start only backend
    python start.py --frontend-only     # Start only frontend
    python start.py --check             # Check dependencies
    python start.py --comfyui           # Start with ComfyUI
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
from pathlib import Path

# Ensure project root is in path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


def print_banner() -> None:
    """Display the ASCII banner."""
    banner = r"""
    ╔══════════════════════════════════════════════╗
    ║          AI MANGA STUDIO PRO V1.0            ║
    ║      Local Manga Generation System           ║
    ║         一键生成漫剧 · 全自动                 ║
    ╚══════════════════════════════════════════════╝
    """
    print(banner)


def check_python() -> bool:
    """Check Python version."""
    version = sys.version_info
    if version.major < 3 or (version.major == 3 and version.minor < 10):
        print(f"[FAIL] Python 3.10+ required (current: {version.major}.{version.minor})")
        return False
    print(f"[OK] Python {version.major}.{version.minor}.{version.micro}")
    return True


def check_comfyui(comfyui_dir: str) -> bool:
    """Check if ComfyUI is installed."""
    path = Path(comfyui_dir) if comfyui_dir else PROJECT_ROOT / "comfyui"
    if path.exists() and (path / "main.py").exists():
        print(f"[OK] ComfyUI found at {path}")
        return True
    print(f"[WARN] ComfyUI not found at {path}")
    print("       Install with: git clone https://github.com/comfyanonymous/ComfyUI.git")
    return False


def check_node() -> bool:
    """Check Node.js for frontend."""
    try:
        result = subprocess.run(["node", "--version"], capture_output=True, text=True)
        print(f"[OK] Node.js {result.stdout.strip()}")
        return True
    except FileNotFoundError:
        print("[WARN] Node.js not found (needed for frontend)")
        return False


def start_backend(host: str = "127.0.0.1", port: int = 8800) -> subprocess.Popen:
    """Start FastAPI backend server.

    Args:
        host: Bind address.
        port: Bind port.

    Returns:
        Subprocess handle.
    """
    backend_dir = PROJECT_ROOT / "backend"
    cmd = [
        sys.executable, "-m", "uvicorn",
        "backend.main:app",
        "--host", host,
        "--port", str(port),
        "--reload",
        "--log-level", "info",
    ]
    print(f"\n[START] Backend → http://{host}:{port}")
    print(f"        API docs → http://{host}:{port}/docs")

    return subprocess.Popen(cmd, cwd=str(PROJECT_ROOT))


def start_frontend(frontend_dir: str = "") -> subprocess.Popen:
    """Start React frontend dev server.

    Args:
        frontend_dir: Frontend project directory.

    Returns:
        Subprocess handle.
    """
    fe_dir = Path(frontend_dir) if frontend_dir else PROJECT_ROOT / "frontend"

    if not (fe_dir / "node_modules").exists():
        print("[INSTALL] Installing frontend dependencies...")
        subprocess.run(["npm", "install"], cwd=str(fe_dir), check=True, shell=True)

    print(f"\n[START] Frontend → http://localhost:3000")
    return subprocess.Popen(["npm", "start"], cwd=str(fe_dir), shell=True)


def start_comfyui(comfyui_dir: str = "") -> subprocess.Popen:
    """Start ComfyUI server.

    Args:
        comfyui_dir: ComfyUI installation directory.

    Returns:
        Subprocess handle.
    """
    cui_dir = Path(comfyui_dir) if comfyui_dir else PROJECT_ROOT / "comfyui"
    print(f"\n[START] ComfyUI → http://127.0.0.1:8188")
    return subprocess.Popen(
        [sys.executable, "main.py", "--listen", "127.0.0.1", "--port", "8188"],
        cwd=str(cui_dir),
    )


def main() -> None:
    """Main launcher entry point."""
    parser = argparse.ArgumentParser(
        description="AI Manga Studio Pro V1.0 Launcher"
    )
    parser.add_argument(
        "--backend-only",
        action="store_true",
        help="Start only backend server",
    )
    parser.add_argument(
        "--frontend-only",
        action="store_true",
        help="Start only frontend",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Check dependencies and exit",
    )
    parser.add_argument(
        "--comfyui",
        action="store_true",
        help="Also start ComfyUI server",
    )
    parser.add_argument(
        "--comfyui-dir",
        default="",
        help="Custom ComfyUI installation path",
    )
    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="Backend bind address",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8800,
        help="Backend bind port",
    )
    args = parser.parse_args()

    print_banner()

    # Environment check
    print("\n--- System Check ---")
    all_ok = check_python()
    if not all_ok:
        sys.exit(1)

    if args.check:
        check_node()
        check_comfyui(args.comfyui_dir)
        print("\n[INFO] Dependency check complete.")
        return

    processes: list = []

    try:
        # Start ComfyUI first (if requested)
        if args.comfyui:
            if check_comfyui(args.comfyui_dir):
                proc = start_comfyui(args.comfyui_dir)
                processes.append(("ComfyUI", proc))
                time.sleep(3)  # Wait for ComfyUI to initialize

        if args.backend_only:
            proc = start_backend(args.host, args.port)
            processes.append(("Backend", proc))
        elif args.frontend_only:
            proc = start_frontend()
            processes.append(("Frontend", proc))
        else:
            # Start both
            proc = start_backend(args.host, args.port)
            processes.append(("Backend", proc))
            time.sleep(2)
            proc = start_frontend()
            processes.append(("Frontend", proc))

        print("\n--- All Services Running ---")
        print("Press Ctrl+C to stop all services.\n")

        # Keep alive
        while True:
            for name, proc in processes:
                if proc.poll() is not None:
                    print(f"[STOP] {name} exited with code {proc.returncode}")
                    return
            time.sleep(1)

    except KeyboardInterrupt:
        print("\n\n[STOP] Shutting down...")
    finally:
        for name, proc in processes:
            print(f"[STOP] Terminating {name}...")
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
        print("[DONE] All services stopped.")


if __name__ == "__main__":
    main()
