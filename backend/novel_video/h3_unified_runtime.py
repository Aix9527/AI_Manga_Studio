"""Strict formal runtime bindings for H3 Unified media references.

The mature NovelVideoRunner/TaskRunner remain unchanged for legacy Ref2VA.
These subclasses only extend scheduler/replay behavior when the persisted H3
package carries approved video/audio reference asset-version ids.
"""
from __future__ import annotations

import hmac
import json
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path

from backend.novel_video.continuity import ContinuityError
from backend.novel_video.h3_provider import H3SegmentRequest
from backend.novel_video.models import GenerationIdentity, H3ReferencePackage, RunEvent, RunStatus, ShotRecord
from backend.novel_video.runner import NovelVideoRunner
from backend.orchestration.worker import TaskRunner


@dataclass(frozen=True)
class H3UnifiedSegmentRequest(H3SegmentRequest):
    """Formal H3 request carrying verified optional motion/audio references."""

    video_paths: tuple[Path, ...] = ()
    audio_paths: tuple[Path, ...] = ()


class H3UnifiedNovelVideoRunner(NovelVideoRunner):
    """Persist authoritative media paths beside a compiled H3 Unified package."""

    def _enqueue_formal_task(self, run, shot: ShotRecord) -> None:
        package = shot.reference_package
        if package is None:
            raise ContinuityError("H3 reference package is not compiled")
        latest = self.repo.get_run(run.id)
        if latest is None or latest.status is not RunStatus.RENDERING:
            return
        project = self.repo.get_project(run.project_id)
        if project is None:
            raise KeyError("run project does not exist")
        task_id = self._task_id(run.id, shot)
        if self.task_queue.get(task_id) is None:
            picture_paths = [
                str(self._approved_asset_path(asset_id, run, shot))
                for asset_id in package.picture_asset_version_ids
            ]
            video_paths = [
                str(self._approved_media_asset_path(asset_id, run, media_kind="video"))
                for asset_id in package.video_reference_asset_version_ids
            ]
            audio_paths = [
                str(self._approved_media_asset_path(asset_id, run, media_kind="audio"))
                for asset_id in package.audio_reference_asset_version_ids
            ]
            suffix = task_id[-16:]
            payload = {
                "formal_novel_video": True,
                "run_id": run.id,
                "package": package.model_dump(mode="json"),
                "picture_paths": picture_paths,
                "video_paths": video_paths,
                "audio_paths": audio_paths,
                "output_video": f"{shot.id}-{suffix}.mp4",
                "output_tail": f"{shot.id}-{suffix}-tail.png",
                "package_sha256": self._binding(shot)["package_sha256"],
                "generation_identity": self._generation_identity(shot),
            }
            self.task_queue.enqueue(
                "video_generation",
                payload,
                project_id=run.project_id,
                task_id=task_id,
                retry_policy={"max_attempts": 1, "backoff_seconds": 0},
            )
        if not any(
            event.event_type == "formal_task_enqueued"
            and event.payload.get("task_id") == task_id
            for event in self.repo.list_events(run.id)
        ):
            self.repo.append_event(
                RunEvent(
                    run_id=run.id,
                    event_type="formal_task_enqueued",
                    payload={
                        "shot_id": shot.id,
                        "task_id": task_id,
                        "binding": self._binding(shot),
                        "generation_identity": self._generation_identity(shot),
                        "retry_nonce": shot.retry_nonce,
                    },
                )
            )

    def _approved_media_asset_path(self, asset_id: str, run, *, media_kind: str) -> Path:
        asset = self.repo.get_asset(asset_id)
        if (
            asset is None
            or asset.project_id != run.project_id
            or asset.state != "approved"
            or not self._file_matches(asset)
        ):
            raise ContinuityError(f"approved reference asset does not verify: {asset_id}")
        if media_kind == "video" and asset.kind != "video":
            raise ContinuityError(f"approved video reference has incompatible kind: {asset.kind}")
        if media_kind == "audio" and not _is_audio_kind(asset.kind):
            raise ContinuityError(f"approved audio reference has incompatible kind: {asset.kind}")
        return asset.path


