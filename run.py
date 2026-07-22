#!/usr/bin/env python3
"""
AI Manga Studio - One-Click Launcher & Pipeline Runner
======================================================
THE single entry point. Everything starts here.

Usage:
    python run.py                              Interactive menu
    python run.py --novel novel.txt            Pipeline: novel -> video
    python run.py --web                        Start web services
    python run.py --all novel.txt              Web + pipeline
    python run.py --check                      Environment check
    python run.py --comfyui                    Start ComfyUI too

Quick start:
    1. Drop your .txt novel into novels/ folder
    2. Run: python run.py --novel novels/your_novel.txt
    3. Or: double-click 一键启动.bat
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.resolve()
sys.path.insert(0, str(PROJECT_ROOT))

# ============================================================
# Constants
# ============================================================
BACKEND_HOST = "127.0.0.1"
BACKEND_PORT = 8800
COMFYUI_PORT = 8188
FRONTEND_PORT = 3000
NOVELS_DIR = PROJECT_ROOT / "novels"
OUTPUT_DIR = PROJECT_ROOT / "output"


def print_banner():
    print("""
    ╔══════════════════════════════════════════════════════╗
    ║        AI Manga Studio Pro - One-Click Launcher       ║
    ║         Novel -> AI Manga/Video, Fully Automated      ║
    ╚══════════════════════════════════════════════════════╝
    """)


def find_python() -> str:
    """Find Python 3.10+ executable."""
    for cmd in ["python3", "python"]:
        try:
            r = subprocess.run([cmd, "--version"], capture_output=True, text=True, timeout=5)
            version = r.stdout.strip() or r.stderr.strip()
            if "Python 3" in version:
                return cmd
        except Exception:
            continue
    return "python"


def check_environment(verbose=True):
    """Check all dependencies and return status."""
    issues = []
    ok = []

    # Python
    py = find_python()
    v = sys.version_info
    if v.major >= 3 and v.minor >= 10:
        ok.append(f"Python {v.major}.{v.minor}.{v.micro}")
    else:
        issues.append(f"Python 3.10+ required (found {v.major}.{v.minor})")

    # Node.js
    try:
        r = subprocess.run(["node", "--version"], capture_output=True, text=True)
        ok.append(f"Node.js {r.stdout.strip()}")
    except FileNotFoundError:
        issues.append("Node.js not found (needed for frontend)")

    # npm
    try:
        r = subprocess.run(["npm", "--version"], capture_output=True, text=True)
        ok.append(f"npm {r.stdout.strip()}")
    except FileNotFoundError:
        issues.append("npm not found")

    # Git
    try:
        r = subprocess.run(["git", "--version"], capture_output=True, text=True)
        ok.append(f"Git found")
    except FileNotFoundError:
        ok.append("Git not needed")

    # ComfyUI
    comfyui_path = PROJECT_ROOT / "comfyui"
    if (comfyui_path / "main.py").exists():
        ok.append(f"ComfyUI installed")
    else:
        issues.append("ComfyUI not found (image/video generation needs it)")

    # Backend
    backend_path = PROJECT_ROOT / "backend" / "main.py"
    if backend_path.exists():
        ok.append("Backend code found")
    else:
        issues.append("Backend code not found")

    if verbose:
        print("\n--- Environment Check ---")
        for item in ok:
            print(f"  [OK] {item}")
        for item in issues:
            print(f"  [WARN] {item}")

        if not issues:
            print("\n  All checks passed!")
        else:
            print(f"\n  {len(issues)} issue(s) found. Some features may not work.")

    return len(issues) == 0, issues


def is_port_in_use(port: int) -> bool:
    """Check if a port is already in use."""
    import socket
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex((BACKEND_HOST, port)) == 0


def start_backend() -> subprocess.Popen | None:
    """Start FastAPI backend server."""
    if is_port_in_use(BACKEND_PORT):
        print(f"  Backend already running on :{BACKEND_PORT}")
        return None

    print(f"\n  [START] Backend -> http://{BACKEND_HOST}:{BACKEND_PORT}")
    print(f"          API docs -> http://{BACKEND_HOST}:{BACKEND_PORT}/docs")

    env = os.environ.copy()
    env["PYTHONPATH"] = str(PROJECT_ROOT)

    return subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "backend.main:app",
         "--host", BACKEND_HOST, "--port", str(BACKEND_PORT),
         "--log-level", "info"],
        cwd=str(PROJECT_ROOT),
        env=env,
        creationflags=subprocess.CREATE_NEW_CONSOLE if sys.platform == "win32" else 0,
    )


def start_frontend() -> subprocess.Popen | None:
    """Start React frontend dev server."""
    if is_port_in_use(FRONTEND_PORT):
        print(f"  Frontend already running on :{FRONTEND_PORT}")
        return None

    fe_dir = PROJECT_ROOT / "frontend"
    if not (fe_dir / "node_modules").exists():
        print("  [INSTALL] Installing frontend dependencies...")
        subprocess.run(["npm", "install"], cwd=str(fe_dir), check=False)

    print(f"\n  [START] Frontend -> http://localhost:{FRONTEND_PORT}")

    return subprocess.Popen(
        ["npm", "start"],
        cwd=str(fe_dir),
        creationflags=subprocess.CREATE_NEW_CONSOLE if sys.platform == "win32" else 0,
        shell=True,
    )


def start_comfyui() -> subprocess.Popen | None:
    """Start ComfyUI server."""
    if is_port_in_use(COMFYUI_PORT):
        print(f"  ComfyUI already running on :{COMFYUI_PORT}")
        return None

    comfyui_dir = PROJECT_ROOT / "comfyui"
    if not (comfyui_dir / "main.py").exists():
        print("  [SKIP] ComfyUI not installed (image/video gen won't work)")
        return None

    print(f"\n  [START] ComfyUI -> http://{BACKEND_HOST}:{COMFYUI_PORT}")

    return subprocess.Popen(
        [sys.executable, "main.py", "--listen", BACKEND_HOST, "--port", str(COMFYUI_PORT)],
        cwd=str(comfyui_dir),
        creationflags=subprocess.CREATE_NEW_CONSOLE if sys.platform == "win32" else 0,
    )


def wait_for_service(url: str, max_wait: int = 60, name: str = "Service") -> bool:
    """Wait for a service to become available."""
    import urllib.request

    print(f"  Waiting for {name}...", end="", flush=True)
    for i in range(max_wait):
        try:
            urllib.request.urlopen(url, timeout=2)
            print(f" ready! ({i}s)")
            return True
        except Exception:
            time.sleep(1)
            if i % 5 == 0:
                print(".", end="", flush=True)
    print(f" timeout ({max_wait}s)")
    return False


def api_json_request(
    method: str,
    path: str,
    payload: dict | None = None,
    *,
    base_url: str = f'http://{BACKEND_HOST}:{BACKEND_PORT}',
    opener=None,
) -> dict | None:
    opener = opener or urllib.request.urlopen
    data = None if payload is None else json.dumps(payload).encode('utf-8')
    request = urllib.request.Request(
        f'{base_url}{path}',
        data=data,
        method=method,
        headers={'Content-Type': 'application/json'},
    )
    try:
        with opener(request, timeout=10) as response:
            body = response.read()
    except (urllib.error.URLError, TimeoutError) as error:
        raise RuntimeError(f'本地服务不可用：{error}') from error
    return json.loads(body) if body else None


def submit_job(
    novel_path: str | Path,
    style: str | None = None,
    *,
    base_url: str = f'http://{BACKEND_HOST}:{BACKEND_PORT}',
    opener=None,
) -> dict:
    novel = Path(novel_path).resolve()
    if not novel.is_file():
        raise FileNotFoundError(f'输入文件不存在：{novel}')
    return api_json_request(
        'POST',
        '/api/jobs',
        {
            'project_id': novel.stem,
            'input_path': str(novel),
            'input_type': 'novel',
            'mode': 'automatic',
            'shot_duration': 5,
            'width': 1080,
            'height': 1920,
            'fps': 24,
            'options': {'style': style or 'realistic'},
            'idempotency_key': f'cli-{uuid.uuid4()}',
        },
        base_url=base_url,
        opener=opener,
    )


def monitor_job(job_id: str, poll_seconds: float = 1.0) -> int:
    last = None
    while True:
        job = api_json_request('GET', f'/api/jobs/{job_id}')
        snapshot = (job['status'], job['progress'], job['message'])
        if snapshot != last:
            print(
                '  [{}] {:.0%} {}'.format(
                    job['status'], job['progress'], job['message']
                )
            )
            last = snapshot
        if job['status'] == 'completed':
            return 0
        if job['status'] in {'failed', 'cancelled'}:
            return 1
        time.sleep(poll_seconds)


def run_pipeline(
    novel_path: str,
    style: str | None = None,
    config: str | None = None,
):
    if config:
        raise ValueError('The canonical durable API does not accept legacy config files')
    if not is_port_in_use(BACKEND_PORT):
        start_backend()
        if not wait_for_service(
            f'http://{BACKEND_HOST}:{BACKEND_PORT}/health',
            max_wait=30,
            name='Backend',
        ):
            raise RuntimeError('本地后端启动失败')
    job = submit_job(novel_path, style=style)
    print('  Durable job created: {}'.format(job['id']))
    return monitor_job(job['id'])


def interactive_menu():
    """Show interactive menu for users."""
    print_banner()
    check_environment()

    print(f"""
