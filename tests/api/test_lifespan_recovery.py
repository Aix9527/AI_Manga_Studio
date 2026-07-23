from types import SimpleNamespace

from backend.main import create_job_runtime


class IdleRunner:
    def __init__(self, repository):
        self.repository = repository

    def run_next(self, job, cancel_requested):
        return None

    def cancel(self, job_id):
        return False


def test_runtime_recovers_expired_running_job(job_repo, running_job):
    config = SimpleNamespace(orchestration=SimpleNamespace(
        database_path=str(job_repo.database.path),
        retry_delays_seconds=[0, 0, 0],
        lease_seconds=30,
    ))
    repository, _, _ = create_job_runtime(config, runner_factory=IdleRunner)
    restored = repository.get_job(running_job["id"])
    assert restored["status"] == "queued"
    assert restored["steps"][0]["status"] == "completed"
