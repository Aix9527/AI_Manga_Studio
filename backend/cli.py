#!/usr/bin/env python3
"""AI Manga Studio CLI — one-click novel to CG AI video generation.

Usage:
    python -m backend.cli generate --input novel.txt --output output.mp4
    python -m backend.cli generate --input novel.txt --comfy-url http://127.0.0.1:8188
    python -m backend.cli serve          # Start web UI
    python -m backend.cli diagnose        # Check environment
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(
        description="AI Manga Studio — 长篇小说 → CG AI 视频 一键生成",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python -m backend.cli generate -i 归墟.txt -o 归墟第一集.mp4
  python -m backend.cli generate -i novel.txt --comfy-url http://localhost:8188
  python -m backend.cli serve
  python -m backend.cli diagnose
        """,
    )

    sub = parser.add_subparsers(dest="command")

    # generate command
    gen = sub.add_parser("generate", help="从小说生成视频")
    gen.add_argument("-i", "--input", required=True, help="输入小说文件路径 (.txt)")
    gen.add_argument("-o", "--output", default="output.mp4", help="输出视频文件路径")
    gen.add_argument("--title", default="", help="视频标题")
    gen.add_argument("--comfy-url", default="http://127.0.0.1:8188", help="ComfyUI 地址")
    gen.add_argument("--image-model", default="flux", choices=["flux", "sd3"], help="图片生成模型")
    gen.add_argument("--video-model", default="ltx23", choices=["ltx23", "wan"], help="视频生成模型")
    gen.add_argument("--target-duration", type=int, default=60, help="目标视频时长（秒）")
    gen.add_argument("--max-shots", type=int, default=10, help="最大镜头数")
    gen.add_argument("--width", type=int, default=1080, help="输出宽度")
    gen.add_argument("--height", type=int, default=1920, help="输出高度")
    gen.add_argument("--fps", type=int, default=24, help="帧率")
    gen.add_argument("--skip-audio", action="store_true", help="跳过音频生成")
    gen.add_argument("--skip-composition", action="store_true", help="跳过视频合成")
    gen.add_argument("--ai-video", action="store_true", help="使用 Wan2.2 图生视频 (AI 动态视频)")
    gen.add_argument("--motion-bucket-id", type=int, default=127, help="Wan2.2 动感强度 (0-255, 默认127)")
    gen.add_argument("--video-frames", type=int, default=33, help="AI 视频帧数 (默认33)")
    gen.add_argument("--project-dir", default="projects", help="项目目录")

    # serve command
    sub.add_parser("serve", help="启动 Web UI 服务")

    # diagnose command
    sub.add_parser("diagnose", help="检查运行环境")

    args = parser.parse_args()

    if args.command == "generate":
        asyncio.run(cmd_generate(args))
    elif args.command == "serve":
        cmd_serve()
    elif args.command == "diagnose":
        cmd_diagnose()
    else:
        parser.print_help()


