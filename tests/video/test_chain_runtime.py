from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path

from backend.video.chain_manager import ChainCheckpoint, ChainState
from backend.video.runtime import ChainRuntime


def _shot(sid: str, location: str, keyframe: str, **kw) -> dict:
    data = {
        "id": sid,
        "location": location,
        "time_of_day": "night",
        "image_path": keyframe,
        "prompt_tail": f"shot {sid}",
        "negative_prompt": "bad",
        "seed": 42,
        "motion_level": "low",
        "width": 480,
        "height": 832,
        "frames": 81,
        "fps": 24,
    }
    data.update(kw)
    return data


@dataclass
class FakeArtifact:
    path: Path


class FakeProvider:
    """Records requests and writes a dummy video file per shot."""

    def __init__(self, out_root: Path, fail_on: str | None = None):
        self.out_root = out_root
        self.fail_on = fail_on
        self.requests = []
        self.generated = []

    async def generate(self, request):
        self.requests.append(request)
        if self.fail_on and request.output_path.stem == self.fail_on:
            raise RuntimeError("comfy timeout")
        request.output_path.write_bytes(b"dummy-video")
        self.generated.append(request.output_path.stem)
        return FakeArtifact(path=request.output_path)


def _fake_extractor(video_path: Path, out: Path) -> Path | None:
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(b"last-frame")
    return out


def test_plan_modes_and_report(tmp_path: Path):
    rt = ChainRuntime(project_id="p1", workdir=tmp_path)
    plan = rt.plan([
        _shot("gx_001", "lab", "k1.png"),
        _shot("gx_002", "lab", "k2.png"),
        _shot("gx_003", "cave", "k3.png"),
    ])
    assert plan["shots_total"] == 3
    modes = [link["mode"] for link in plan["links"]]
    assert modes == ["keyframe", "last_frame", "reset"]
    assert plan["report"]["total"] == 3


def test_run_generates_in_order_with_last_frame_inheritance(tmp_path: Path):
    shots = [
        _shot("gx_001", "lab", "k1.png"),
        _shot("gx_002", "lab", "k2.png"),
        _shot("gx_003", "lab", "k3.png"),
    ]
    rt = ChainRuntime(project_id="p1", workdir=tmp_path, frame_extractor=_fake_extractor)
    provider = FakeProvider(tmp_path)

    result = asyncio.run(rt.run(shots, provider, resume=False))

    assert [r["status"] for r in result["results"]] == ["completed"] * 3
    assert provider.generated == ["gx_001", "gx_002", "gx_003"]

    # shot 2 (last_frame mode) must start from shot 1's extracted tail frame
    req2 = provider.requests[1]
    assert "gx_001_last_frame.png" in str(req2.image_path)
    assert req2.image_path.exists()
    # shot 1 started from its own keyframe
    assert "k1.png" in str(provider.requests[0].image_path)

    summary = result["summary"]
    assert summary["completed"] == ["gx_001", "gx_002", "gx_003"]
    assert summary["last_frame"].endswith("gx_003_last_frame.png")


def test_resume_keeps_completed_and_restarts_inflight(tmp_path: Path):
    shots = [_shot(f"gx_{i:03d}", "lab", f"k{i}.png") for i in range(1, 7)]

    # First run fails on gx_005 after gx_001-004 completed
    provider = FakeProvider(tmp_path, fail_on="gx_005")
    rt = ChainRuntime(project_id="p1", workdir=tmp_path, frame_extractor=_fake_extractor)
    result = asyncio.run(rt.run(shots, provider, resume=False))

    assert [r["status"] for r in result["results"]] == [
        "completed", "completed", "completed", "completed", "failed",
    ]
    assert provider.generated == ["gx_001", "gx_002", "gx_003", "gx_004"]

    # Second run resumes: gx_001-004 skipped, gx_005 + gx_006 generated
    provider2 = FakeProvider(tmp_path)
    rt2 = ChainRuntime(project_id="p1", workdir=tmp_path, frame_extractor=_fake_extractor)
    result2 = asyncio.run(rt2.run(shots, provider2, resume=True))

    assert [r["status"] for r in result2["results"]] == [
        "skipped", "skipped", "skipped", "skipped", "completed", "completed",
    ]
    assert provider2.generated == ["gx_005", "gx_006"]
    summary = result2["summary"]
    assert summary["completed"] == ["gx_001", "gx_002", "gx_003", "gx_004", "gx_005", "gx_006"]
    assert summary["failed"] == []


def test_status_reports_manifest(tmp_path: Path):
    rt = ChainRuntime(project_id="p1", workdir=tmp_path)
    status = rt.status()
    assert status["project"] == "p1"
    assert status["completed"] == []


