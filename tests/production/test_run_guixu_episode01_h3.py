from __future__ import annotations

import importlib
from pathlib import Path
import subprocess
import sys

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _runner():
    try:
        return importlib.import_module("scripts.run_guixu_episode01_h3")
    except ModuleNotFoundError:
        pytest.fail("scripts.run_guixu_episode01_h3 is missing")


def _manifest(anchor_path: Path) -> dict:
    return {
        "output_root": "F:/AI_Manga_Studio/outputs/guixu_episode01_h3_v1",
        "anchors": {"苏晚": str(anchor_path)},
        "profiles": {
            "preview": {"width": 432, "height": 768, "fps": 24, "frames": 124, "steps": 4},
            "production": {"width": 576, "height": 1024, "fps": 24, "frames": 124, "steps": 6},
            "hero": {"width": 768, "height": 1344, "fps": 24, "frames": 124, "steps": 8},
        },
        "shots": [
            {
                "id": "S04",
                "workflow": "reference",
                "refs": ["苏晚"],
                "profile": "hero",
                "candidate_s": 5,
                "takes": 2,
                "seeds": [11, 12],
                "audio": False,
                "prompt": "portrait",
            }
        ],
    }


def test_pending_jobs_skip_existing_success(tmp_path: Path) -> None:
    runner = _runner()
    manifest = _manifest(tmp_path / "anchor.png")
    state = {"jobs": {"S04/take-01/preview": {"status": "success"}}}

    jobs = runner.pending_jobs(manifest, state, {"S04"}, "preview")

    assert [(job["shot"]["id"], job["take"], job["seed"]) for job in jobs] == [
        ("S04", 2, 12)
    ]


def test_pending_jobs_preserve_queued_prompt_for_resume(tmp_path: Path) -> None:
    runner = _runner()
    manifest = _manifest(tmp_path / "anchor.png")
    state = {
        "jobs": {
            "S04/take-01/preview": {
                "status": "queued",
                "prompt_id": "prompt-123",
            }
        }
    }

    jobs = runner.pending_jobs(manifest, state, {"S04"}, "preview")

    assert jobs[0]["prompt_id"] == "prompt-123"
    assert jobs[1].get("prompt_id") is None


def test_reference_request_contains_uploaded_anchor_refs(tmp_path: Path) -> None:
    runner = _runner()
    manifest = _manifest(tmp_path / "anchor.png")
    shot = manifest["shots"][0]

    request = runner.build_request(
        shot,
        manifest["profiles"],
        "preview",
        {"苏晚": "guixu_ep01/苏晚.png"},
        filename_prefix="guixu_episode01_h3_v1/S04/take-01",
    )

    assert request["workflow"] == "reference"
    assert request["ref_images"] == ["guixu_ep01/苏晚.png"]
    assert request["orientation"] == "portrait"
    assert request["params"]["frames"] == 124
    assert request["audio"] is False


def test_standard_request_has_no_reference_images(tmp_path: Path) -> None:
    runner = _runner()
    manifest = _manifest(tmp_path / "anchor.png")
    shot = {
        **manifest["shots"][0],
        "id": "S01",
        "workflow": "standard",
        "refs": [],
    }

    request = runner.build_request(
        shot,
        manifest["profiles"],
        "production",
        {},
        filename_prefix="guixu_episode01_h3_v1/S01/take-01",
    )

    assert request["workflow"] == "standard"
    assert "ref_images" not in request


def test_oom_falls_back_one_profile_without_cloud() -> None:
    runner = _runner()

    assert runner.next_profile_after_oom("hero") == "production"
    assert runner.next_profile_after_oom("production") == "preview"
    assert runner.next_profile_after_oom("preview") is None


def test_memory_is_freed_only_for_oom_recovery() -> None:
    runner = _runner()

    assert runner.should_free_memory_after(None) is False
    assert runner.should_free_memory_after(runner.ProductionErrorCode.COMFY_OOM) is True
    assert (
        runner.should_free_memory_after(
            runner.ProductionErrorCode.COMFY_EXECUTION_FAILED
        )
        is False
    )


def test_two_failed_repair_rounds_stop_the_shot() -> None:
    runner = _runner()

    assert runner.can_schedule_repair({"repair_rounds": 0}) is True
    assert runner.can_schedule_repair({"repair_rounds": 1}) is True
    assert runner.can_schedule_repair({"repair_rounds": 2}) is False


def test_preflight_rejects_missing_anchor_or_model(tmp_path: Path) -> None:
    runner = _runner()
    manifest = _manifest(tmp_path / "missing-anchor.png")
    model_root = tmp_path / "models"

    missing = runner.validate_required_files(manifest, model_root)

    assert str(tmp_path / "missing-anchor.png") in missing
    assert str(model_root / "diffusion_models" / "minimax_h3_fl2va_pruned_int8_convrot.safetensors") in missing
    assert str(model_root / "vae" / "minimax_h3_audio_vae_fp32.safetensors") in missing


def test_state_round_trip_is_atomic(tmp_path: Path) -> None:
    runner = _runner()
    path = tmp_path / "run_state.json"
    state = {"jobs": {"S04/take-01/preview": {"status": "queued"}}}

    runner.save_state(path, state)

    assert runner.load_state(path) == state
    assert not path.with_suffix(".json.tmp").exists()


def test_runner_can_be_invoked_as_a_direct_script() -> None:
    result = subprocess.run(
        [sys.executable, "scripts/run_guixu_episode01_h3.py", "--help"],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=30,
    )

    assert result.returncode == 0, result.stderr
    assert "preflight" in result.stdout


@pytest.mark.asyncio
async def test_run_job_reports_prompt_id_before_waiting_for_completion(
    tmp_path: Path,
) -> None:
    runner = _runner()
    submitted: list[str] = []

    class FakeProvider:
        def build_prompt(self, request: dict) -> dict:
            return {"prompt": {"1": {"class_type": "Fake"}}}

    class FakeAdapter:
        async def submit_workflow(self, prompt: dict) -> str:
            return "prompt-123"

        async def wait_for_completion(self, prompt_id: str) -> dict:
            raise RuntimeError("runner interrupted after submission")

    with pytest.raises(RuntimeError, match="interrupted"):
        await runner.run_job(
            FakeAdapter(),
            FakeProvider(),
            {"request": {}},
            tmp_path / "candidate.mp4",
            on_submitted=submitted.append,
        )

    assert submitted == ["prompt-123"]
