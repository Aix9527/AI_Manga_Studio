"""
V3.5 one_click.py — 18-stage pipeline entry point.

CLI usage:
    python -m backend.one_click run novel.txt
    python -m backend.one_click run novel.txt --no-storygraph
    python -m backend.one_click run novel.txt --quality-threshold 0.7
    python -m backend.one_click run novel.txt --gpu-layout custom.json
    python -m backend.one_click run novel.txt --motion-style cinematic
    python -m backend.one_click run novel.txt --dashboard-port 9090
    python -m backend.one_click run novel.txt --v35
"""

from __future__ import annotations

import argparse
import logging
import sys
import threading
import time
from pathlib import Path
from typing import Dict, List, Optional

# ── V3.5 Engine imports ────────────────────────────────────
try:
    from backend.storyboard_engine import StoryboardEngine
    from backend.camera_planner import CameraPlanner
    from backend.motion_planner import MotionPlanner
    from backend.character_reasoner import CharacterReasoner
    from backend.scene_reasoner import SceneReasoner
    from backend.image_prompt_builder import ImagePromptBuilder
    from backend.video_prompt_builder import VideoPromptBuilder
    from backend.dialogue_optimizer import DialogueOptimizer
    HAS_V35_ENGINES = True
except ImportError as e:
    HAS_V35_ENGINES = False
    _v35_import_error = str(e)

logger = logging.getLogger(__name__)

# Rich progress bar (optional — graceful fallback)
try:
    from rich.console import Console
    from rich.progress import (
        BarColumn,
        Progress,
        TextColumn,
        TimeElapsedColumn,
    )
    HAS_RICH = True
except ImportError:
    HAS_RICH = False


# ── 18-Stage labels ───────────────────────────────────────────

STAGE_LABELS = [
    "Novel Parsing",
    "AI Director",
    "StoryGraph",
    "Character DNA",
    "Scene DNA",
    "Style DNA",
    "Prompt Engine",
    "Model Router",
    "Control Layer",
    "Image Pipeline",
    "Quality AI",
    "Motion Planner",
    "Video Pipeline",
    "LipSync",
    "Timeline",
    "Cache Checkpoints",
    "Database Checkpoints",
    "Final Render",
]


# ── CLI ───────────────────────────────────────────────────────


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ai-manga",
        description="AI Manga Studio V3.0 — 18-Layer Pipeline",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # run command
    run_p = sub.add_parser("run", help="Run the full pipeline")
    run_p.add_argument("novel", help="Path to novel text file")
    run_p.add_argument("--output-dir", default="", help="Output directory")
    run_p.add_argument("--project-name", default="", help="Project name")

    # Pipeline switches
    run_p.add_argument("--no-storygraph", action="store_true",
                       help="Disable StoryGraph (fallback to V2.0 mode)")
    run_p.add_argument("--story-graph-json", default="",
                       help="Export StoryGraph to JSON file")

    # Quality
    run_p.add_argument("--quality-threshold", type=float, default=0.6,
                       help="Quality grade threshold (0.0~1.0)")

    # Skip flags
    run_p.add_argument("--skip-pulid", action="store_true",
                       help="Skip PuLID face consistency")
    run_p.add_argument("--skip-supir", action="store_true",
                       help="Skip SUPIR 4K upscale")
    run_p.add_argument("--skip-codeformer", action="store_true",
                       help="Skip CodeFormer face restore")
    run_p.add_argument("--skip-lip-sync", action="store_true",
                       help="Skip LipSync (TTS + MuseTalk)")
    run_p.add_argument("--skip-voice-clone", action="store_true",
                       help="Skip voice cloning (use default voice)")
    run_p.add_argument("--skip-rife", action="store_true",
                       help="Skip RIFE frame interpolation")
    run_p.add_argument("--skip-optical-flow", action="store_true",
                       help="Skip optical flow consistency check")

    # GPU
    run_p.add_argument("--gpu-layout", default="",
                       help="GPU layout JSON file (maps GPU ID → model list)")

    # Motion
    run_p.add_argument("--motion-style", default="cinematic",
                       choices=["cinematic", "anime", "realistic", "action"],
                       help="Global motion style")

    # Dashboard
    run_p.add_argument("--dashboard-port", type=int, default=8080,
                       help="Dashboard HTTP port (0 to disable)")

    # V3.5
    run_p.add_argument("--v35", action="store_true",
                       help="Enable V3.5 engine suite")

    # Debug
    run_p.add_argument("--debug", action="store_true",
                       help="Enable debug mode — saves full reproducibility artifacts "
                            "to output/debug/chXX_scXX_shXX/ for every shot "
                            "(equiv. AI_MANGA_DEBUG=1)")

    return parser