class H3UnifiedTaskRunner(TaskRunner):
    """Replay H3 Unified tasks only from repository-authenticated media paths."""

    def _formal_replay_context(self, task):
        payload = task.payload or {}
        raw_package = H3ReferencePackage.model_validate(payload["package"])
        has_media = bool(
            raw_package.video_reference_asset_version_ids
            or raw_package.audio_reference_asset_version_ids
        )
        if not has_media:
            return super()._formal_replay_context(task)

        run_id = str(payload["run_id"])
        run = self.novel_video_repository.get_run(run_id)
        if run is None:
            raise KeyError(f"Novel-video run {run_id} does not exist")
        project = self.novel_video_repository.get_project(run.project_id)
        if project is None:
            raise KeyError(f"Novel-video project {run.project_id} does not exist")
        if task.project_id != run.project_id:
            raise ValueError("formal task project_id does not own its run")
        package = raw_package
        if not package.shot_id:
            raise ValueError("formal package needs a shot id")
        shot = self.novel_video_repository.get_shot(package.shot_id)
        if shot is None or shot.run_id != run_id:
            raise ValueError("formal package shot does not belong to its run")

        expected_hash = _formal_package_hash(package)
        strict_scheduler = "package_sha256" in payload
        if not strict_scheduler:
            raise ValueError("formal H3 unified media references require a scheduler package binding")
        if payload.get("package_sha256") != expected_hash:
            raise ValueError("formal task package hash does not verify")
        if shot.reference_package is None or _formal_package_hash(shot.reference_package) != expected_hash:
            raise ValueError("formal task package is stale against the persisted shot")

        previous = next(
            (
                item
                for item in self.novel_video_repository.list_shots(run_id)
                if item.sequence == shot.sequence - 1
            ),
            None,
        )
        picture_paths = self._verified_reference_paths(
            package.picture_asset_version_ids,
            payload.get("picture_paths", []),
            project_id=project.id,
            media_kind="picture",
            run_id=run_id,
            previous=previous,
        )
        video_paths = self._verified_reference_paths(
            package.video_reference_asset_version_ids,
            payload.get("video_paths", []),
            project_id=project.id,
            media_kind="video",
        )
        audio_paths = self._verified_reference_paths(
            package.audio_reference_asset_version_ids,
            payload.get("audio_paths", []),
            project_id=project.id,
            media_kind="audio",
        )

        output_root = (Path(project.root) / "outputs" / "formal").resolve()
        request = H3UnifiedSegmentRequest(
            package=package,
            picture_paths=picture_paths,
            output_video=self._formal_output_path(output_root, str(payload["output_video"])),
            output_tail=self._formal_output_path(output_root, str(payload["output_tail"])),
            video_paths=video_paths,
            audio_paths=audio_paths,
        )
        queue_checkpoint = dict(getattr(task, "checkpoint", {}) or {})
        attempt_id = str(
            queue_checkpoint.get("formal_generation_attempt_id")
            or f"{task.task_id}:{max(int(getattr(task, 'attempts', 0)), 1)}"
        )
        queue_checkpoint["formal_generation_attempt_id"] = attempt_id
        package_sha256 = str(payload["package_sha256"])
        generation_identity = GenerationIdentity(
            task_id=task.task_id,
            run_id=run_id,
            shot_id=package.shot_id,
            attempt_id=attempt_id,
            package_sha256=package_sha256,
        ).canonical()
        return payload, run, project, package, request, generation_identity, task

    def _verified_reference_paths(
        self,
        asset_ids,
        supplied_paths,
        *,
        project_id: str,
        media_kind: str,
        run_id: str | None = None,
        previous=None,
    ) -> tuple[Path, ...]:
        expected: list[Path] = []
        for asset_id in asset_ids:
            asset = self.novel_video_repository.get_asset(str(asset_id))
            if (
                asset is None
                or asset.project_id != project_id
                or asset.state != "approved"
                or not asset.path.is_file()
                or not hmac.compare_digest(_file_sha256(asset.path), asset.sha256)
            ):
                raise ValueError(f"formal {media_kind} reference is not an approved verified project asset")
            if media_kind == "video" and asset.kind != "video":
                raise ValueError("formal video reference has incompatible asset kind")
            if media_kind == "audio" and not _is_audio_kind(asset.kind):
                raise ValueError("formal audio reference has incompatible asset kind")
            if media_kind == "picture" and asset.kind == "tail":
                if (
                    previous is None
                    or previous.status.value != "approved"
                    or previous.approved_tail_asset_id != asset.id
                    or asset.run_id != run_id
                ):
                    raise ValueError("formal inherited tail is not the preceding approved run tail")
            expected.append(asset.path)

        supplied = tuple(Path(path) for path in supplied_paths)
        expected_tuple = tuple(expected)
        if supplied != expected_tuple:
            raise ValueError(f"formal task {media_kind} paths do not match approved references")
        return expected_tuple


def _formal_package_hash(package: H3ReferencePackage) -> str:
    encoded = json.dumps(
        package.model_dump(mode="json"),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return sha256(encoded.encode("utf-8")).hexdigest()


def _is_audio_kind(kind: str) -> bool:
    return kind == "audio" or kind.endswith("_audio")


def _file_sha256(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as file:
        for block in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()
