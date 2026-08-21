"""The sole write boundary for the formal novel-to-video domain.

The runner and HTTP layer call this service; neither gets permission to alter
asset files, plans, or run state directly.  It intentionally does not call
cloud services or submit Comfy jobs.
"""
from __future__ import annotations

import shutil
import tempfile
import uuid
import json
import os
from dataclasses import asdict, replace
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from typing import BinaryIO, Iterable

from backend.novel_video.continuity import ContinuityCompiler, ContinuityError
from backend.novel_video.models import (
    AssetVersion,
    NovelVideoProject,
    ProductionMode,
    ProductionRun,
    RunCommand,
    RunEvent,
    RunStatus,
    ShotRecord,
)
from backend.novel_video.planner import ChapterPlanner
from backend.novel_video.repository import NovelVideoRepository
from backend.novel_video.schemas import ProjectCreateRequest
from backend.novel_video.storage import AtomicAssetStore
from backend.production.contracts import ChapterPlanBundle, NovelImportResult
from backend.production.input_loader import load_input


def _is_reparse_point(path: Path) -> bool:
    """Reject Unix symlinks and Windows reparse points before staging writes."""
    if path.is_symlink():
        return True
    try:
        attributes = path.stat().st_file_attributes
    except (AttributeError, FileNotFoundError, OSError):
        return False
    return bool(attributes & 0x400)  # FILE_ATTRIBUTE_REPARSE_POINT