╔═══════════════════════════════════════════════╗
║           What would you like to do?           ║
╠═══════════════════════════════════════════════╣
║  [1] Pipeline: Novel -> AI Manga Video        ║
║  [2] Start Web Services (backend + frontend)  ║
║  [3] Start Everything (web + pipeline)        ║
║  [4] Start ComfyUI                             ║
║  [5] Environment Check                         ║
║  [q] Quit                                      ║
╚═══════════════════════════════════════════════╝
""")

    choice = input("  Choice [1-5/q]: ").strip().lower()

    if choice == "q":
        print("  Goodbye!")
        return

    if choice == "1":
        # List available novels
        novels = []
        if NOVELS_DIR.exists():
            novels.extend(NOVELS_DIR.glob("*.txt"))
        novels.extend(PROJECT_ROOT.glob("novel*.txt"))

        if not novels:
            path = input("  Novel file path: ").strip()
        else:
            print("\n  Available novels:")
            for i, n in enumerate(novels, 1):
                print(f"    [{i}] {n.name}")
            sel = input(f"  Select [1-{len(novels)}] or enter path: ").strip()
            if sel.isdigit() and 1 <= int(sel) <= len(novels):
                path = str(novels[int(sel) - 1])
            elif sel:
                path = sel
            else:
                print("  No novel selected.")
                return

        run_pipeline(path)

    elif choice == "2":
        start_web_services()

    elif choice == "3":
        novels = []
        if NOVELS_DIR.exists():
            novels.extend(NOVELS_DIR.glob("*.txt"))
        novels.extend(PROJECT_ROOT.glob("novel*.txt"))

        if novels:
            print("\n  Available novels:")
            for i, n in enumerate(novels, 1):
                print(f"    [{i}] {n.name}")
            sel = input(f"  Select [1-{len(novels)}] or enter path: ").strip()
            if sel.isdigit() and 1 <= int(sel) <= len(novels):
                novel_path = str(novels[int(sel) - 1])
            else:
                novel_path = sel
        else:
            novel_path = input("  Novel file path: ").strip()

        if novel_path:
            start_web_services()
            time.sleep(5)
            run_pipeline(novel_path)

    elif choice == "4":
        start_comfyui()

    elif choice == "5":
        check_environment(verbose=True)
    else:
        print("  Invalid choice.")


def start_web_services(with_comfyui=False):
    """Start backend + frontend (+ ComfyUI)."""
    print(f"\n{'='*60}")
    print("  Starting Services...")
    print(f"{'='*60}")

    # Start in order: ComfyUI -> Backend -> Frontend
    if with_comfyui:
        start_comfyui()
        time.sleep(2)

    backend_proc = start_backend()
    time.sleep(2)

    frontend_proc = start_frontend()

    # Wait & verify
    print()
    wait_for_service(f"http://{BACKEND_HOST}:{BACKEND_PORT}/health",
                     max_wait=30, name="Backend")
    wait_for_service(f"http://localhost:{FRONTEND_PORT}",
                     max_wait=30, name="Frontend")

    print(f"""
{'='*60}
  All Services Started!
  Frontend: http://localhost:{FRONTEND_PORT}
  Backend:  http://{BACKEND_HOST}:{BACKEND_PORT}
  API Docs: http://{BACKEND_HOST}:{BACKEND_PORT}/docs
{'='*60}
""")

    return backend_proc, frontend_proc


def main():
    parser = argparse.ArgumentParser(
        description="AI Manga Studio - One-Click Launcher & Pipeline",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python run.py                              Interactive menu
  python run.py --novel novels/my_novel.txt  Direct pipeline
  python run.py --web                        Start web services
  python run.py --all novels/my_novel.txt    Web + pipeline
  python run.py --comfyui                    Start ComfyUI only
        """
    )

    parser.add_argument("--novel", "-n", help="Path to novel .txt file")
    parser.add_argument("--web", "-w", action="store_true", help="Start web services (backend + frontend)")
    parser.add_argument("--all", "-a", help="Start everything: web + pipeline for given novel")
    parser.add_argument("--comfyui", action="store_true", help="Also start ComfyUI server")
    parser.add_argument("--check", "-c", action="store_true", help="Check environment and exit")
    parser.add_argument("--style", "-s", help="Art style (anime, realistic, manga, 3d)")
    parser.add_argument("--config", help="Path to config JSON file")

    args = parser.parse_args()

    print_banner()

    # --check mode
    if args.check:
        check_environment()
        return

    # --comfyui mode
    if args.comfyui and not args.web and not args.novel and not args.all:
        start_comfyui()
        print("\n  ComfyUI started. Press Ctrl+C to stop.")
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            print("\n  Shutting down...")
        return

    # --web mode: start services and stay alive
    if args.web and not args.all:
        start_web_services(with_comfyui=args.comfyui)
        print("  Press Ctrl+C to stop all services.")
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            print("\n  Shutting down...")
        return

    # --all mode: start web + run pipeline
    if args.all:
        start_web_services(with_comfyui=args.comfyui)
        time.sleep(5)
        run_pipeline(args.all, style=args.style, config=args.config)
        print("\n  Pipeline complete! Web services still running.")
        print("  Press Ctrl+C to stop.")
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            print("\n  Shutting down...")
        return

    # --novel mode: direct pipeline
    if args.novel:
        if args.comfyui:
            start_comfyui()
            time.sleep(3)
        run_pipeline(args.novel, style=args.style, config=args.config)
        return

    # Default: interactive menu
    interactive_menu()


if __name__ == "__main__":
    main()
