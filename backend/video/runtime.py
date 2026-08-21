"""Long-video Chain Runtime (Phase 10.3-B).

Connects ChainManager (planning + keyframe memory) to the ComfyUI video
providers and persists a checkpoint manifest per project so an interrupted
run can resume: completed shots are kept, the in-flight shot restarts and
the remaining shots continue with inherited last frames.
"""

from __future__ import annotations

import logging
from dataclasses import asdict
from pathlib import Path
from typing import Any, Callable, Protocol

from backend.video.chain_manager import (
    ChainCheckpoint,
    ChainLink,
    ChainManager,
    ChainState,
)
from backend.video.worker_lock import LeaseError, WorkerLeaseLock

logger = logging.getLogger(__name__)

_MOTION_LEVEL_TO_BUCKET = {"low": 60, "medium": 110, "high": 160}


class VideoProvider(Protocol):
    """Minimal provider protocol: generate(VideoRequest) -> MediaArtifact."""

    async def generate(self, request: Any) -> Any:
        ...


FrameExtractor = Callable[[Path, Path], Path | None]


def _default_frame_extractor(video_path: Path, output_path: Path) -> Path | None:
    from backend.video.tailframe import extract_last_frame

    return extract_last_frame(video_path, output_path)


class ChainRuntime:
    """Drives a sequence of shots through ComfyUI with continuity + recovery."""

    def __init__(
        self,
        project_id: str = "default",
        workdir: str | Path = "storage/chains",
        chain: ChainManager | None = None,
        checkpoint: ChainCheckpoint | None = None,
        frame_extractor: FrameExtractor | None = None,
        identity_verifier: Any = None,
        lease_lock: WorkerLeaseLock | None = None,
        cost_meter: Any = None,
        video_engine_policy: dict | None = None,
    ):
        self.project_id = project_id
        self.workdir = Path(workdir)
        self.chain = chain or ChainManager()
        self.checkpoint = checkpoint or ChainCheckpoint(
            project_id, root=self.workdir
        ).load()
        self.frame_extractor = frame_extractor or _default_frame_extractor
        self.identity_verifier = identity_verifier
        self.lease_lock = lease_lock
        self.cost_meter = cost_meter
        # GPT Round-5: 默认 H3-first（用户指令：视频模型使用 MiniMax H3），
        # Wan 仅作为失败恢复/成本保护通道。
        self.video_engine_policy = dict(video_engine_policy or {})
        self.video_engine_policy.setdefault("primary_engine", "minimax_h3")

    # ------------------------------------------------------------------ plan
    def plan(self, shots: list[dict]) -> dict:
        """Plan chain modes for a shot list without running anything."""
        links = self.chain.plan_chain(shots)
        return {
            "project": self.project_id,
            "shots_total": len(links),
            "links": [asdict(link) for link in links],
            "report": self.chain.chain_report(links),
        }

    # ------------------------------------------------------------------ run
    async def run(
        self,
        shots: list[dict],
        provider: VideoProvider,
        *,
        resume: bool = True,
        output_root: str | Path | None = None,
    ) -> dict:
        """Generate videos for all shots in order.

        - ``resume=True`` skips shots already marked completed in the manifest.
        - After each successful generation the last frame is extracted and fed
          back into the ChainManager memory so the next ``last_frame`` link
          starts from the actual tail frame.
        - Each step persists the manifest, so a crash only loses the
          in-flight shot.
        """
        shots_by_id = {_shot_id(s): s for s in shots}
        completed = (
            set(self.checkpoint.completed_ids()) if resume else set()
        )
        links = self.chain.plan_chain(shots)
        output_root = Path(output_root) if output_root else self.workdir / self.project_id / "videos"
        output_root.mkdir(parents=True, exist_ok=True)

        results: list[dict] = []
        for link in links:
            sid = link.shot_id
            if sid in completed:
                results.append(
                    {"shot_id": sid, "status": "skipped", "reason": "already_completed"}
                )
                continue

            shot = shots_by_id.get(sid, {})
            state = self.checkpoint.state_for(sid) or ChainState(
                project_id=self.project_id,
                shot_id=sid,
                keyframe=shot.get("image_path", ""),
            )
            state.mode = link.mode
            state.workflow_id = str(
                shot.get("workflow_id", "wan22_ti2v5b_native")
            )
            state.retry_count = int(state.retry_count or 0)
            state.status = "running"
            state.keyframe = shot.get("image_path", "") or state.keyframe
            state.start_image = self._resolve_start_image(link, state, shot)
            state.end_frame = shot.get("end_frame_path", "")
            self.checkpoint.mark_running(state)

            lease_acquired = False
            if self.lease_lock is not None:
                try:
                    self.lease_lock.acquire(sid)
                    lease_acquired = True
                except LeaseError as exc:
                    state.status = "failed"
                    state.error = str(exc)
                    self.checkpoint.mark_failed(state)
                    results.append(asdict(state))
                    break
            if self.cost_meter is not None:
                self.cost_meter.start(sid)

            try:
                request = self._build_request(shot, state, output_root)
                artifact = await provider.generate(request)
                video_path = Path(getattr(artifact, "path", request.output_path))
                if not video_path.exists():
                    video_path = Path(request.output_path)

                last_frame = ""
                if self.frame_extractor is not None and video_path.exists():
                    lf_path = output_root / f"{sid}_last_frame.png"
                    extracted = self.frame_extractor(video_path, lf_path)
                    if extracted is not None:
                        last_frame = str(extracted)

                identity_report = await self._run_identity_check(shot, video_path)
                state.identity_report = identity_report

                if self.cost_meter is not None:
                    cost = self.cost_meter.stop(
                        sid, retry_count=state.retry_count
                    )
                    state.cost = cost.to_dict()

                state.status = "completed"
                state.output_video = str(video_path)
                state.last_frame = last_frame
                if last_frame:
                    self.chain.advance(sid, last_frame, shot)
                if (
                    state.identity_report
                    and state.identity_report.get("overall_verdict") == "fail"
                ):
                    state.status = "identity_failed"
                    state.error = "identity gate failed"
                    self.checkpoint.mark_failed(state)
                    results.append(asdict(state))
                    break
                self.checkpoint.mark_completed(state)
                results.append(asdict(state))
            except Exception as exc:  # noqa: BLE001 - checkpoint and stop
                state.status = "failed"
                state.error = str(exc)
                self.checkpoint.mark_failed(state)
                logger.exception("Chain shot %s failed", sid)
                results.append(asdict(state))
                break
            finally:
                if lease_acquired and self.lease_lock is not None:
                    self.lease_lock.release(sid)

        return {
            "project": self.project_id,
            "results": results,
            "summary": self.checkpoint.summary(),
        }

    def status(self) -> dict:
        return self.checkpoint.summary()

    # ------------------------------------------------------------- helpers
    def _resolve_start_image(self, link: ChainLink, state: ChainState, shot: dict) -> str:
        if link.mode == "last_frame":
            last = self.chain.memory.last()
            inherited = last.get("last_frame", "") or link.start_image
            return inherited or state.keyframe
        return shot.get("image_path", "") or state.keyframe

    def _build_request(self, shot: dict, state: ChainState, output_root: Path):
        from backend.production.providers import VideoRequest
        from backend.production.engine_policy import (
            decide_engine,
            engine_for_duration,
            h3_duration_for,
        )

        out = Path(shot.get("output_path") or output_root / f"{state.shot_id}.mp4")
        out.parent.mkdir(parents=True, exist_ok=True)

        motion = shot.get("motion_level", "medium")
        if isinstance(motion, (int, float)):
            bucket = int(motion)
        else:
            bucket = _MOTION_LEVEL_TO_BUCKET.get(str(motion), 127)

        # GPT Round-5: H3-first 引擎调度（默认 minimax_h3，Wan 仅 fallback）。
        # 显式指定 engine / premium_shot 的镜头仍按镜头覆盖。
        settings = {"video_engine_policy": self.video_engine_policy}
        engine_decision = decide_engine(shot, settings)
        engine = engine_decision.engine

        # 时长：H3 按 Duration Policy v1（premium 15s / 默认 10s 封顶）
        target_duration = float(shot.get("target_duration_s", 0.0) or 0.0)
        if engine == "minimax_h3":
            target_duration = h3_duration_for(shot, settings)
            shot["target_duration_s"] = target_duration
        else:
            target_duration = target_duration or 5.0
        frames, fps = engine_for_duration(engine, target_duration)
        width = int(shot.get("width", 480))
        height = int(shot.get("height", 832))
        if engine == "minimax_h3":
            # H3 竖屏长镜
            width = int(shot.get("width", 480))
            height = int(shot.get("height", 832))

        return VideoRequest(
            image_path=Path(state.start_image or state.keyframe),
            prompt=shot.get("prompt_tail") or shot.get("prompt", ""),
            negative_prompt=shot.get("negative_prompt", ""),
            seed=int(shot.get("seed", 0) or 0),
            width=width,
            height=height,
            frames=frames,
            fps=fps,
            output_path=out,
            motion_bucket_id=bucket,
            denoise_strength=float(shot.get("denoise_strength", 1.0)),
            ai_video=True,
            end_frame_path=state.end_frame,
            engine=engine,
        )


    async def _run_identity_check(self, shot: dict, video_path: Path) -> dict:
        """Phase 10.5-C: optional post-generation identity gate.

        When a shot carries ``character_references`` ({cid: embedding}) and the
        runtime was given an IdentityVerifier, sample the video and check every
        expected character.  Failing shots are recorded as ``identity_failed``
        and stop the chain so they can be re-run (checkpoint keeps the rest).
        """
        refs = shot.get("character_references") or {}
        if not refs or self.identity_verifier is None:
            return {}
        try:
            report = self.identity_verifier.verify_video(video_path, refs)
            return report.__dict__ if hasattr(report, "__dict__") else dict(report)
        except Exception as exc:  # noqa: BLE001 - gate must not crash the chain
            logger.warning("Identity gate error for %s: %s", shot.get("id"), exc)
            return {"error": str(exc)}


def _shot_id(shot: dict) -> str:
    return shot.get("id") or shot.get("shot_id") or ""
