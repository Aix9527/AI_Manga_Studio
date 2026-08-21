#!/usr/bin/env python3
"""V7 Launcher — one command to start the full stack (backend + frontend)."""

from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path


def main():
    print("=" * 50)
    print("AI Manga Studio v0.7 — 长篇小说 → CG AI 视频")
    print("=" * 50)

    root_dir = Path(__file__).parent

    # Check if frontend is built
    frontend_dist = root_dir / "frontend" / "dist"
    frontend_built = frontend_dist.exists() and (frontend_dist / "index.html").exists()

    print("\n[1/2] Starting backend (FastAPI + Orchestrator)...")
    backend_proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "backend.main:app",
         "--host", "0.0.0.0", "--port", "8000"],
        cwd=str(root_dir),
    )

    time.sleep(2)
    print("  Backend API: http://localhost:8000")
    print("  API Docs:    http://localhost:8000/docs")

    if frontend_built:
        print("  Frontend:    http://localhost:8000 (static files served)")
    else:
        print("\n[2/2] Starting frontend dev server...")
        frontend_dir = root_dir / "frontend"
        if frontend_dir.exists():
            frontend_proc = subprocess.Popen(
                ["npm", "run", "dev"],
                cwd=str(frontend_dir),
                shell=True,
            )
            print("  Frontend: http://localhost:5173")
        else:
            print("  [SKIP] Frontend directory not found")

    print("\n按 Ctrl+C 停止所有服务.\n")

    try:
        backend_proc.wait()
    except KeyboardInterrupt:
        print("\n正在关闭...")
        backend_proc.terminate()
        backend_proc.wait()
        if not frontend_built:
            try:
                frontend_proc.terminate()
                frontend_proc.wait()
            except Exception:
                pass


if __name__ == "__main__":
    main()