def test_identity_gate_stops_chain_on_swap(tmp_path: Path):
    """Phase 10.5-C acceptance at runtime level: swapped character -> fail -> stop."""
    from backend.characters.identity import IdentityEngine
    from backend.video.identity_gate import IdentityVerifier

    class SwappedEmbedder:
        def embed_image(self, image_path: str) -> list[float]:
            return [0.0, 1.0]  # every frame looks like ChenYe

    def _id_extractor(video_path: Path, out_dir: Path, num_frames: int) -> list[Path]:
        out_dir.mkdir(parents=True, exist_ok=True)
        out = []
        for i in range(num_frames):
            f = out_dir / f"f{i}.png"
            f.write_bytes(b"x")
            out.append(f)
        return out

    shots = [
        _shot("gx_001", "lab", "k1.png"),
        _shot(
            "gx_002", "lab", "k2.png",
            character_references={"suwan": [1.0, 0.0]},
        ),
        _shot("gx_003", "lab", "k3.png"),
    ]
    verifier = IdentityVerifier(
        engine=IdentityEngine(embedder=SwappedEmbedder(), threshold=0.75),
        frame_extractor=_id_extractor,
    )
    rt = ChainRuntime(
        project_id="p1", workdir=tmp_path,
        frame_extractor=_fake_extractor,
        identity_verifier=verifier,
    )
    provider = FakeProvider(tmp_path)
    result = asyncio.run(rt.run(shots, provider, resume=False))

    statuses = [r["status"] for r in result["results"]]
    assert statuses[0] == "completed"
    assert statuses[1] == "identity_failed"
    assert len(statuses) == 2  # chain stopped; gx_003 not attempted
    assert provider.generated == ["gx_001", "gx_002"]
    assert result["summary"]["failed"] == ["gx_002"]


def test_stress_30_100_600_shots(tmp_path: Path):
    """GPT acceptance: Stage A 30 / Stage B 100 / Stage C 600 shots."""
    import time

    for n in (30, 100, 600):
        shots = [
            _shot(f"gx_{i:03d}", "lab" if i % 5 else "cave", f"k{i}.png")
            for i in range(1, n + 1)
        ]
        rt = ChainRuntime(
            project_id=f"stress_{n}", workdir=tmp_path,
            frame_extractor=_fake_extractor,
        )
        provider = FakeProvider(tmp_path)
        t0 = time.perf_counter()
        result = asyncio.run(rt.run(shots, provider, resume=False))
        elapsed = time.perf_counter() - t0

        assert len(result["results"]) == n
        assert all(r["status"] == "completed" for r in result["results"])
        assert result["summary"]["completed"] == [f"gx_{i:03d}" for i in range(1, n + 1)]
        assert provider.generated == [f"gx_{i:03d}" for i in range(1, n + 1)]
        assert elapsed < 20.0  # fake provider stays fast at scale (CI-safe bound)


def test_worker_lease_lock_prevents_double_generation(tmp_path: Path):
    """Two workers must not generate the same shot at the same time."""
    from backend.video.worker_lock import LeaseError, WorkerLeaseLock

    lock = WorkerLeaseLock(root=tmp_path / "leases", worker_id="worker-A")
    token = lock.acquire("gx_050")
    assert lock.holder("gx_050") == token

    lock2 = WorkerLeaseLock(root=tmp_path / "leases", worker_id="worker-B")
    try:
        lock2.acquire("gx_050")
        raised = False
    except LeaseError:
        raised = True
    assert raised

    lock.release("gx_050")
    assert lock2.acquire("gx_050")  # after release the second worker can take it


def test_lease_lock_integrated_into_runtime(tmp_path: Path):
    from backend.video.worker_lock import WorkerLeaseLock

    lock = WorkerLeaseLock(root=tmp_path / "leases", worker_id="w1")
    shots = [_shot("gx_001", "lab", "k1.png"), _shot("gx_002", "lab", "k2.png")]
    rt = ChainRuntime(project_id="p1", workdir=tmp_path, frame_extractor=_fake_extractor, lease_lock=lock)
    provider = FakeProvider(tmp_path)
    result = asyncio.run(rt.run(shots, provider, resume=False))
    assert [r["status"] for r in result["results"]] == ["completed", "completed"]
    assert lock.held() == []  # leases released after each shot


def test_cost_meter_records_gpu_time(tmp_path: Path):
    from backend.video.cost_meter import CostMeter

    meter = CostMeter()
    rt = ChainRuntime(project_id="p1", workdir=tmp_path, frame_extractor=_fake_extractor, cost_meter=meter)
    shots = [_shot("gx_001", "lab", "k1.png"), _shot("gx_002", "lab", "k2.png")]
    provider = FakeProvider(tmp_path)
    result = asyncio.run(rt.run(shots, provider, resume=False))
    summary = meter.summary()
    assert summary["shots"] == 2
    assert summary["total_gpu_time_s"] >= 0
    # cost persisted into the checkpoint states
    assert result["results"][0].get("cost", {}).get("shot") == "gx_001"