async def cmd_generate(args):
    """Generate video from novel."""
    print("=" * 60)
    print("AI Manga Studio — 长篇小说 → CG AI 视频")
    print("=" * 60)

    input_path = Path(args.input)
    if not input_path.exists():
        print(f"[ERROR] 输入文件不存在: {input_path}")
        sys.exit(1)

    print(f"\n输入: {input_path}")
    print(f"输出: {args.output}")
    print(f"ComfyUI: {args.comfy_url}")
    print()

    # Step 1: Load input
    print("[1/6] 加载小说文本...")
    from backend.production.input_loader import load_input, detect_input_type

    input_type = detect_input_type(str(input_path))
    loaded = load_input(str(input_path))
    title = args.title or loaded.contract.title or input_path.stem
    print(f"  类型: {input_type.value}, 标题: {title}")
    print(f"  章节数: {loaded.contract.chapter_count}, 总字数: {loaded.contract.total_words}")

    # Step 2: Build production plan
    print("[2/6] 生成分镜计划...")
    from backend.production.plan_builder import (
        PlanSettings, build_trailer_plan, save_plan,
    )

    project_id = title.replace(" ", "_")[:30]
    settings = PlanSettings(
        target_seconds=args.target_duration,
        max_shots=args.max_shots,
        width=args.width,
        height=args.height,
        fps=args.fps,
        provider=args.video_model,
    )
    plan = build_trailer_plan(project_id, loaded, settings)
    plan_path = Path(args.project_dir) / project_id / "production_plan.json"
    save_plan(plan, plan_path)
    print(f"  镜头数: {len(plan.shots)}, 总时长: {plan.total_duration:.1f}s")
    print(f"  计划已保存: {plan_path}")

    # Step 3: Run NLP pipeline (character extraction + story parsing)
    print("[3/6] 分析故事结构...")
    from backend.pipeline.orchestrator import PipelineOrchestrator
    from backend.pipeline.schemas import PipelineRequest

    pipeline = PipelineOrchestrator()
    pipeline_req = PipelineRequest(
        text=loaded.text,
        title=title,
        novel_id=project_id,
    )
    pipeline_result = pipeline.run(pipeline_req)
    print(f"  角色: {pipeline_result.characters_found}, 镜头: {pipeline_result.shots_planned}")
    print(f"  编译Prompt: {pipeline_result.prompts_compiled}")

    # Step 4: Generate images via ComfyUI
    print("[4/6] 生成关键帧图像...")
    output_dir = Path(args.project_dir) / project_id / "outputs"
    image_dir = output_dir / "images"
    image_dir.mkdir(parents=True, exist_ok=True)

    from backend.production.comfy_adapter import ComfyUIAdapter
    from backend.production.workflow_templates import WorkflowTemplate

    comfy = ComfyUIAdapter(base_url=args.comfy_url)
    comfy_available = await comfy.is_available()

    generated_images = []

    if comfy_available:
        print(f"  ComfyUI 已连接: {args.comfy_url}")

        # Load workflow template (fix: WorkflowTemplate is a frozen dataclass
        # with workflow/bindings fields — use the loader instead of the old
        # name=/template= constructor which no longer exists)
        workflow_path = Path("backend/production/workflows/flux_live_action.json")
        if workflow_path.exists():
            template = WorkflowTemplate.load(workflow_path)
        else:
            template = WorkflowTemplate(
                workflow=_create_default_image_template(),
                bindings={
                    "prompt": [("4", "text")],
                    "seed": [("7", "noise_seed")],
                    "width": [("6", "width"), ("10", "width")],
                    "height": [("6", "height"), ("10", "height")],
                    "filename_prefix": [("13", "filename_prefix")],
                },
            )

        from backend.production.comfy_image import FluxImageProvider
        from backend.production.providers import ImageRequest

        provider = FluxImageProvider(adapter=comfy, template=template)

        for i, shot in enumerate(plan.shots):
            shot_dir = image_dir / shot.id
            shot_dir.mkdir(parents=True, exist_ok=True)
            output_path = shot_dir / "frame.png"

            if output_path.exists():
                print(f"  [{i+1}/{len(plan.shots)}] {shot.id}: 已存在, 跳过")
                generated_images.append({"shot_id": shot.id, "path": str(output_path), "cached": True})
                continue

            print(f"  [{i+1}/{len(plan.shots)}] {shot.id}: 生成中...")
            try:
                request = ImageRequest(
                    prompt=shot.positive_prompt,
                    negative_prompt=shot.negative_prompt,
                    seed=shot.seed,
                    width=settings.generation_width,
                    height=settings.generation_height,
                    output_path=output_path,
                )
                await provider.generate(request)
                generated_images.append({"shot_id": shot.id, "path": str(output_path), "cached": False})
                print(f"    完成: {output_path}")
            except Exception as e:
                print(f"    失败: {e}")
                # Create placeholder
                _create_placeholder_image(output_path)
                generated_images.append({"shot_id": shot.id, "path": str(output_path), "cached": False, "error": str(e)})
    else:
        print(f"  [WARN] ComfyUI 未连接 ({args.comfy_url}), 创建占位图...")
        for i, shot in enumerate(plan.shots):
            shot_dir = image_dir / shot.id
            shot_dir.mkdir(parents=True, exist_ok=True)
            output_path = shot_dir / "frame.png"
            _create_placeholder_image(output_path)
            generated_images.append({"shot_id": shot.id, "path": str(output_path), "cached": False, "placeholder": True})

    # Step 5: Generate AI video (Wan2.2) if --ai-video enabled
    ai_video_generated = False
    video_dir = output_dir / "videos"

    if args.ai_video:
        print("[5/7] 生成 AI 动态视频 (Wan2.2)...")
        video_dir.mkdir(parents=True, exist_ok=True)

        if comfy_available:
            try:
                from backend.production.comfy_video import WanVideoProvider
                from backend.production.providers import VideoRequest

                from backend.production.workflow_registry import select_wan_video_workflow
                wan_spec = select_wan_video_workflow(has_end_frame=False)
                wan_workflow_path = wan_spec.path
                if wan_workflow_path.exists():
                    wan_template = WorkflowTemplate.load(wan_workflow_path)
                    wan_provider = WanVideoProvider(adapter=comfy, template=wan_template)

                    for i, shot in enumerate(plan.shots):
                        shot_video_dir = video_dir / shot.id
                        shot_video_dir.mkdir(parents=True, exist_ok=True)
                        output_video_path = shot_video_dir / "ai_clip.mp4"

                        if output_video_path.exists():
                            print(f"  [{i+1}/{len(plan.shots)}] {shot.id}: AI 视频已存在, 跳过")
                            continue

                        # Source image from step 4
                        source_image = image_dir / shot.id / "frame.png"
                        if not source_image.exists():
                            print(f"  [{i+1}/{len(plan.shots)}] {shot.id}: 无源图像, 跳过")
                            continue

                        print(f"  [{i+1}/{len(plan.shots)}] {shot.id}: Wan2.2 视频生成中...")
                        try:
                            video_request = VideoRequest(
                                image_path=source_image,
                                prompt=shot.positive_prompt,
                                negative_prompt=shot.negative_prompt,
                                seed=shot.seed,
                                width=settings.generation_width,
                                height=settings.generation_height,
                                frames=args.video_frames,
                                fps=args.fps,
                                output_path=output_video_path,
                                motion_bucket_id=args.motion_bucket_id,
                                denoise_strength=1.0,
                                ai_video=True,
                            )
                            await wan_provider.generate(video_request)
                            print(f"    完成: {output_video_path}")
                        except Exception as e:
                            print(f"    失败: {e}")

                    ai_video_generated = True
                    print(f"  AI 视频生成完成 (motion_bucket_id={args.motion_bucket_id})")
                else:
                    print("  [WARN] Wan2.2 工作流文件未找到, 跳过 AI 视频")
            except Exception as e:
                print(f"  [WARN] AI 视频生成失败: {e}")
        else:
            print("  [WARN] ComfyUI 未连接, 跳过 AI 视频生成")
    else:
        print("[5/7] 跳过 AI 视频生成 (未启用 AI 视频；已禁用 Ken Burns 静态兜底)")

    # Step 6: Generate audio
    audio_dir = output_dir / "audio"
    audio_files = []

    if not args.skip_audio:
        print("[6/7] 生成音频...")
        try:
            from backend.audio.tts_engine import TTSEngine, SFXEngine

            tts = TTSEngine(output_dir=str(audio_dir))
            sfx = SFXEngine(output_dir=str(audio_dir))

            for i, shot in enumerate(plan.shots):
                dialogue_path = audio_dir / f"{shot.id}_dialogue.wav"
                narration_path = audio_dir / f"{shot.id}_narration.wav"

                if shot.narration:
                    await tts.generate_narration(shot.narration, shot.id)
                if shot.dialogue:
                    await tts.generate_dialogue(
                        str(shot.dialogue[0]) if shot.dialogue else "",
                        shot.id,
                    )

                audio_files.append({
                    "shot_id": shot.id,
                    "dialogue": str(dialogue_path) if dialogue_path.exists() else "",
                    "narration": str(narration_path) if narration_path.exists() else "",
                })
                if (i + 1) % 5 == 0:
                    print(f"  [{i+1}/{len(plan.shots)}] 音频生成中...")
            print(f"  音频生成完成: {len(audio_files)} 个镜头")
        except Exception as e:
            print(f"  [WARN] 音频生成失败: {e}")
    else:
        print("[6/7] 跳过音频生成")

    # Step 7: Compose final video
    if not args.skip_composition:
        print("[7/7] 合成最终视频...")
        try:
            from backend.video.composer import VideoComposer, check_ffmpeg

            composer = VideoComposer(output_dir=str(output_dir))

            has_ffmpeg = check_ffmpeg()
            if has_ffmpeg:
                print("  FFmpeg 可用, 正在合成...")

                shot_data = []
                for i, shot in enumerate(plan.shots):
                    img = generated_images[i] if i < len(generated_images) else {}
                    aud = audio_files[i] if i < len(audio_files) else {}
                    ai_vid_path = video_dir / shot.id / "ai_clip.mp4"

                    shot_entry = {
                        "image": img.get("path", ""),
                        "audio": aud.get("narration", "") or aud.get("dialogue", ""),
                        "duration": shot.duration,
                        "subtitle": shot.narration[:50] if shot.narration else "",
                    }

                    if args.ai_video and ai_vid_path.exists():
                        shot_entry["ai_video"] = str(ai_vid_path)

                    shot_data.append(shot_entry)

                final_path = Path(args.output)
                composer.compose_sequence(shot_data, final_path, fps=args.fps, use_ai_video=args.ai_video)
                print(f"  视频已生成: {final_path}")
            else:
                print("  [WARN] FFmpeg 未安装, 跳过视频合成")
                print("  安装 FFmpeg: https://ffmpeg.org/download.html")
                print("  或使用: winget install ffmpeg")
        except Exception as e:
            print(f"  [WARN] 视频合成失败: {e}")
    else:
        print("[7/7] 跳过视频合成")

    # Summary
    print()
    print("=" * 60)
    print("生成完成!")
    print(f"  项目目录: {Path(args.project_dir) / project_id}")
    print(f"  生成图像: {len(generated_images)} 张")
    if args.ai_video:
        print(f"  AI 动态视频: Wan2.2 (motion={args.motion_bucket_id})")
    print(f"  生成音频: {len(audio_files)} 个")
    if not args.skip_composition and Path(args.output).exists():
        file_size = Path(args.output).stat().st_size
        print(f"  输出视频: {args.output} ({file_size / 1024 / 1024:.1f} MB)")
    print()
    print("使用 Web UI 查看和管理项目:")
    print(f"  python -m backend.cli serve")
    print("=" * 60)


