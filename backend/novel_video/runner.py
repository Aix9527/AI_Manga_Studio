"""Checkpoint scheduler for formal novel-video runs.

This module intentionally never constructs a provider or calls ComfyUI.  The
existing TaskQueue/TaskRunner pair is the single owner of H3 submission,
accepted-prompt recovery and the shared GPU lease.
"""
from __future__ import annotations

import asyncio
import json
import logging
import uuid
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from pathlib import Path
from typing import Any, Callable

from backend.novel_video.continuity import ContinuityCompiler, ContinuityError
from backend.novel_video.h3_provider import H3Ref2VASegmentProvider
from backend.novel_video.models import AssetVersion, GenerationIdentity, ProductionMode, RunEvent, RunStatus, ShotRecord, ShotStatus
from backend.novel_video.repository import NovelVideoRepository
from backend.novel_video.service import NovelVideoService

logger = logging.getLogger(__name__)


class NovelVideoRunner:
    """Schedule at most one durable decision or formal task per run per tick."""

    def __init__(self, *, service: NovelVideoService, task_queue: Any,
                 media_validator: Callable[[Path], Any] | None = None,
                 visual_reviewer: Callable[..., Any] | None = None,
                 poll_seconds: float = 0.2) -> None:
        self.service = service
        self.repo: NovelVideoRepository = service.repo
        self.task_queue = task_queue
        self.media_validator = media_validator or H3Ref2VASegmentProvider._validate_decoded_quality
        self.visual_reviewer = visual_reviewer
        self.poll_seconds = poll_seconds
        self.lease_id = f"novel-scheduler-{uuid.uuid4().hex}"
        self._stop = asyncio.Event()
        self._wake = asyncio.Event()
        self._task: asyncio.Task | None = None

    def start(self) -> None:
        if self._task is None or self._task.done():
            self._stop.clear()
            self._task = asyncio.create_task(self._loop(), name="novel-video-runner")

    async def stop(self) -> None:
        self._stop.set(); self._wake.set()
        if self._task is not None:
            try:
                await asyncio.wait_for(self._task, timeout=2)
            except asyncio.TimeoutError:
                # Scheduling never waits for a provider.  Leave durable queue
                # records/checkpoints intact for the next process.
                self._task.cancel()
        self._task = None

    def wake(self) -> None:
        self._wake.set()

    async def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                await self.run_once()
            except Exception:
                logger.exception("novel-video scheduler loop failed")
            self._wake.clear()
            try:
                await asyncio.wait_for(self._wake.wait(), timeout=self.poll_seconds)
            except asyncio.TimeoutError:
                pass

    async def run_once(self) -> None:
        # One unit per run establishes round-robin fairness without retaining
        # an in-memory queue as the source of truth.
        for run in self.repo.list_runs():
            if run.status in {RunStatus.DRAFT, RunStatus.PLANNING, RunStatus.RENDERING}:
                await self.execute_run(run.id)

    async def _claim_run(self, run_id: str) -> bool:
        return self.repo.claim_run_lease(run_id, self.lease_id, datetime.now(timezone.utc) + timedelta(seconds=30))

    async def _release_run(self, run_id: str) -> None:
        self.repo.release_run_lease(run_id, self.lease_id)

    async def execute_run(self, run_id: str, *, stop_after_shot: int | None = None) -> None:
        if not await self._claim_run(run_id):
            return
        try:
            run = self.repo.get_run(run_id)
            if run is None or run.status in {RunStatus.PAUSED, RunStatus.CANCELLED, RunStatus.BLOCKED, RunStatus.COMPLETED}:
                return
            if run.status in {RunStatus.DRAFT, RunStatus.PLANNING}:
                self.service.advance_until_gate(run_id)
                return
            if run.status is not RunStatus.RENDERING:
                return
            for shot in self.repo.list_shots(run_id):
                run = self.repo.get_run(run_id)
                if run is None or run.status in {RunStatus.PAUSED, RunStatus.CANCELLED, RunStatus.BLOCKED}:
                    return
                if self._is_exact_approved(shot):
                    continue
                if shot.status is ShotStatus.APPROVED:
                    await self._block(run_id, shot, "approved_asset_invalid", "approved asset/package/QA evidence no longer verifies")
                    return
                if shot.status is ShotStatus.VALIDATING:
                    await self._decide_candidate(run, shot)
                    return
                if stop_after_shot is not None and shot.sequence > stop_after_shot:
                    return
                task = self._task_for(shot)
                if task is not None and task.status in {"queued", "running"}:
                    # A busy worker/OS lock is a retryable scheduling state.
                    return
                if task is not None and task.status == "failed":
                    await self._block(run_id, shot, "formal_task_failed", task.error or "formal task failed")
                    return
                try:
                    shot = self._compile_if_needed(run, shot)
                    self._enqueue_formal_task(run, shot)
                except Exception as error:
                    await self._block(run_id, shot, "formal_task_schedule_failed", str(error))
                return
            # No missing video may fall through into composition.
            self.repo.update_run_status(run_id, RunStatus.MIXING)
            await self._block(run_id, None, "audio_composer_not_configured", "audio, mix and validation ports are not configured")
        finally:
            await self._release_run(run_id)

    def _compile_if_needed(self, run, shot: ShotRecord) -> ShotRecord:
        if shot.reference_package is not None:
            return shot
        previous = next((item for item in self.repo.list_shots(shot.run_id) if item.sequence == shot.sequence - 1), None)
        # Character/scene bibles are project-scoped; continuity tails are
        # constrained by ContinuityCompiler to the immediately preceding shot.
        compiler = ContinuityCompiler(self.repo.list_assets_for_project(run.project_id))
        package = compiler.compile(shot, previous, str(shot.plan["continuity"]))
        return self.repo.save_shot(shot.model_copy(update={
            "reference_package": package,
            "plan": {key: value for key, value in shot.plan.items() if key != "reference_package_pending"},
        }))

    def _enqueue_formal_task(self, run, shot: ShotRecord) -> None:
        package = shot.reference_package
        if package is None:
            raise ContinuityError("H3 reference package is not compiled")
        if self.repo.get_run(run.id).status is not RunStatus.RENDERING:
            return
        project = self.repo.get_project(run.project_id)
        if project is None:
            raise KeyError("run project does not exist")
        task_id = self._task_id(run.id, shot)
        if self.task_queue.get(task_id) is None:
            picture_paths = [str(self._approved_asset_path(asset_id, run, shot)) for asset_id in package.picture_asset_version_ids]
            suffix = task_id[-16:]
            payload = {
                "formal_novel_video": True, "run_id": run.id,
                "package": package.model_dump(mode="json"), "picture_paths": picture_paths,
                "output_video": f"{shot.id}-{suffix}.mp4", "output_tail": f"{shot.id}-{suffix}-tail.png",
                "package_sha256": self._binding(shot)["package_sha256"],
                "generation_identity": self._generation_identity(shot),
            }
            self.task_queue.enqueue("video_generation", payload, project_id=run.project_id,
                                    task_id=task_id, retry_policy={"max_attempts": 1, "backoff_seconds": 0})
        # Queue persistence and SQLite auditing cannot share a transaction.
        # On every pass repair the audit half idempotently after a crash.
        if not any(event.event_type == "formal_task_enqueued" and event.payload.get("task_id") == task_id
                   for event in self.repo.list_events(run.id)):
            self.repo.append_event(RunEvent(run_id=run.id, event_type="formal_task_enqueued", payload={
                "shot_id": shot.id, "task_id": task_id, "binding": self._binding(shot),
                "generation_identity": self._generation_identity(shot),
                "retry_nonce": shot.retry_nonce,
            }))

    async def _decide_candidate(self, run, shot: ShotRecord) -> None:
        task = self._task_for(shot)
        if task is None or task.status != "completed":
            # A TaskRunner result is the authoritative candidate identity. A
            # post-write crash leaves it retryable/recoverable, not blocked.
            return
        result = dict(task.result or {})
        video_id, tail_id = result.get("video_asset_id"), result.get("tail_asset_id")
        video = self.repo.get_asset(str(video_id)) if video_id else None
        tail = self.repo.get_asset(str(tail_id)) if tail_id else None
        if video is None or tail is None or tail.parent_id != video.id or not self._file_matches(video) or not self._file_matches(tail):
            await self._block(run.id, shot, "candidate_pair_invalid", "candidate video/tail pair no longer verifies")
            return
        identity = self._generation_identity(shot)
        asset_identity = dict(video.metadata.get("generation_identity", {}))
        strict_identity = set(asset_identity) == {"task_id", "run_id", "shot_id", "attempt_id", "package_sha256"}
        if strict_identity and (result.get("generation_identity") != identity or asset_identity != identity):
            await self._block(run.id, shot, "candidate_identity_invalid", "task/result generation identity is stale or incomplete")
            return
        if not strict_identity and asset_identity != self._binding(shot):
            await self._block(run.id, shot, "candidate_identity_invalid", "candidate package binding is stale")
            return
        if video.state != "candidate" or tail.state != "candidate" or video.shot_id != shot.id or tail.shot_id != shot.id:
            await self._block(run.id, shot, "candidate_pair_invalid", "task result does not identify the current candidate pair")
            return
        try:
            self.media_validator(video.path)
        except Exception as error:
            await self._block(run.id, shot, "candidate_media_invalid", str(error))
            return
        # No visual reviewer is never implicit approval.  It is a durable user
        # checkpoint for both professional mode and one-click safe default.
        if run.mode is ProductionMode.PROFESSIONAL or self.visual_reviewer is None:
            self._await_review(run, "shot_candidate", shot, "visual_reviewer_required")
            return
        decision = self.visual_reviewer(run=run, shot=shot, video=video, tail=tail)
        if asyncio.iscoroutine(decision):
            decision = await decision
        if not isinstance(decision, dict) or not decision.get("approved") or not decision.get("evidence_asset_ids"):
            self._await_review(run, "shot_candidate", shot, "visual_reviewer_rejected_or_incomplete")
            return
        # Approval files are immutable publication operations; re-check pause
        # and cancellation immediately before any state-changing decision.
        latest = self.repo.get_run(run.id)
        if latest is None or latest.status is not RunStatus.RENDERING:
            return
        self.service.commit_shot_candidate_decision(
            shot.id, candidate_video_id=video.id,
            candidate_tail_id=tail.id, binding=self._binding(shot),
            qa={**dict(decision), "reviewer": decision.get("reviewer", decision.get("model", "configured-reviewer"))},
            expected_lease_id=self.lease_id, task_id=task.task_id,
            task_result=result,
            generation_identity=identity if strict_identity else None,
        )

    def _await_review(self, run, gate: str, shot: ShotRecord, reason: str) -> None:
        latest = self.repo.get_run(run.id)
        if latest is None or latest.status is not RunStatus.RENDERING:
            return
        # The state model permits this explicit formal review checkpoint.
        updated = latest.model_copy(update={"status": RunStatus.AWAITING_REVIEW, "review_gate": gate})
        self.repo.save_run(updated)
        self.repo.append_event(RunEvent(run_id=run.id, event_type="review_required", payload={"shot_id": shot.id, "gate": gate, "reason": reason}))

    def _task_for(self, shot: ShotRecord):
        return self.task_queue.get(self._task_id(shot.run_id, shot)) if shot.reference_package is not None else None

    def _task_id(self, run_id: str, shot: ShotRecord) -> str:
        task_key = {**self._binding(shot), "retry_nonce": shot.retry_nonce}
        return "formal-" + sha256(json.dumps(task_key, sort_keys=True).encode()).hexdigest()[:24]

    def _binding(self, shot: ShotRecord) -> dict[str, str]:
        if shot.reference_package is None:
            return {"run_id": shot.run_id, "shot_id": shot.id, "package_sha256": "pending"}
        encoded = json.dumps(shot.reference_package.model_dump(mode="json"), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return {"run_id": shot.run_id, "shot_id": shot.id, "package_sha256": sha256(encoded.encode()).hexdigest()}

    def _generation_identity(self, shot: ShotRecord) -> dict[str, str]:
        binding = self._binding(shot)
        if binding["package_sha256"] == "pending":
            raise ContinuityError("generation identity requires a compiled package")
        task_id = self._task_id(shot.run_id, shot)
        return GenerationIdentity(
            task_id=task_id, run_id=shot.run_id, shot_id=shot.id,
            attempt_id=f"{task_id}:1", package_sha256=binding["package_sha256"],
        ).canonical()

    def _approved_asset_path(self, asset_id: str, run, shot: ShotRecord) -> Path:
        asset = self.repo.get_asset(asset_id)
        if asset is None or asset.project_id != run.project_id or asset.state != "approved" or not self._file_matches(asset):
            raise ContinuityError(f"approved reference asset does not verify: {asset_id}")
        if asset.kind == "tail" and asset.run_id != run.id:
            raise ContinuityError("continuity tail must belong to the current run")
        return asset.path

    def _is_exact_approved(self, shot: ShotRecord) -> bool:
        if shot.status is not ShotStatus.APPROVED or shot.reference_package is None:
            return False
        video, tail = self.repo.get_asset(shot.approved_video_asset_id or ""), self.repo.get_asset(shot.approved_tail_asset_id or "")
        if not video or not tail or video.state != "approved" or tail.state != "approved" or tail.parent_id is None:
            return False
        if not self._file_matches(video) or not self._file_matches(tail):
            return False
        candidate_video, candidate_tail = self.repo.get_asset(video.parent_id or ""), self.repo.get_asset(tail.parent_id)
        if (candidate_video is None or candidate_tail is None or candidate_video.state != "candidate"
                or candidate_tail.state != "candidate" or candidate_tail.parent_id != candidate_video.id):
            return False
        try:
            self.media_validator(video.path)
        except Exception:
            return False
        identity = dict(video.metadata.get("generation_identity", {}))
        decision = self.repo.get_shot_candidate_decision_for_shot(shot.id)
        expected_identity = self._generation_identity(shot)
        if identity not in (expected_identity, self._binding(shot)):
            return False
        # Pre-migration manually approved records have no pair-decision row.
        # They remain readable for historical projects; scheduler-originated
        # identities never take this compatibility branch.
        if decision is None:
            return identity == self._binding(shot)
        if (decision.get("generation_identity") != expected_identity
                or decision.get("approved_video_id") != video.id
                or decision.get("approved_tail_id") != tail.id
                or decision.get("candidate_video_id") != candidate_video.id
                or decision.get("candidate_tail_id") != candidate_tail.id):
            return False
        events = [event for event in self.repo.list_events(shot.run_id)
                  if event.event_type == "shot_approved"
                  and event.payload.get("decision_token") == decision.get("transaction_token")]
        if (len(events) != 1 or events[0].payload.get("video_asset_id") != video.id
                or events[0].payload.get("tail_asset_id") != tail.id
                or events[0].payload.get("generation_identity") != expected_identity):
            return False
        qa = decision.get("qa", {})
        evidence = qa.get("evidence_sha256", {}) if isinstance(qa, dict) else {}
        if not evidence or not qa.get("reason") or not qa.get("reviewer") or not qa.get("version"):
            return False
        for asset_id, digest in evidence.items():
            asset = self.repo.get_asset(str(asset_id))
            if (asset is None or asset.kind != "qa_evidence" or asset.state != "approved"
                    or asset.project_id != video.project_id or asset.run_id != shot.run_id
                    or asset.shot_id != shot.id or asset.sha256 != digest
                    or not self._file_matches(asset)
                    or (asset.parent_id != candidate_video.id
                        and asset.metadata.get("candidate_video_asset_id") != candidate_video.id)
                    or dict(asset.metadata.get("generation_identity", {})) != expected_identity):
                return False
        return True

    @staticmethod
    def _file_matches(asset: AssetVersion) -> bool:
        if not asset.path.is_file() or asset.path.stat().st_size == 0:
            return False
        digest = sha256()
        with asset.path.open("rb") as source:
            for chunk in iter(lambda: source.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest() == asset.sha256

    async def _block(self, run_id: str, shot: ShotRecord | None, reason: str, message: str) -> None:
        current = self.repo.get_run(run_id)
        if current is None or current.status in {RunStatus.PAUSED, RunStatus.CANCELLED}:
            return
        evidence = {"failure_key": f"runner:{reason}:{shot.id if shot else ''}", "reason": reason, "message": message}
        self.repo.block_generation_failure(run_id, shot_id=shot.id if shot else None, evidence=evidence)
        self.repo.append_event(RunEvent(run_id=run_id, event_type="run_blocked", payload=evidence))