# ── V3.5 Engine Initialization ────────────────────────────────────


def init_v35_engines(args) -> Optional[Dict[str, object]]:
    """Lazy-initialize V3.5 engine suite if --v35 flag is set."""
    if not getattr(args, "v35", False):
        return None

    if not HAS_V35_ENGINES:
        logger.warning(
            f"V3.5 engines requested but import failed: {_v35_import_error}. "
            "Falling back to V3.0 mode."
        )
        return None

    logger.info("Initializing V3.5 engine suite...")
    engines = {
        "storyboard": StoryboardEngine(),
        "camera": CameraPlanner(),
        "motion": MotionPlanner(),
        "character_reasoner": CharacterReasoner(),
        "scene_reasoner": SceneReasoner(),
        "image_builder": ImagePromptBuilder(),
        "video_builder": VideoPromptBuilder(),
        "dialogue": DialogueOptimizer(),
    }
    logger.info(f"V3.5 engines ready: {', '.join(engines.keys())}")
    return engines


def run_pipeline(args: argparse.Namespace) -> int:
    """Execute the 18-stage pipeline."""
    
    # ── Debug mode: set env var so all downstream components pick it up ──
    if getattr(args, "debug", False):
        os.environ["AI_MANGA_DEBUG"] = "1"
        logger.info("Debug mode enabled — artifacts saved to output/debug/")
    
    project_dir = args.output_dir or ""
    project_name = args.project_name or Path(args.novel).stem

    if HAS_RICH:
        console = Console()
        console.print(f"[bold cyan]AI Manga Studio V3.0[/]")
        console.print(f"Project: [green]{project_name}[/]")
        console.print(f"Novel: [dim]{args.novel}[/]")
        console.print(f"StoryGraph: [{'green' if not args.no_storygraph else 'yellow'}]{'enabled' if not args.no_storygraph else 'disabled'}[/]")
        console.print()

    # Pre-parse novel to get total shot count for progress bars
    novel_path = Path(args.novel)
    if novel_path.is_file():
        novel_content = novel_path.read_text(encoding="utf-8")
    else:
        novel_content = args.novel

    from backend.ai_director import AIDirector
    try:
        temp_director = AIDirector()
        parsed = temp_director.parse_novel(novel_content)
        total_shots = sum(len(getattr(ch, "shots", [])) for ch in parsed.chapters)
        total_chapters = len(parsed.chapters)
    except Exception:
        total_shots = 0
        total_chapters = 0

    # Load GPU layout
    gpu_layout = None
    if args.gpu_layout:
        import json
        with open(args.gpu_layout) as f:
            raw = json.load(f)
            gpu_layout = {int(k): v for k, v in raw.items()}

    # Create scheduler
    from backend.scheduler import Scheduler
    sched = Scheduler(
        project_dir=project_dir,
        use_storygraph=not args.no_storygraph,
        quality_threshold=args.quality_threshold,
        gpu_layout=gpu_layout,
        skip_pulid=args.skip_pulid,
        skip_supir=args.skip_supir,
        skip_codeformer=args.skip_codeformer,
        skip_lip_sync=args.skip_lip_sync,
        skip_voice_clone=args.skip_voice_clone,
        skip_rife=args.skip_rife,
        skip_optical_flow=args.skip_optical_flow,
        motion_style=args.motion_style,
        dashboard_port=args.dashboard_port,
    )

    # ── Dashboard startup ─────────────────────────────────
    dashboard = None
    dashboard_thread = None
    if args.dashboard_port > 0:
        try:
            from backend.dashboard import DashboardApp
            dashboard = DashboardApp()
            dashboard.set_project(
                name=args.project_name or novel_path.stem,
                shots=total_shots,
                status="running",
                progress=0,
            )
            dashboard_thread = threading.Thread(
                target=dashboard.run,
                kwargs={"host": "127.0.0.1", "port": args.dashboard_port, "debug": False},
                daemon=True,
            )
            dashboard_thread.start()
        except Exception as e:
            print(f"Dashboard failed to start: {e}")

    # ── Wire dashboard progress callbacks ───────────────────
    if dashboard:
        shot_counter = [0]  # mutable closure
        def on_shot_complete(shot):
            shot_counter[0] += 1
            dashboard.set_project(
                name=dashboard._project_name,
                shots=total_shots,
                status="running",
                progress=int(shot_counter[0] / total_shots * 100) if total_shots else 0,
            )
        sched.register_callbacks(on_shot_complete=on_shot_complete)

    # Run with dual progress bars
    if HAS_RICH:
        with Progress(
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            TextColumn("· {task.completed}/{task.total}"),
            TimeElapsedColumn(),
            console=console,
        ) as progress:
            # Two progress bars: overall (all shots) + current stage
            overall_task = progress.add_task(
                f"[bold]Total[/] ({total_shots} shots)" if total_shots else "[bold]Total[/]",
                total=max(total_shots, 1),
            )
            stage_task = progress.add_task(
                "[dim]Initializing...[/]",
                total=1,
            )

            # Shared state for callbacks
            _state = {
                "overall_done": 0,
                "stage_done": 0,
                "stage_total": 1,
            }

            def on_stage_begin(stage_name: str, item_count: int):
                _state["stage_done"] = 0
                _state["stage_total"] = max(item_count, 1)
                progress.update(
                    stage_task,
                    description=f"[cyan]{stage_name}[/]",
                    completed=0,
                    total=_state["stage_total"],
                )

            def on_shot_complete(shot_record):
                _state["overall_done"] += 1
                _state["stage_done"] += 1
                progress.update(overall_task, completed=_state["overall_done"])
                progress.update(stage_task, completed=min(_state["stage_done"], _state["stage_total"]))

            sched.register_callbacks(
                on_shot_complete=on_shot_complete,
                on_stage_begin=on_stage_begin,
            )

            t0 = time.time()
            success = sched.run(args.novel)
            elapsed = time.time() - t0

            progress.update(
                overall_task,
                description="[green]Complete[/]" if success else "[red]Failed[/]",
                completed=_state["overall_done"],
            )
            progress.update(
                stage_task,
                description="[green]Done[/]" if success else "[red]Aborted[/]",
                completed=_state["stage_done"],
            )

            if success:
                console.print(f"\n[green]Pipeline completed in {elapsed:.1f}s[/]")
            else:
                console.print(f"\n[red]Pipeline failed after {elapsed:.1f}s[/]")

            # Print stage times
            if hasattr(sched, "_stage_times") and sched._stage_times:
                console.print("\n[bold]Stage Times:[/]")
                for name, dt in sched._stage_times.items():
                    color = "green" if dt < 60 else "yellow" if dt < 300 else "red"
                    console.print(f"  [{color}]{dt:>7.1f}s[/]  {name}")
    else:
        t0 = time.time()
        success = sched.run(args.novel)
        elapsed = time.time() - t0
        print(f"\nPipeline {'OK' if success else 'FAILED'} in {elapsed:.1f}s")

    return 0 if success else 1


def main():
    parser = build_parser()
    args = parser.parse_args()

    if args.command == "run":
        return run_pipeline(args)

    return 1


if __name__ == "__main__":
    sys.exit(main())