class _ShotDecisionLock:
    """Crash-released, cross-process lock for one shot's approval decision."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._file = None

    def __enter__(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        descriptor = os.open(self.path, os.O_RDWR | os.O_CREAT, 0o600)
        self._file = os.fdopen(descriptor, "r+b", buffering=0)
        if os.fstat(self._file.fileno()).st_size == 0:
            self._file.write(b"0")
            os.fsync(self._file.fileno())
        self._file.seek(0)
        try:
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(self._file.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self._file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as error:
            self._file.close()
            self._file = None
            raise RuntimeError("shot candidate decision is already active") from error
        return self

    def __exit__(self, *_args) -> None:
        if self._file is None:
            return
        self._file.seek(0)
        if os.name == "nt":
            import msvcrt
            msvcrt.locking(self._file.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl
            fcntl.flock(self._file.fileno(), fcntl.LOCK_UN)
        self._file.close()
        self._file = None


class NovelVideoService:
    """Transactionally coordinate source, planning, run, and review writes."""

    def __init__(
        self,
        *,
        repo: NovelVideoRepository,
        asset_store: AtomicAssetStore | None = None,
        planner: ChapterPlanner | None = None,
        projects_root: Path,
    ) -> None:
        self.repo = repo
        self.asset_store = asset_store or AtomicAssetStore()
        self.planner = planner or ChapterPlanner()
        self.projects_root = projects_root.resolve()
        self._runner = None
        self._shot_decision_fault = lambda _point: None

    def attach_runner(self, runner) -> None:
        """Attach the lifecycle-owned runner without making HTTP state authoritative."""
        self._runner = runner

    def create_project(self, request: ProjectCreateRequest, *, principal: str = "local") -> NovelVideoProject:
        root = self._project_root(request.id)
        root.mkdir(parents=True, exist_ok=True)
        project = NovelVideoProject(
            id=request.id,
            name=request.name,
            root=root,
            owner_principal=principal,
            mode=request.mode,
            style=request.style,
            aspect_ratio=request.aspect_ratio,
            width=request.width,
            height=request.height,
            megapixel_profile=request.megapixel_profile,
            multiple=request.multiple,
            target_duration_seconds=request.target_duration_seconds,
            max_shots=request.max_shots,
            base_seed=request.base_seed,
            primary_video_engine=request.primary_video_engine,
            allow_wan_fallback=request.allow_wan_fallback,
            allow_cloud=request.allow_cloud,
        )
        return self.repo.create_project(project)

    def get_project_for_principal(self, project_id: str, *, principal: str) -> NovelVideoProject:
        project = self._require_project(project_id)
        # Projects persisted before local capability principals existed have
        # the schema default ``local``.  Only the authenticated desktop
        # principal may claim that compatibility alias; it is never a wildcard
        # for arbitrary valid principals.
        if project.owner_principal == "local" and principal == "desktop":
            return project
        if project.owner_principal != principal:
            raise PermissionError("project access is not authorized")
        return project

    def get_run_for_principal(self, run_id: str, *, principal: str) -> ProductionRun:
        run = self._require_run(run_id)
        self.get_project_for_principal(run.project_id, principal=principal)
        return run

    def get_asset_for_principal(self, asset_id: str, *, principal: str) -> AssetVersion:
        asset = self.repo.get_asset(asset_id)
        if asset is None:
            raise KeyError("asset does not exist")
        self.get_project_for_principal(asset.project_id, principal=principal)
        return asset

    def create_upload_staging_file(
        self, project_id: str, *, principal: str, suffix: str
    ) -> tuple[Path, BinaryIO]:
        """Create an exclusive staging file after final directory validation.

        The route never receives a writable directory path.  Every directory
        component is rechecked after creation and immediately before the
        exclusive open, which fails closed if a symlink/reparse swap occurs.
        """
        project = self.get_project_for_principal(project_id, principal=principal)
        if suffix.lower() not in {".txt", ".md"}:
            raise ValueError("source staging suffix is not permitted")
        upload_dir = self._confined(project.root / "source", project.root)
        upload_dir.mkdir(parents=True, exist_ok=True)
        upload_dir = self._confined(upload_dir, project.root)
        if _is_reparse_point(upload_dir):
            raise ValueError("source staging directory is not safe")
        for _attempt in range(8):
            token = uuid.uuid4().hex
            candidate = self._confined(upload_dir / f".upload-{token}{suffix.lower()}", project.root)
            # Revalidate after candidate composition: an attacker cannot turn
            # an earlier directory check into an external write target.
            if _is_reparse_point(upload_dir) or self._confined(upload_dir, project.root) != upload_dir:
                raise ValueError("source staging directory changed during creation")
            try:
                descriptor = os.open(
                    str(candidate),
                    os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0),
                    0o600,
                )
            except FileExistsError:
                continue
            except OSError as exc:
                raise ValueError("unable to create source staging file") from exc
            try:
                # A swap immediately after the exclusive open must not be
                # adopted.  The descriptor is closed and its name is removed
                # only if it still lies in the validated project tree.
                if _is_reparse_point(upload_dir) or self._confined(candidate, project.root) != candidate:
                    os.close(descriptor)
                    candidate.unlink(missing_ok=True)
                    raise ValueError("source staging directory changed during creation")
                return candidate, os.fdopen(descriptor, "wb")
            except Exception:
                try:
                    os.close(descriptor)
                except OSError:
                    pass
                raise
        raise RuntimeError("unable to allocate source staging file")

    def import_source(self, project_id: str, source_path: Path | str) -> NovelImportResult:
        project = self._require_project(project_id)
        source = Path(source_path).resolve()
        if source.suffix.lower() not in {".txt", ".md"}:
            raise ValueError("only .txt and .md novel sources are supported")
        if not source.is_file():
            raise FileNotFoundError(f"novel source does not exist: {source}")
        # Decode before copying so invalid/binary inputs never become project assets.
        decoded = load_input(str(source))
        digest = sha256(source.read_bytes()).hexdigest()
        final_path = self._confined(project.root / "source" / f"novel-original-{digest[:16]}{source.suffix.lower()}", project.root)
        final_path.parent.mkdir(parents=True, exist_ok=True)
        if not final_path.exists():
            with tempfile.NamedTemporaryFile(dir=final_path.parent, delete=False) as temporary:
                temporary_path = Path(temporary.name)
                with source.open("rb") as origin:
                    shutil.copyfileobj(origin, temporary)
            try:
                copied_path, copied_digest = self.asset_store.publish(temporary_path, final_path)
            except FileExistsError:
                # Another importer won the no-overwrite rename.  It is safe to
                # adopt only when its bytes prove it is the same source.
                copied_path, copied_digest = final_path, sha256(final_path.read_bytes()).hexdigest()
            finally:
                temporary_path.unlink(missing_ok=True)
            if copied_digest != digest:
                raise RuntimeError("source copy hash changed during import")
        else:
            copied_path = final_path
            copied_digest = sha256(copied_path.read_bytes()).hexdigest()
            if copied_digest != digest:
                raise ValueError("existing immutable source path has a different hash")

        asset = AssetVersion(
            id=f"source-{uuid.uuid4().hex}", project_id=project.id,
            run_id=f"source-{project.id}", kind="novel_source", state="approved",
            path=copied_path, sha256=copied_digest,
            metadata={"encoding": decoded.contract.metadata["encoding"], "original_filename": source.name, "source_size_bytes": source.stat().st_size},
        )
        registered = self.repo.register_source_asset(asset)
        return NovelImportResult(loaded=decoded, encoding=str(decoded.contract.metadata["encoding"]), sha256=copied_digest, copied_path=copied_path, asset=registered)

    def analyze(
        self, project_id: str, *, chapter_indexes: list[int], target_seconds: float | None = None,
        max_shots: int | None = None, provider: str = "local",
    ) -> ChapterPlanBundle:
        project = self._require_project(project_id)
        if provider != "local":
            # A project declaration alone is not a usable authorization.  The
            # first formal release has no registered cloud authorization
            # verifier/provider, so it fails closed before source bytes can
            # leave this process.
            raise PermissionError("cloud narrative analysis is not authorized for this project")
        source = self._require_source(project)
        loaded = load_input(str(source.path))
        resolved_target = target_seconds if target_seconds is not None else project.target_duration_seconds
        resolved_max_shots = max_shots if max_shots is not None else project.max_shots
        planned = self.planner.plan(
            loaded, chapter_indexes=chapter_indexes,
            target_seconds=resolved_target, max_shots=resolved_max_shots,
        )
        plan_id = self._plan_id(source.id, planned.source_sha256, planned.chapter_indexes, resolved_target, resolved_max_shots, planned.plan_version)
        bundle = replace(planned, source_asset_version_id=source.id, plan_id=plan_id, max_shots=resolved_max_shots)
        self.repo.save_chapter_plan(project.id, bundle, source_asset_id=source.id)
        return bundle

    def get_chapter_plan(
        self, project_id: str, *, chapter_indexes: list[int] | None = None, target_seconds: float | None = None,
        max_shots: int | None = None, plan_id: str | None = None,
    ) -> ChapterPlanBundle:
        project = self._require_project(project_id)
        source = self._require_source(project)
        if plan_id is None and chapter_indexes is None:
            raise ValueError("chapter indexes or an immutable plan_id is required")
        bundle = self.repo.get_chapter_plan(
            project_id, chapter_indexes or (), source_asset_id=source.id,
            target_seconds=target_seconds if target_seconds is not None else project.target_duration_seconds,
            max_shots=max_shots if max_shots is not None else project.max_shots,
            plan_id=plan_id,
        )
        if bundle is None:
            raise KeyError("chapter plan does not exist; analyze the selected chapters first")
        if bundle.source_asset_version_id != source.id or bundle.source_sha256 != source.sha256:
            raise ValueError("chapter plan does not match the current immutable source")
        return bundle

    def create_run(
        self, project_id: str, *, plan_id: str, mode: ProductionMode | str | None = None,
    ) -> ProductionRun:
        project = self._require_project(project_id)
        selected_mode = ProductionMode(mode or project.mode)
        bundle = self.get_chapter_plan(project_id, plan_id=plan_id)
        run = ProductionRun(
            id=f"run-{uuid.uuid4().hex}", project_id=project.id,
            chapter_indexes=list(bundle.chapter_indexes), mode=selected_mode,
            settings={"chapter_plan_version": bundle.plan_version, "chapter_plan_id": bundle.plan_id, "chapter_plan_sha256": bundle.source_sha256, "source_asset_version_id": bundle.source_asset_version_id},
        )
        assets = self.repo.list_assets_for_project(project.id)
        compiler = ContinuityCompiler(assets)
        shots: list[ShotRecord] = []
        previous: ShotRecord | None = None
        for shot_plan in bundle.shots:
            plan = self._shot_payload(project, shot_plan)
            shot = ShotRecord(id=shot_plan.id + "-" + run.id[-12:], run_id=run.id, chapter_id=shot_plan.scene_id, sequence=shot_plan.sequence, plan=plan)
            try:
                package = compiler.compile(shot, previous, shot_plan.continuity)
            except ContinuityError:
                # A same-action tail is not legal until the preceding shot has
                # passed QA.  Preserve the plan and compile it at execution time.
                package = None
                plan["reference_package_pending"] = True
                shot = shot.model_copy(update={"plan": plan})
            shots.append(shot.model_copy(update={"reference_package": package}))
            previous = shot
        self.repo.create_run_with_shots(run, shots)
        self.repo.append_event(RunEvent(run_id=run.id, event_type="run_created", payload={"chapter_indexes": run.chapter_indexes, "mode": run.mode.value}))
        return run

    def create_run_idempotent(
        self, project_id: str, *, plan_id: str, principal: str, idempotency_key: str,
        request_fingerprint: str, mode: ProductionMode | str | None = None,
    ) -> tuple[ProductionRun, bool]:
        project = self.get_project_for_principal(project_id, principal=principal)
        selected_mode = ProductionMode(mode or project.mode)
        bundle = self.get_chapter_plan(project_id, plan_id=plan_id)
        run = ProductionRun(
            id=f"run-{uuid.uuid4().hex}", project_id=project.id,
            chapter_indexes=list(bundle.chapter_indexes), mode=selected_mode,
            settings={"chapter_plan_version": bundle.plan_version, "chapter_plan_id": bundle.plan_id, "chapter_plan_sha256": bundle.source_sha256, "source_asset_version_id": bundle.source_asset_version_id},
        )
        assets = self.repo.list_assets_for_project(project.id)
        compiler = ContinuityCompiler(assets)
        shots: list[ShotRecord] = []
        previous: ShotRecord | None = None
        for shot_plan in bundle.shots:
            plan = self._shot_payload(project, shot_plan)
            shot = ShotRecord(id=shot_plan.id + "-" + run.id[-12:], run_id=run.id, chapter_id=shot_plan.scene_id, sequence=shot_plan.sequence, plan=plan)
            try:
                package = compiler.compile(shot, previous, shot_plan.continuity)
            except ContinuityError:
                package = None
                plan["reference_package_pending"] = True
                shot = shot.model_copy(update={"plan": plan})
            shots.append(shot.model_copy(update={"reference_package": package}))
            previous = shot
        persisted, replayed = self.repo.create_run_with_shots_idempotent(
            run, shots, principal=principal, idempotency_key=idempotency_key,
            request_fingerprint=request_fingerprint,
        )
        if not replayed:
            self.repo.append_event(RunEvent(run_id=persisted.id, event_type="run_created", payload={"chapter_indexes": persisted.chapter_indexes, "mode": persisted.mode.value}))
        return persisted, replayed

    def advance_until_gate(self, run_id: str) -> ProductionRun:
        run = self._require_run(run_id)
        if run.status is RunStatus.DRAFT:
            run = self.repo.update_run_status(run.id, RunStatus.PLANNING)
        if run.status is RunStatus.PLANNING:
            if run.mode is ProductionMode.PROFESSIONAL:
                run = self._replace_run(run, status=RunStatus.AWAITING_REVIEW, review_gate="character_scene_bibles")
            else:
                run = self.repo.update_run_status(run.id, RunStatus.RENDERING)
        elif run.status is RunStatus.AWAITING_REVIEW and run.mode is ProductionMode.PROFESSIONAL:
            # Calling start again is the explicit confirmation of the current
            # professional gate.  It never skips either review stop.
            if run.review_gate == "character_scene_bibles":
                run = self._replace_run(run, status=RunStatus.AWAITING_REVIEW, review_gate="storyboard")
            elif run.review_gate == "storyboard":
                run = self.repo.update_run_status(run.id, RunStatus.RENDERING)
            elif run.review_gate == "shot_candidate":
                run = self.repo.update_run_status(run.id, RunStatus.RENDERING)
        return run

    def command(self, run_id: str, command: RunCommand | str) -> ProductionRun:
        run = self._require_run(run_id)
        action = RunCommand(command)
        if action is RunCommand.START:
            updated = self.advance_until_gate(run.id)
        elif action is RunCommand.CANCEL:
            if run.status is RunStatus.CANCELLED:
                updated = run
            else:
                updated = self.repo.update_run_status(run.id, RunStatus.CANCELLED)
        elif action is RunCommand.PAUSE:
            if run.status is RunStatus.PAUSED:
                updated = run
            elif run.status not in {RunStatus.RENDERING, RunStatus.MIXING, RunStatus.VALIDATING}:
                raise ValueError("pause is only available during active execution")
            else:
                updated = self._replace_run(run, status=RunStatus.PAUSED, settings={**run.settings, "resume_status": run.status.value})
        elif action is RunCommand.RESUME:
            if run.status is not RunStatus.PAUSED:
                raise ValueError("resume requires a paused run")
            target = RunStatus(run.settings.get("resume_status", RunStatus.RENDERING.value))
            updated = self._replace_run(run, status=target, settings={key: value for key, value in run.settings.items() if key != "resume_status"})
        elif action is RunCommand.RETRY:
            if run.status not in {RunStatus.BLOCKED, RunStatus.INTERRUPTED}:
                raise ValueError("retry requires a blocked or interrupted run")
            # Requeue every failed/blocked shot so the runner re-executes the
            # first invalid step instead of reusing the stale failure record.
            # retry_nonce bumps the task id so the old failed task is ignored;
            # clearing the compiled package forces bible-aware recompilation.
            for shot in self.repo.list_shots(run.id):
                if shot.status.value in {"failed", "blocked"}:
                    self.repo.save_shot(shot.model_copy(update={
                        "status": type(shot.status).QUEUED,
                        "retry_nonce": shot.retry_nonce + 1,
                        "reference_package": None,
                    }))
            updated = self._replace_run(
                run, status=RunStatus.RENDERING,
                settings={key: value for key, value in run.settings.items() if key != "formal_prompt_checkpoints"},
            )
        else:
            raise ValueError(f"unsupported run command: {action.value}")
        self.repo.append_event(RunEvent(
            run_id=updated.id,
            event_type="run_command",
            payload={"command": action.value, "status": updated.status.value},
        ))
        wake = getattr(self._runner, "wake", None)
        if callable(wake):
            wake()
        return updated

    def get_run(self, run_id: str) -> ProductionRun:
        return self._require_run(run_id)

    def get_project(self, project_id: str) -> NovelVideoProject:
        return self._require_project(project_id)

    def events_page(
        self, run_id: str, *, after_sequence: int = 0, limit: int = 100
    ) -> list[RunEvent]:
        self._require_run(run_id)
        return self.repo.list_events_page(
            run_id, after_sequence=after_sequence, limit=limit
        )

    def retry_shot(self, shot_id: str) -> ShotRecord:
        """Requeue one failed/blocked shot only after proving its run ownership."""
        shot = self.repo.get_shot(shot_id)
        if shot is None:
            raise KeyError(f"shot {shot_id} does not exist")
        run = self._require_run(shot.run_id)
        self._require_project(run.project_id)
        if shot.status.value not in {"failed", "blocked"}:
            raise ValueError("only failed or blocked shots may be retried")
        updated = self.repo.update_shot_status(shot.id, type(shot.status).QUEUED)
        self.repo.append_event(RunEvent(
            run_id=run.id,
            event_type="shot_retry_requested",
            payload={"shot_id": updated.id, "attempt": updated.current_attempt},
        ))
        return updated

    def review_shot_candidate(
        self, shot_id: str, *, approve: bool, candidate_video_id: str,
        candidate_tail_id: str, qa: dict | None,
    ) -> ShotRecord:
        """Apply an explicit user/GPT decision at the isolated shot gate."""
        shot = self.repo.get_shot(shot_id)
        if shot is None:
            raise KeyError("shot does not exist")
        run = self._require_run(shot.run_id)
        if run.status is not RunStatus.AWAITING_REVIEW or run.review_gate != "shot_candidate":
            if not approve and any(
                event.event_type == "shot_candidate_rejected"
                and event.payload.get("shot_id") == shot.id
                and event.payload.get("candidate_video_id") == candidate_video_id
                and event.payload.get("candidate_tail_id") == candidate_tail_id
                for event in self.repo.list_events(run.id)
            ):
                return shot
            raise ValueError("shot candidate is not awaiting review")
        if shot.status is not type(shot.status).VALIDATING:
            raise ValueError("shot candidate is not validating")
        video = self.repo.get_asset(candidate_video_id)
        tail = self.repo.get_asset(candidate_tail_id)
        if video is None or tail is None or video.shot_id != shot.id or tail.shot_id != shot.id or tail.parent_id != video.id:
            raise ValueError("candidate pair does not belong to the shot")
        if shot.reference_package is None:
            raise ValueError("shot has no immutable H3 reference package")
        binding = {"run_id": run.id, "shot_id": shot.id, "package_sha256": sha256(json.dumps(shot.reference_package.model_dump(mode="json"), ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()}
        task_id, task_result = self._candidate_task_identity(
            run.id, shot.id, video, tail, binding,
        )
        identity = dict(video.metadata.get("generation_identity", {}))
        if not approve:
            return self.repo.reject_shot_candidate_decision(
                run_id=run.id, shot_id=shot.id,
                candidate_video_id=candidate_video_id,
                candidate_tail_id=candidate_tail_id, binding=binding,
                task_id=task_id, task_result=task_result,
                generation_identity=identity if len(identity) == 5 else None,
            )
        if qa is None:
            raise ValueError("approval requires visual QA")
        return self.commit_shot_candidate_decision(
            shot.id, candidate_video_id=video.id, candidate_tail_id=tail.id,
            binding=binding, qa=qa, expected_lease_id=None,
            task_id=task_id, task_result=task_result,
        )

    def commit_shot_candidate_decision(
        self, shot_id: str, *, candidate_video_id: str,
        candidate_tail_id: str, binding: dict[str, str], qa: dict,
        expected_lease_id: str | None, task_id: str,
        task_result: dict, generation_identity: dict[str, str] | None = None,
    ) -> ShotRecord:
        """Recoverably publish and commit one exact candidate video/tail pair.

        Filesystems and SQLite cannot form one native transaction.  A durable
        per-shot manifest bridges them: exact published bytes can be adopted
        after a crash, but no approved database asset is visible until both
        finals and every run/task/QA fence verify in one ``BEGIN IMMEDIATE``.
        """
        shot = self.repo.get_shot(shot_id)
        if shot is None:
            raise KeyError("shot does not exist")
        run = self._require_run(shot.run_id)
        project = self._require_project(run.project_id)
        video = self.repo.get_asset(candidate_video_id)
        tail = self.repo.get_asset(candidate_tail_id)
        if video is None or tail is None:
            raise ValueError("candidate decision pair is missing")
        if (task_result.get("video_asset_id") != video.id
                or task_result.get("tail_asset_id") != tail.id
                or task_result.get("prompt_id") != video.metadata.get("prompt_id")):
            raise ValueError("task result does not identify the exact candidate pair and prompt")

        candidate_identity = dict(video.metadata.get("generation_identity", {}))
        # Older offline recovery records predate the five-key identity.  They
        # remain replayable only through their legacy package binding; queued
        # scheduler decisions always supply the strict complete identity.
        exact_identity = generation_identity
        if exact_identity is None and set(candidate_identity) == {
            "task_id", "run_id", "shot_id", "attempt_id", "package_sha256",
        }:
            exact_identity = candidate_identity
        request = {
            "run_id": run.id, "shot_id": shot.id,
            "candidate_video_id": video.id, "candidate_tail_id": tail.id,
            "candidate_video_sha256": video.sha256,
            "candidate_tail_sha256": tail.sha256,
            "task_id": task_id, "task_result": dict(task_result),
            "generation_identity": exact_identity or candidate_identity,
            "binding": dict(binding), "qa": dict(qa),
        }
        request_sha256 = sha256(json.dumps(
            request, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
        ).encode()).hexdigest()
        transaction_token = sha256(
            f"shot-decision\0{run.id}\0{shot.id}\0{request_sha256}".encode()
        ).hexdigest()
        approved_dir = self._confined(
            project.root / "shots" / shot.id / "approved", project.root,
        )
        approved_dir.mkdir(parents=True, exist_ok=True)
        identity_token = sha256(shot.id.encode()).hexdigest()[:24]
        manifest_path = approved_dir / f".shot-decision-{identity_token}.json"
        lock_path = approved_dir / f".shot-decision-{identity_token}.lock"

        video_approved = self._decision_approved_asset(video, approved_dir)
        tail_approved = self._decision_approved_asset(tail, approved_dir)
        paths = {
            "video_stage": str(approved_dir / f".{transaction_token}.video.stage"),
            "tail_stage": str(approved_dir / f".{transaction_token}.tail.stage"),
            "video_final": str(video_approved.path),
            "tail_final": str(tail_approved.path),
        }
        expected_manifest = {
            "version": 1, "state": "prepared",
            "transaction_token": transaction_token,
            "request_sha256": request_sha256,
            "request": request, "paths": paths,
            "digests": {"video": video.sha256, "tail": tail.sha256},
            "approved_ids": {"video": video_approved.id, "tail": tail_approved.id},
            "published": {"video": False, "tail": False},
        }

        with _ShotDecisionLock(lock_path):
            manifest = self._load_shot_decision_manifest(manifest_path)
            if manifest is not None:
                self._assert_shot_decision_manifest(manifest, expected_manifest)
            else:
                self.repo.validate_shot_candidate_decision(
                    run_id=run.id, shot_id=shot.id,
                    candidate_video_id=video.id, candidate_tail_id=tail.id,
                    binding=binding, qa=qa,
                    expected_lease_id=expected_lease_id,
                    task_id=task_id, task_result=task_result,
                    generation_identity=exact_identity,
                )
                self._capture_decision_stage(video, Path(paths["video_stage"]))
                self._capture_decision_stage(tail, Path(paths["tail_stage"]))
                if video_approved.path.exists() or tail_approved.path.exists():
                    self._mark_shot_decision_recovery(
                        manifest_path, expected_manifest,
                        "a final path existed before this transaction was prepared",
                    )
                self._write_shot_decision_manifest(manifest_path, expected_manifest)
                manifest = expected_manifest

            # An exact DB commit may precede the manifest's final fsync.  The
            # repository replay branch authenticates its unique pair/event.
            committed = self.repo.get_shot_candidate_decision(transaction_token)
            if committed is not None:
                updated = self.repo.commit_shot_candidate_decision(
                    transaction_token=transaction_token,
                    request_sha256=request_sha256, run_id=run.id,
                    shot_id=shot.id, candidate_video_id=video.id,
                    candidate_tail_id=tail.id, approved_video=video_approved,
                    approved_tail=tail_approved, binding=binding, qa=qa,
                    expected_lease_id=expected_lease_id, task_id=task_id,
                    task_result=task_result, generation_identity=exact_identity,
                )
                self._finish_shot_decision_manifest(manifest_path, manifest)
                return updated

            self.repo.validate_shot_candidate_decision(
                run_id=run.id, shot_id=shot.id,
                candidate_video_id=video.id, candidate_tail_id=tail.id,
                binding=binding, qa=qa, expected_lease_id=expected_lease_id,
                task_id=task_id, task_result=task_result,
                generation_identity=exact_identity,
            )
            self._shot_decision_fault("before_first_publish")
            self._publish_decision_file(
                Path(paths["video_stage"]), video_approved.path, video.sha256,
                manifest_path, manifest, "video",
            )
            self._shot_decision_fault("between_publishes")
            self._publish_decision_file(
                Path(paths["tail_stage"]), tail_approved.path, tail.sha256,
                manifest_path, manifest, "tail",
            )
            self._shot_decision_fault("after_both_before_db")
            updated = self.repo.commit_shot_candidate_decision(
                transaction_token=transaction_token,
                request_sha256=request_sha256, run_id=run.id,
                shot_id=shot.id, candidate_video_id=video.id,
                candidate_tail_id=tail.id, approved_video=video_approved,
                approved_tail=tail_approved, binding=binding, qa=qa,
                expected_lease_id=expected_lease_id, task_id=task_id,
                task_result=task_result, generation_identity=exact_identity,
            )
            self._shot_decision_fault("after_db_before_manifest_commit")
            self._finish_shot_decision_manifest(manifest_path, manifest)
            return updated

    def _candidate_task_identity(
        self, run_id: str, shot_id: str, video: AssetVersion,
        tail: AssetVersion, binding: dict[str, str],
    ) -> tuple[str, dict[str, str]]:
        identity = dict(video.metadata.get("generation_identity", {}))
        strict = set(identity) == {"task_id", "run_id", "shot_id", "attempt_id", "package_sha256"}
        if strict:
            if identity["run_id"] != run_id or identity["shot_id"] != shot_id:
                raise ValueError("candidate generation identity does not own this shot")
            task_id = identity["task_id"]
        else:
            events = self.repo.list_events(run_id)
            tasks = [event.payload.get("task_id") for event in events
                     if event.event_type == "formal_task_enqueued"
                     and event.payload.get("shot_id") == shot_id
                     and event.payload.get("binding") == binding]
            if len(tasks) != 1 or not isinstance(tasks[0], str) or not tasks[0]:
                raise ValueError("candidate task identity does not verify exactly once")
            task_id = tasks[0]
        prompt_id = video.metadata.get("prompt_id")
        if not isinstance(prompt_id, str) or not prompt_id:
            raise ValueError("candidate prompt identity is missing")
        expected = {
            "video_asset_id": video.id, "tail_asset_id": tail.id,
            "prompt_id": prompt_id,
        }
        # In the running application the service is attached to the scheduler,
        # whose durable queue is the authority for an explicit review.  Tests
        # and offline recovery may not attach a runner; in that case the same
        # identity is still authenticated by the unique enqueue/success events
        # in the repository transaction.
        task_queue = getattr(self._runner, "task_queue", None)
        if strict and task_queue is None:
            raise ValueError("strict formal candidate approval requires an attached TaskQueue authority")
        if task_queue is not None:
            task = task_queue.get(task_id)
            result = dict(getattr(task, "result", None) or {}) if task else {}
            if task is None or task.status != "completed" or any(
                result.get(key) != value for key, value in expected.items()
            ):
                raise ValueError("durable task result does not identify the exact candidate pair")
            if strict and result.get("generation_identity") != identity:
                raise ValueError("durable task result generation identity is stale")
            events = self.repo.list_events(run_id)
            enqueued = [event for event in events if event.event_type == "formal_task_enqueued"
                        and event.payload.get("task_id") == task_id
                        and event.payload.get("generation_identity") == identity]
            succeeded = [event for event in events if event.event_type == "video_generation_succeeded"
                         and event.payload.get("video_asset_id") == video.id
                         and event.payload.get("tail_asset_id") == tail.id
                         and event.payload.get("generation_identity") == identity]
            if strict and (len(enqueued) != 1 or len(succeeded) != 1):
                raise ValueError("candidate queue/audit identity does not verify exactly once")
            return task_id, result
        return task_id, expected

    def _decision_approved_asset(
        self, candidate: AssetVersion, approved_dir: Path,
    ) -> AssetVersion:
        token = sha256(candidate.id.encode()).hexdigest()[:24]
        suffix = candidate.path.suffix or ".bin"
        final_path = approved_dir / f"{candidate.kind}-{token}{suffix}"
        return AssetVersion(
            id=f"approved-{token}", project_id=candidate.project_id,
            run_id=candidate.run_id, shot_id=candidate.shot_id,
            parent_id=candidate.id, kind=candidate.kind, state="approved",
            path=final_path, sha256=candidate.sha256,
            metadata={"approved_from": candidate.id, **dict(candidate.metadata)},
        )

    def _capture_decision_stage(self, candidate: AssetVersion, stage: Path) -> None:
        if stage.exists():
            if stage.is_file() and self._stream_digest(stage) == candidate.sha256:
                return
            raise ValueError("shot decision private stage has a different immutable hash")
        source = self._confined(candidate.path, self._require_project(candidate.project_id).root)
        digest = sha256()
        with source.open("rb") as origin, tempfile.NamedTemporaryFile(
            dir=stage.parent, prefix=f".{stage.name}.", delete=False,
        ) as target:
            temporary = Path(target.name)
            for chunk in iter(lambda: origin.read(1024 * 1024), b""):
                digest.update(chunk)
                target.write(chunk)
            target.flush()
            os.fsync(target.fileno())
        try:
            if digest.hexdigest() != candidate.sha256:
                raise ValueError("candidate asset file or SHA-256 no longer verifies")
            os.link(temporary, stage)
        except FileExistsError:
            if self._stream_digest(stage) != candidate.sha256:
                raise ValueError("shot decision private stage has a different immutable hash")
        finally:
            temporary.unlink(missing_ok=True)

    def _publish_decision_file(
        self, stage: Path, final: Path, digest: str,
        manifest_path: Path, manifest: dict, kind: str,
    ) -> None:
        if final.exists():
            if (manifest.get("published", {}).get(kind) is True
                    and final.is_file() and self._stream_digest(final) == digest):
                return
            # A process may have linked the immutable final just before the
            # durable manifest-state update.  The prepared manifest pins the
            # destination token and digest, so this exact inode is safely
            # adopted instead of turning a recoverable crash into a block.
            if final.is_file() and self._stream_digest(final) == digest:
                manifest.setdefault("published", {})[kind] = True
                manifest["state"] = "files_published" if all(
                    manifest["published"].get(item) for item in ("video", "tail")
                ) else f"{kind}_published"
                self._write_shot_decision_manifest(manifest_path, manifest)
                return
            self._mark_shot_decision_recovery(manifest_path, manifest,
                                               "an unrecorded final path already exists")
        if not stage.is_file() or self._stream_digest(stage) != digest:
            self._mark_shot_decision_recovery(manifest_path, manifest,
                                               "private stage is missing or corrupt")
        try:
            os.link(stage, final)
        except FileExistsError:
            self._mark_shot_decision_recovery(manifest_path, manifest,
                                               "a concurrent final path won publication")
        manifest.setdefault("published", {})[kind] = True
        manifest["state"] = "files_published" if all(
            manifest["published"].get(item) for item in ("video", "tail")
        ) else f"{kind}_published"
        self._write_shot_decision_manifest(manifest_path, manifest)

    def _finish_shot_decision_manifest(self, path: Path, manifest: dict) -> None:
        committed = {**manifest, "state": "committed"}
        self._write_shot_decision_manifest(path, committed)
        for key in ("video_stage", "tail_stage"):
            Path(committed["paths"][key]).unlink(missing_ok=True)

    def _mark_shot_decision_recovery(self, path: Path, manifest: dict,
                                     reason: str) -> None:
        recovery = {**manifest, "state": "recovery_required",
                    "recovery_reason": reason}
        self._write_shot_decision_manifest(path, recovery)
        raise ValueError(f"shot candidate decision recovery required: {reason}")

    @staticmethod
    def _assert_shot_decision_manifest(actual: dict, expected: dict) -> None:
        if actual.get("state") == "recovery_required":
            raise ValueError("shot candidate decision recovery required")
        for key in ("version", "transaction_token", "request_sha256", "request",
                    "paths", "digests", "approved_ids"):
            if actual.get(key) != expected.get(key):
                raise ValueError("shot candidate decision manifest conflicts with this request")

    @staticmethod
    def _load_shot_decision_manifest(path: Path) -> dict | None:
        if not path.is_file():
            return None
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise ValueError("shot candidate decision manifest is unreadable") from error
        if not isinstance(value, dict):
            raise ValueError("shot candidate decision manifest is malformed")
        return value

    @staticmethod
    def _write_shot_decision_manifest(path: Path, payload: dict) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=path.parent,
            prefix=f".{path.name}.", delete=False,
        ) as target:
            temporary = Path(target.name)
            json.dump(payload, target, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"))
            target.flush()
            os.fsync(target.fileno())
        try:
            os.replace(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)

    @staticmethod
    def _stream_digest(path: Path) -> str:
        digest = sha256()
        with path.open("rb") as source:
            for chunk in iter(lambda: source.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    def get_export(self, export_id: str) -> AssetVersion:
        asset = self.repo.get_asset(export_id)
        if asset is None or asset.kind != "export" or asset.state != "approved":
            raise KeyError("approved export does not exist")
        run = self._require_run(asset.run_id)
        if run.project_id != asset.project_id or run.export_asset_id != asset.id:
            raise ValueError("export ownership does not verify")
        self._require_project(asset.project_id)
        return asset

    def approve_asset(self, asset_id: str, *, approve_tail: bool = False) -> AssetVersion:
        candidate = self.repo.get_asset(asset_id)
        if candidate is None:
            raise KeyError(f"asset {asset_id} does not exist")
        if candidate.state != "candidate":
            raise ValueError("only candidate assets may be approved")
        if (candidate.shot_id and candidate.kind in {"video", "tail"}
                and (candidate.metadata.get("prompt_id") or candidate.metadata.get("generation_identity")
                     or candidate.parent_id)):
            raise ValueError("formal shot video/tail approval requires the exact pair review endpoint")
        if approve_tail and candidate.kind != "tail":
            raise ValueError("approve_tail may only approve a tail asset from the same shot")
        project = self._require_project(candidate.project_id)
        if not candidate.shot_id or self.repo.get_shot(candidate.shot_id) is None:
            raise ValueError("asset is not owned by a formal shot")
        source_path = self._confined(candidate.path, project.root)
        if not source_path.is_file():
            raise ValueError("candidate asset path or SHA-256 no longer verifies")
        suffix = source_path.suffix or ".bin"
        approval_token = sha256(candidate.id.encode("utf-8")).hexdigest()[:24]
        final_path = self._confined(project.root / "shots" / candidate.shot_id / "approved" / f"{candidate.kind}-{approval_token}{suffix}", project.root)
        final_path.parent.mkdir(parents=True, exist_ok=True)
        # Capture once from one open descriptor.  The staged bytes, not a later
        # reopened candidate path, are what is approved; the transaction below
        # rechecks the candidate's current digest before it can update state.
        captured = sha256()
        with source_path.open("rb") as origin, tempfile.NamedTemporaryFile(dir=final_path.parent, delete=False) as temporary:
            temporary_path = Path(temporary.name)
            for chunk in iter(lambda: origin.read(1024 * 1024), b""):
                captured.update(chunk)
                temporary.write(chunk)
        if captured.hexdigest() != candidate.sha256:
            temporary_path.unlink(missing_ok=True)
            raise ValueError("candidate asset file or SHA-256 no longer verifies")
        published_here = False
        try:
            try:
                approved_path, digest = self.asset_store.publish(temporary_path, final_path)
                published_here = True
            except FileExistsError:
                approved_path, digest = final_path, sha256(final_path.read_bytes()).hexdigest()
                if digest != candidate.sha256:
                    raise ValueError("existing staged approval path has a different immutable hash")
        finally:
            temporary_path.unlink(missing_ok=True)
        approved = AssetVersion(
            id=f"approved-{approval_token}", project_id=candidate.project_id, run_id=candidate.run_id,
            shot_id=candidate.shot_id, parent_id=candidate.id, kind=candidate.kind, state="approved",
            path=approved_path, sha256=digest, metadata={"approved_from": candidate.id, **dict(candidate.metadata)},
        )
        try:
            return self.repo.approve_candidate_asset(candidate.id, approved)
        except Exception:
            # Files never become visible as assets until the transaction above
            # commits.  Clean a failed new publication; a crash leaves the
            # deterministic file for exact-hash replay adoption, never reuse.
            if published_here and self.repo.get_asset(approved.id) is None:
                approved_path.unlink(missing_ok=True)
            raise

    def _shot_payload(self, project: NovelVideoProject, shot_plan) -> dict[str, object]:
        return {
            **asdict(shot_plan), "base_seed": project.base_seed, "prompt_version": "prompt-v1",
            "workflow_version": "h3-ref2va-api-v1", "width": project.width, "height": project.height,
            "aspect_ratio": project.aspect_ratio, "megapixel_profile": project.megapixel_profile,
            "multiple": project.multiple, "model_registry_ids": {},
            "character_reference_asset_version_ids": [], "scene_reference_asset_version_ids": [],
            "video_reference_asset_version_ids": [], "audio_reference_asset_version_ids": [],
        }

    async def generate_bible_assets(self, project_id: str, *, plan_id: str, principal: str = "desktop") -> list[dict[str, str]]:
        """Generate one approved scene reference image per planned scene (Flux 2 Klein).

        Fills ``scene_reference_asset_version_ids`` on each shot so the first
        H3 segment has an authoritative reference package.  Character bibles
        remain a follow-up; scene references are the minimal approved input.
        """
        project = self._require_project(project_id)
        bundle = self.get_chapter_plan(project_id, plan_id=plan_id)
        bibles_dir = self._confined(self._project_root(project_id) / "bibles" / "scenes", self._project_root(project_id))
        bibles_dir.mkdir(parents=True, exist_ok=True)

        from backend.production.comfy_adapter import ComfyUIAdapter
        from pathlib import Path as _P
        workflow_dir = _P(__file__).resolve().parent.parent / "production" / "workflows"
        import json as _json

        template = _json.loads((workflow_dir / "flux_ipadapter_faceid.json").read_text(encoding="utf-8"))["workflow"]
        adapter = ComfyUIAdapter(base_url="http://127.0.0.1:8188")
        style = "写实电影摄影，8K 细节，电影级布光，浅景深，都市冷色调，空镜无人物，无文字"
        owner_run = next((r.id for r in reversed(self.repo.list_runs()) if r.project_id == project.id), f"bible-{project.id}")
        created: list[dict[str, str]] = []
        scenes = list(bundle.scenes)
        for index, scene in enumerate(scenes, start=1):
            excerpt = str(scene.source_excerpt or "")[:90]
            prompt_text = f"{excerpt}。{style}"
            prompt = _json.loads(_json.dumps(template))
            for node_id in ("14", "15", "16", "17"):
                prompt.pop(node_id, None)
            for nid, node in prompt.items():
                cls = node.get("class_type", "")
                if cls == "CFGGuider":
                    node["inputs"]["model"] = ["1", 0]
                elif cls == "CLIPTextEncode":
                    node["inputs"]["text"] = prompt_text
                elif cls == "EmptyFlux2LatentImage":
                    node["inputs"]["width"], node["inputs"]["height"] = 1024, 576
                elif cls == "RandomNoise":
                    node["inputs"]["noise_seed"] = int(project.base_seed)
                elif cls == "SaveImage":
                    node["inputs"]["filename_prefix"] = f"novel_bible/{project.id}_scene{index:02d}"
            try:
                prompt_id = await adapter.submit_workflow(prompt)
                outputs = await adapter.wait_for_completion(prompt_id)
            except Exception as error:
                raise RuntimeError(f"bible scene {index} generation failed: {error}") from error
            artifact = self._first_artifact(outputs)
            if artifact is None:
                raise RuntimeError(f"bible scene {index} produced no image")
            import httpx as _httpx
            raw = _httpx.get(
                "http://127.0.0.1:8188/view",
                params={"filename": artifact["filename"], "subfolder": artifact.get("subfolder", ""), "type": artifact.get("type", "output")},
                trust_env=False, timeout=120,
            ).content
            digest = sha256(raw).hexdigest()
            final_path = bibles_dir / f"scene-{index:02d}.png"
            final_path.write_bytes(raw)
            asset = AssetVersion(
                id=f"bible-scene-{uuid.uuid4().hex[:16]}", project_id=project.id,
                run_id=owner_run, shot_id=None, parent_id=None,
                kind="scene", state="approved",
                path=final_path, sha256=digest,
                metadata={"plan_id": bundle.plan_id, "scene_id": scene.id, "prompt": prompt_text},
            )
            self.repo.append_asset(asset)
            created.append({"asset_id": asset.id, "scene_id": scene.id, "path": str(final_path)})
        # ContinuityCompiler discovers approved scene bibles by scene id, so
        # the immutable chapter plan does not need to be rewritten.
        return created, bundle.plan_id

    @staticmethod
    def _first_artifact(outputs: dict) -> Any | None:
        for node_outputs in outputs.values():
            for items in node_outputs.values():
                for item in items:
                    if isinstance(item, dict) and item.get("filename"):
                        return item
        return None

    def _replace_run(self, run: ProductionRun, *, status: RunStatus, review_gate: str | None = None, settings: dict | None = None) -> ProductionRun:
        return self.repo.save_run(run.model_copy(update={"status": status, "review_gate": review_gate, "settings": settings if settings is not None else run.settings, "updated_at": datetime.now(timezone.utc)}))

    def _project_root(self, project_id: str) -> Path:
        return self._confined(self.projects_root / project_id, self.projects_root)

    @staticmethod
    def _plan_id(
        source_asset_id: str, source_sha256: str, chapter_indexes: Iterable[int],
        target_seconds: float, max_shots: int | None, plan_version: str,
    ) -> str:
        payload = {
            "source_asset_id": source_asset_id, "source_sha256": source_sha256,
            "chapter_indexes": list(chapter_indexes), "target_seconds": target_seconds,
            "max_shots": max_shots, "plan_version": plan_version,
        }
        return "plan-" + sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()[:24]

    @staticmethod
    def _confined(path: Path, root: Path) -> Path:
        # ``Path.resolve`` consults process-global Windows path state and can
        # yield mismatched drive spellings during concurrent imports.  Both
        # paths are service-generated absolute paths; normalize lexically,
        # then reject any traversal before touching the filesystem.
        resolved_root = Path(os.path.normpath(os.path.abspath(str(root))))
        resolved_path = Path(os.path.normpath(os.path.abspath(str(path))))
        if _is_reparse_point(resolved_root):
            raise ValueError("path is not a safe local project directory")
        try:
            relative = resolved_path.relative_to(resolved_root)
        except ValueError as exc:
            raise ValueError("path escapes its project root") from exc
        # Lexical normalization prevents traversal; refuse existing symlink
        # components as well so an internal-looking asset cannot jump outside
        # the project root before it is read or published.
        probe = resolved_root
        for part in relative.parts:
            probe /= part
            if probe.exists() and _is_reparse_point(probe):
                raise ValueError("path escapes its project root through a symlink")
        return resolved_path

    def _require_project(self, project_id: str) -> NovelVideoProject:
        project = self.repo.get_project(project_id)
        if project is None:
            raise KeyError(f"project {project_id} does not exist")
        self._confined(project.root, self.projects_root)
        return project

    def _require_run(self, run_id: str) -> ProductionRun:
        run = self.repo.get_run(run_id)
        if run is None:
            raise KeyError(f"run {run_id} does not exist")
        return run

    def _require_source(self, project: NovelVideoProject) -> AssetVersion:
        if not project.source_asset_version_id:
            raise ValueError("project has no imported novel source")
        source = self.repo.get_asset(project.source_asset_version_id)
        if source is None or source.project_id != project.id or source.state != "approved":
            raise ValueError("project novel source is not an approved immutable asset")
        self._confined(source.path, project.root)
        if not source.path.is_file() or sha256(source.path.read_bytes()).hexdigest() != source.sha256:
            raise ValueError("project novel source hash no longer verifies")
        return source
