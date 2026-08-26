from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.production.comfy_adapter import ComfyUIAdapter
from backend.video.h3_unified.comfy_media import H3ComfyMediaAdapter
from backend.video.h3_unified.execution import H3UnifiedExecutionService
from backend.video.h3_unified.live_gate import H3UnifiedLiveGate
from backend.video.h3_unified.reference_bundle import H3ReferenceBundle
from backend.video.h3_unified.ui_state import H3Mode, H3UnifiedRequest


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Preflight local RTX/ComfyUI H3 Unified capability; submit only with --submit.",
    )
    parser.add_argument("--comfy-url", default="http://127.0.0.1:8188")
    parser.add_argument("--evidence", default="storage/live/h3_unified_live_gate.json")
    parser.add_argument("--submit", action="store_true", help="Explicitly submit one smoke generation after preflight")
    parser.add_argument("--resume-prompt-id", default="", help="Resume this exact accepted ComfyUI prompt instead of submitting another")
    parser.add_argument("--mode", choices=[mode.value for mode in H3Mode], default=H3Mode.T2VA.value)
    parser.add_argument("--prompt", default="cinematic rain corridor, natural motion, stable identity")
    parser.add_argument("--negative-prompt", default="static, duplicate person, deformed limbs, flicker, watermark")
    parser.add_argument("--duration", type=float, default=5.0)
    parser.add_argument("--resolution", choices=("360p", "480p", "720p", "1080p"), default="480p")
    parser.add_argument("--aspect-ratio", choices=("16:9", "9:16", "1:1"), default="9:16")
    parser.add_argument("--steps", type=int, choices=(8, 10, 12, 15, 20), default=12)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--gpu-vram-gb", type=float, default=16.0)
    parser.add_argument("--character", default="")
    parser.add_argument("--secondary-character", default="")
    parser.add_argument("--location", default="")
    parser.add_argument("--costume", default="")
    parser.add_argument("--prop", default="")
    parser.add_argument("--expression", default="")
    parser.add_argument("--style", default="")
    parser.add_argument("--lighting", default="")
    parser.add_argument("--storyboard", default="")
    parser.add_argument("--video", action="append", default=[])
    parser.add_argument("--audio", action="append", default=[])
    parser.add_argument("--first-frame", default="")
    parser.add_argument("--last-frame", default="")
    return parser


def build_request(args: argparse.Namespace) -> H3UnifiedRequest:
    references = H3ReferenceBundle(
        character_identity=args.character,
        secondary_character=args.secondary_character,
        location=args.location,
        costume=args.costume,
        prop=args.prop,
        expression=args.expression,
        style=args.style,
        lighting=args.lighting,
        storyboard=args.storyboard,
        videos=tuple(args.video),
        audios=tuple(args.audio),
    )
    return H3UnifiedRequest(
        mode=H3Mode(args.mode),
        prompt=args.prompt,
        negative_prompt=args.negative_prompt,
        references=references,
        first_frame=args.first_frame,
        last_frame=args.last_frame,
        duration_seconds=args.duration,
        resolution=args.resolution,
        aspect_ratio=args.aspect_ratio,
        steps=args.steps,
        seed=args.seed,
        gpu_vram_gb=args.gpu_vram_gb,
        shot_project="H3 Unified Live Gate",
    )


async def _main(args: argparse.Namespace) -> int:
    base = ComfyUIAdapter(base_url=args.comfy_url)
    adapter = H3ComfyMediaAdapter(base=base)
    gate = H3UnifiedLiveGate(
        adapter=adapter,
        execution=H3UnifiedExecutionService(adapter=adapter),
    )
    request = build_request(args) if args.submit else None
    try:
        evidence = await gate.run(
            request=request,
            submit=args.submit,
            evidence_path=Path(args.evidence),
            resume_prompt_id=args.resume_prompt_id,
        )
    except Exception as error:
        print(json.dumps({"ok": False, "error": str(error), "evidence": args.evidence}, ensure_ascii=False, indent=2))
        return 2
    print(json.dumps(evidence, ensure_ascii=False, indent=2))
    return 0 if evidence["preflight"]["ok"] else 1


def main() -> int:
    return asyncio.run(_main(build_parser().parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
