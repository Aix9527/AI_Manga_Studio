from __future__ import annotations

"""Real subprocess worker harness for cross-process kill/recover tests.

This process opens the SAME SQLite orchestration database as the parent test,
creates a real JobRepository / ProductionStepRunner / DurableWorker and runs
exactly one worker iteration. The execution adapter is the only faked part.

Usage:
    python tests/support/process_worker_harness.py \
        --database <path> --mode block|record|fail|terminal \
        --signal-file <path> --result-file <path> \
        --lease-seconds <n> --heartbeat-seconds <n>
"""

import argparse
import json
import os
import sys
import time
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from backend.orchestration.database import OrchestrationDatabase
from backend.orchestration.repository import JobRepository
from backend.orchestration.worker import DurableWorker, StepExecutionError
from backend.production.contracts import (
    ProductionExecutionRequest,
    ProductionExecutionResult,
)
from backend.production.executor import ProductionStepRunner


class BlockingExecutionAdapter:
    """Process A adapter: record binding, signal STARTED, then block forever."""

    def __init__(self, signal_file: Path, result_file: Path):
        self.signal_file = Path(signal_file)
        self.result_file = Path(result_file)

    def execute(self, request):
        self._record(request)
        self.signal_file.write_text("STARTED", encoding="utf-8")
        while True:
            time.sleep(60)

    def cancel(self, job_id: str) -> bool:
        return False

    def _record(self, request):
        record = {
            "event": "execute",
            "pid": os.getpid(),
            "worker_id": os.environ.get("WAVE4C_WORKER_ID", ""),
            "provider": request.provider_binding.provider,
            "binding": (
                request.provider_binding.model_dump(mode="json")
                if hasattr(request.provider_binding, "model_dump")
                else dict(request.provider_binding)
            ),
        }
        with open(self.result_file, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")


class RecordingSuccessAdapter:
    """Process B adapter: record binding and return success with no artifacts."""

    def __init__(self, signal_file: Path, result_file: Path):
        self.signal_file = Path(signal_file)
        self.result_file = Path(result_file)

    def execute(self, request):
        self._record(request)
        self.signal_file.write_text("STARTED", encoding="utf-8")
        return ProductionExecutionResult(
            artifacts=[],
            metadata={"test_adapter": "recording-success"},
        )

    def cancel(self, job_id: str) -> bool:
        return False

    def _record(self, request):
        record = {
            "event": "execute",
            "pid": os.getpid(),
            "worker_id": os.environ.get("WAVE4C_WORKER_ID", ""),
            "provider": request.provider_binding.provider,
            "binding": (
                request.provider_binding.model_dump(mode="json")
                if hasattr(request.provider_binding, "model_dump")
                else dict(request.provider_binding)
            ),
        }
        with open(self.result_file, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")


class UnavailableProviderAdapter:
    """Simulate the bound provider being unavailable: explicit failure, no fallback."""

    def __init__(self, signal_file: Path, result_file: Path):
        self.signal_file = Path(signal_file)
        self.result_file = Path(result_file)

    def execute(self, request):
        self._record(request)
        self.signal_file.write_text("STARTED", encoding="utf-8")
        raise StepExecutionError("PROVIDER_UNAVAILABLE", "bound provider unavailable")

    def cancel(self, job_id: str) -> bool:
        return False

    def _record(self, request):
        record = {
            "event": "execute",
            "pid": os.getpid(),
            "worker_id": os.environ.get("WAVE4C_WORKER_ID", ""),
            "provider": request.provider_binding.provider,
            "binding": (
                request.provider_binding.model_dump(mode="json")
                if hasattr(request.provider_binding, "model_dump")
                else dict(request.provider_binding)
            ),
        }
        with open(self.result_file, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")


class TerminalGuardAdapter:
    """Adapter that MUST never execute (terminal job must not be replayed)."""

    def __init__(self, signal_file: Path, result_file: Path):
        self.signal_file = Path(signal_file)
        self.result_file = Path(result_file)

    def execute(self, request):
        raise AssertionError("terminal job must not execute after restart")

    def cancel(self, job_id: str) -> bool:
        return False


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--database", required=True)
    parser.add_argument("--mode", required=True,
                        choices=["block", "record", "fail", "terminal"])
    parser.add_argument("--signal-file", required=True)
    parser.add_argument("--result-file", required=True)
    parser.add_argument("--lease-seconds", type=float, default=1.0)
    parser.add_argument("--heartbeat-seconds", type=float, default=0.2)
    parser.add_argument("--poll-seconds", type=float, default=0.05)
    args = parser.parse_args()

    database = OrchestrationDatabase(Path(args.database))
    repository = JobRepository(database)

    if args.mode == "block":
        adapter = BlockingExecutionAdapter(
            Path(args.signal_file), Path(args.result_file)
        )
    elif args.mode == "record":
        adapter = RecordingSuccessAdapter(
            Path(args.signal_file), Path(args.result_file)
        )
    elif args.mode == "fail":
        adapter = UnavailableProviderAdapter(
            Path(args.signal_file), Path(args.result_file)
        )
    elif args.mode == "terminal":
        adapter = TerminalGuardAdapter(
            Path(args.signal_file), Path(args.result_file)
        )
    else:  # pragma: no cover
        return 2

    runner = ProductionStepRunner(repository=repository, execution_port=adapter)
    worker = DurableWorker(
        repository,
        runner,
        retry_delays=[0, 0, 0],
        lease_seconds=args.lease_seconds,
        heartbeat_seconds=args.heartbeat_seconds,
    )

    # Run a bounded number of iterations so the process always exits.
    for _ in range(5):
        worked = worker.run_once()
        if not worked:
            time.sleep(args.poll_seconds)
    return 0


if __name__ == "__main__":
    sys.exit(main())