def cmd_serve():
    """Start the web UI server."""
    import subprocess
    import sys

    print("=" * 50)
    print("AI Manga Studio — Web UI")
    print("=" * 50)

    backend_dir = Path(__file__).parent.parent

    print("\nStarting backend server...")
    backend_proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "backend.main:app",
         "--host", "0.0.0.0", "--port", "8000"],
        cwd=str(backend_dir),
    )

    time.sleep(2)
    print("  Backend API: http://localhost:8000")
    print("  API Docs:    http://localhost:8000/docs")

    # Check if frontend dist exists
    frontend_dist = backend_dir / "frontend" / "dist"
    if frontend_dist.exists() and (frontend_dist / "index.html").exists():
        print("  Frontend:    http://localhost:8000 (served statically)")
    else:
        print("\n前端未构建, 请在新终端运行:")
        print("  cd frontend && npm install && npm run dev")
        print("  Frontend: http://localhost:5173")

    print("\n按 Ctrl+C 停止服务.\n")

    try:
        backend_proc.wait()
    except KeyboardInterrupt:
        print("\n正在关闭...")
        backend_proc.terminate()
        backend_proc.wait()


def cmd_diagnose():
    """Check environment and report status."""
    print("=" * 50)
    print("AI Manga Studio — 环境诊断")
    print("=" * 50)

    checks = []

    # Python version
    checks.append(("Python", f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}", True))

    # Dependencies
    deps = {
        "fastapi": "fastapi",
        "aiohttp": "aiohttp",
        "pydantic": "pydantic",
        "uvicorn": "uvicorn",
    }
    for name, pkg in deps.items():
        try:
            __import__(pkg)
            checks.append((name, "已安装", True))
        except ImportError:
            checks.append((name, "未安装", False))

    # Optional dependencies
    optional = {
        "edge_tts": "edge-tts (TTS)",
        "PIL": "Pillow (图像处理)",
    }
    for pkg, label in optional.items():
        try:
            __import__(pkg)
            checks.append((label, "已安装", True))
        except ImportError:
            checks.append((label, "未安装 (可选)", True))

    # CosyVoice 2 voice cloning
    try:
        from backend.audio.voice_cloning import VoiceCloningProvider
        if VoiceCloningProvider.check_available():
            checks.append(("CosyVoice 2 (语音克隆)", "已安装", True))
        else:
            checks.append(("CosyVoice 2 (语音克隆)", "未安装 (可选)", True))
    except Exception:
        checks.append(("CosyVoice 2 (语音克隆)", "未安装 (可选)", True))

    # IP-Adapter workflow
    ipadapter_workflow = Path("backend/production/workflows/flux_ipadapter_faceid.json")
    checks.append(("IP-Adapter 工作流 (角色一致性)", "存在" if ipadapter_workflow.exists() else "缺失", True))

    # Wan2.2 workflow (official native chain, production default)
    wan22_workflow = Path("backend/production/workflows/wan22_ti2v5b_native.json")
    checks.append(("Wan2.2 原生工作流 (AI 动态视频)", "存在" if wan22_workflow.exists() else "缺失", True))
    wan22_wrapper_workflow = Path("backend/production/workflows/wan22_i2v.json")
    checks.append(("Wan2.2 Wrapper 工作流 (回滚)", "存在" if wan22_wrapper_workflow.exists() else "缺失", True))

    # FFmpeg
    from backend.video.composer import check_ffmpeg
    ffmpeg_ok = check_ffmpeg()
    checks.append(("FFmpeg", "已安装" if ffmpeg_ok else "未安装 (可选)", True))

    # ComfyUI
    print("\n检查 ComfyUI 连接...")
    try:
        import aiohttp

        async def _check_comfy():
            async with aiohttp.ClientSession() as session:
                try:
                    async with session.get(
                        "http://127.0.0.1:8188/system_stats",
                        timeout=aiohttp.ClientTimeout(total=5),
                    ) as resp:
                        if resp.status == 200:
                            return True
                except Exception:
                    pass
                return False

        comfy_ok = asyncio.run(_check_comfy())
        checks.append(("ComfyUI", "已连接" if comfy_ok else "未连接 (需要启动 ComfyUI)", True))
    except Exception:
        checks.append(("ComfyUI", "检查失败", True))

    # Storage
    storage = Path("storage")
    checks.append(("存储目录", f"存在 ({storage.absolute()})" if storage.exists() else "不存在", True))

    # Projects
    projects = Path("projects")
    if projects.exists():
        project_dirs = [d for d in projects.iterdir() if d.is_dir() and not d.name.startswith("_")]
        checks.append(("项目目录", f"存在 ({len(project_dirs)} 个项目)", True))
    else:
        checks.append(("项目目录", "不存在", True))

    print()
    for name, status, ok in checks:
        icon = "OK" if ok else "FAIL"
        print(f"  [{icon}] {name}: {status}")

    all_ok = all(ok for _, _, ok in checks)
    if all_ok:
        print("\n环境检查通过! 可以开始使用.")
    else:
        print("\n部分依赖缺失, 请运行:")
        print("  pip install -r requirements.txt")

    print("\n推荐安装:")
    print("  pip install edge-tts           # 免费 TTS 语音合成")
    print("  pip install cosyvoice          # 零样本语音克隆 (CosyVoice 2)")
    print("  pip install soundfile numpy    # 音频处理依赖")
    print("  winget install ffmpeg           # 视频合成工具")
    print("  pip install Pillow              # 图像处理")
    print("\n角色一致性 (IP-Adapter):")
    print("  在 ComfyUI 中安装: IPAdapter_plus + FaceID 节点")
    print("  工作流: backend/production/workflows/flux_ipadapter_faceid.json")


def _create_placeholder_image(output_path: Path) -> None:
    """Create a simple placeholder image."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        from PIL import Image, ImageDraw, ImageFont

        img = Image.new("RGB", (432, 768), color=(30, 30, 40))
        draw = ImageDraw.Draw(img)
        draw.rectangle([10, 10, 422, 758], outline=(80, 80, 100), width=2)
        draw.text(
            (216, 384),
            "AI Manga Studio\nCG 生成中...",
            fill=(200, 200, 220),
            anchor="mm",
        )
        img.save(str(output_path), "PNG")
    except ImportError:
        # Minimal PNG without PIL
        output_path.write_bytes(b"")


def _create_default_image_template() -> dict:
    """Create a minimal Flux image generation workflow template."""
    return {
        "1": {
            "class_type": "CheckpointLoaderSimple",
            "inputs": {"ckpt_name": "flux1-dev.safetensors"},
        },
        "2": {
            "class_type": "CLIPTextEncode",
            "inputs": {
                "text": "{prompt}",
                "clip": ["1", 1],
            },
        },
        "3": {
            "class_type": "EmptyLatentImage",
            "inputs": {
                "width": "{width}",
                "height": "{height}",
                "batch_size": 1,
            },
        },
        "4": {
            "class_type": "KSampler",
            "inputs": {
                "seed": "{seed}",
                "steps": 20,
                "cfg": 7.0,
                "sampler_name": "euler",
                "scheduler": "normal",
                "denoise": 1.0,
                "model": ["1", 0],
                "positive": ["2", 0],
                "negative": ["2", 0],
                "latent_image": ["3", 0],
            },
        },
        "5": {
            "class_type": "VAEDecode",
            "inputs": {
                "samples": ["4", 0],
                "vae": ["1", 2],
            },
        },
        "6": {
            "class_type": "SaveImage",
            "inputs": {
                "filename_prefix": "{filename_prefix}",
                "images": ["5", 0],
            },
        },
    }


if __name__ == "__main__":
    main()