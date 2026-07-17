"""
AI Manga Studio Pro V1.0 — CLI entry for Python-first pipeline.

Usage:
  python -m backend.orchestrator_cli generate <project_id> [--video]
  python -m backend.orchestrator_cli status <project_id>
  python -m backend.orchestrator_cli shot <shot_json_path>

Principle:
  ComfyUI = GPU worker only.
  Python  = prompt assembly, workflow building, state, retry, quality.
"""

import argparse
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from loguru import logger
from rich.console import Console
from rich.table import Table

from backend.orchestrator import Orchestrator, ShotResult
from backend.unified_shot import UnifiedShot, ShotBatch


console = Console()


def cmd_generate(args):
    """Run pipeline for a project."""
    orch = Orchestrator(max_retries=args.retries)

    console.print(f"\n[bold]Pipeline: {args.project_id}[/bold]")
    console.print("ComfyUI → GPU inference only. Python → everything else.\n")

    def on_shot(result: ShotResult):
        icon = "✓" if result.status.value == "success" else "✗"
        console.print(
            f"  {icon} Shot {result.shot_idx:03d} "
            f"[{result.attempts} attempts, {result.elapsed:.0f}s] "
            f"{result.error or ''}"
        )

    result = orch.run_project(
        project_id=args.project_id,
        generate_image=True,
        generate_video=args.video,
        on_shot=on_shot,
    )

    # Summary table
    table = Table(title=f"Results: {args.project_id}")
    table.add_column("Chapter", style="cyan")
    table.add_column("Total", style="white")
    table.add_column("Success", style="green")
    table.add_column("Failed", style="red")
    table.add_column("Time", style="yellow")

    for ch in result.chapters:
        table.add_row(
            str(ch.chapter),
            str(ch.total_shots),
            str(ch.success),
            str(ch.failed),
            f"{ch.elapsed:.0f}s",
        )

    table.add_row(
        "[bold]TOTAL[/bold]",
        str(result.total_shots),
        f"[bold green]{result.total_success}[/bold green]",
        f"[bold red]{result.total_failed}[/bold red]",
        f"{result.elapsed:.0f}s",
    )

    console.print(table)


def cmd_status(args):
    """Show project status by reading JSON files."""
    from backend.config import get_config
    cfg = get_config()
    base = cfg.project.output_path or cfg.project.root_path
    project_dir = os.path.join(base, args.project_id)

    if not os.path.isdir(project_dir):
        console.print(f"[red]Project not found: {project_dir}[/red]")
        return

    table = Table(title=f"Status: {args.project_id}")
    table.add_column("Shot", style="cyan")
    table.add_column("Status", style="white")
    table.add_column("Image", style="green")
    table.add_column("Video", style="blue")
    table.add_column("Errors", style="red")

    for ch_dir in sorted(os.listdir(project_dir)):
        if not ch_dir.startswith("ch"):
            continue
        shot_dir = os.path.join(project_dir, ch_dir, "shots")
        if not os.path.isdir(shot_dir):
            continue

        for sf in sorted(os.listdir(shot_dir)):
            if not sf.startswith("shot_") or not sf.endswith(".json"):
                continue
            shot_path = os.path.join(shot_dir, sf)
            try:
                shot = UnifiedShot.from_json_file(shot_path)
                table.add_row(
                    shot.shot_id or f"ch{shot.chapter:02d}_sh{shot.shot:03d}",
                    shot.status.value,
                    "✓" if shot.image_path else "-",
                    "✓" if shot.video_path else "-",
                    shot.error_message[:60] if shot.error_message else "-",
                )
            except Exception as e:
                table.add_row(sf, "ERROR", "-", "-", str(e)[:60])

    console.print(table)


def cmd_shot(args):
    """Process a single shot file."""
    shot = UnifiedShot.from_json_file(args.shot_path)
    orch = Orchestrator(max_retries=args.retries)

    console.print(f"\nProcessing: {shot.shot_id or args.shot_path}")
    result = orch.run_shot(shot, generate_image=True, generate_video=args.video)

    if result.status.value == "success":
        console.print(f"[green]✓ Success[/green]  Image: {result.image_path}")
        if result.video_path:
            console.print(f"              Video: {result.video_path}")
    else:
        console.print(f"[red]✗ Failed[/red]  {result.error}")


def main():
    parser = argparse.ArgumentParser(description="AI Manga Studio — Python-first pipeline")
    sub = parser.add_subparsers(dest="command")

    p_gen = sub.add_parser("generate", help="Run pipeline for a project")
    p_gen.add_argument("project_id", help="Project folder name under output/")
    p_gen.add_argument("--video", action="store_true", help="Generate video (I2V)")
    p_gen.add_argument("--retries", type=int, default=3, help="Max retries per shot")

    p_status = sub.add_parser("status", help="Show project status")
    p_status.add_argument("project_id")

    p_shot = sub.add_parser("shot", help="Process single shot JSON")
    p_shot.add_argument("shot_path", help="Path to shot JSON file")
    p_shot.add_argument("--video", action="store_true")
    p_shot.add_argument("--retries", type=int, default=3)

    args = parser.parse_args()

    if args.command == "generate":
        cmd_generate(args)
    elif args.command == "status":
        cmd_status(args)
    elif args.command == "shot":
        cmd_shot(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
