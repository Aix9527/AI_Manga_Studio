import json
import urllib.error
import uuid
from pathlib import Path

import pytest
import yaml

import run


EXPECTED_README = """## 正式运行入口

- CLI：`python run.py --web` 或 `python run.py --novel <文本路径>`
- API：`python -m uvicorn backend.main:app --host 127.0.0.1 --port 8800`
- 正式任务接口：`/api/jobs`

`backend_v3/v4/v6/v7/v10/v11`、根目录 `pipeline.py` 和
`orchestrator.py` 仅保留为历史参考，不再是正式生产入口。

当前里程碑只提供可靠任务与项目底座。真实本地模型执行器未安装时，
任务会以 `PIPELINE_NOT_READY` 明确失败，不会生成占位图片或伪成片。
"""


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self):
        return json.dumps(self.payload).encode("utf-8")


def test_submit_job_posts_complete_payload_to_durable_api(tmp_path):
    novel = tmp_path / "story.txt"
    novel.write_text("测试故事", encoding="utf-8")
    captured = {}

    def opener(request, timeout):
        captured["method"] = request.method
        captured["url"] = request.full_url
        captured["headers"] = dict(request.header_items())
        captured["payload"] = json.loads(request.data)
        captured["timeout"] = timeout
        return FakeResponse({"id": "job-1", "status": "queued"})

    result = run.submit_job(
        novel, style="realistic", base_url="http://127.0.0.1:8800", opener=opener
    )

    idempotency_key = captured["payload"].pop("idempotency_key")
    assert captured == {
        "method": "POST",
        "url": "http://127.0.0.1:8800/api/jobs",
        "headers": {"Content-type": "application/json"},
        "payload": {
            "project_id": "story",
            "input_path": str(novel.resolve()),
            "input_type": "novel",
            "mode": "automatic",
            "shot_duration": 5,
            "width": 1080,
            "height": 1920,
            "fps": 24,
            "options": {"style": "realistic"},
        },
        "timeout": 10,
    }
    assert idempotency_key.startswith("cli-")
    assert str(uuid.UUID(idempotency_key.removeprefix("cli-"))) in idempotency_key
    assert result["id"] == "job-1"


def test_submit_job_generates_a_fresh_idempotency_key_per_submission(tmp_path):
    novel = tmp_path / "story.txt"
    novel.write_text("测试故事", encoding="utf-8")
    keys = []

    def opener(request, timeout):
        keys.append(json.loads(request.data)["idempotency_key"])
        return FakeResponse({"id": f"job-{len(keys)}", "status": "queued"})

    run.submit_job(novel, opener=opener)
    run.submit_job(novel, opener=opener)

    assert len(set(keys)) == 2


def test_submit_job_rejects_a_missing_input_file(tmp_path):
    missing = tmp_path / "missing.txt"

    with pytest.raises(FileNotFoundError, match="输入文件不存在"):
        run.submit_job(missing)


@pytest.mark.parametrize("error", [urllib.error.URLError("offline"), TimeoutError()])
def test_api_json_request_translates_local_connection_errors(error):
    def opener(request, timeout):
        raise error

    with pytest.raises(RuntimeError, match="本地服务不可用"):
        run.api_json_request("GET", "/api/jobs/job-1", opener=opener)


def test_monitor_job_polls_until_completed(monkeypatch):
    jobs = iter(
        [
            {"status": "queued", "progress": 0.0, "message": "Queued"},
            {"status": "running", "progress": 0.5, "message": "Running"},
            {"status": "completed", "progress": 1.0, "message": "Completed"},
        ]
    )
    requests = []
    sleeps = []

    def request(method, path):
        requests.append((method, path))
        return next(jobs)

    monkeypatch.setattr(run, "api_json_request", request)
    monkeypatch.setattr(run.time, "sleep", sleeps.append)

    assert run.monitor_job("job-1", poll_seconds=0.25) == 0
    assert requests == [("GET", "/api/jobs/job-1")] * 3
    assert sleeps == [0.25, 0.25]


@pytest.mark.parametrize("status", ["failed", "cancelled"])
def test_monitor_job_returns_failure_for_unsuccessful_terminal_status(monkeypatch, status):
    monkeypatch.setattr(
        run,
        "api_json_request",
        lambda method, path: {"status": status, "progress": 1.0, "message": status},
    )

    assert run.monitor_job("job-1", poll_seconds=0) == 1


def test_formal_launcher_source_does_not_spawn_historical_pipeline():
    source = Path(run.__file__).read_text(encoding="utf-8")
    assert 'PROJECT_ROOT / "pipeline.py"' not in source
    assert "orchestrator.py --novel" not in source
    for launcher in (Path("一键启动.bat"), Path("run.bat")):
        batch_source = launcher.read_text(encoding="utf-8")
        assert "pipeline.py" not in batch_source
        assert 'python -u "%~dp0run.py" --novel "!NOVEL_PATH!"' in batch_source


def test_entrypoint_manifest_encodes_the_exact_launcher_policy():
    manifest = yaml.safe_load(Path("config/entrypoints.yaml").read_text(encoding="utf-8"))

    assert manifest == {
        "schema_version": 1,
        "canonical": {
            "cli": "run.py",
            "api": "backend.main:app",
            "job_api": "/api/jobs",
            "project_api": "/api/projects",
        },
        "compatibility": [
            {"path": "backend/routes/pipeline.py", "status": "durable_facade"},
            {"path": "一键启动.bat", "status": "forwards_to_canonical_cli"},
            {"path": "run.bat", "status": "forwards_to_canonical_cli"},
        ],
        "reference_only": [
            {"path": "backend_v3", "status": "reference_only"},
            {"path": "backend_v4", "status": "reference_only"},
            {"path": "backend_v6", "status": "reference_only"},
            {"path": "backend_v7", "status": "reference_only"},
            {"path": "backend_v10", "status": "reference_only"},
            {"path": "backend_v11", "status": "reference_only"},
            {"path": "pipeline.py", "status": "reference_only"},
            {"path": "orchestrator.py", "status": "reference_only"},
            {"path": "pipeline.bat", "status": "reference_only"},
            {"path": "run_v7.bat", "status": "reference_only"},
            {"path": "start_v4.bat", "status": "reference_only"},
            {"path": "start_v6.bat", "status": "reference_only"},
        ],
        "policy": {
            "delete_legacy_files": False,
            "allow_placeholder_success": False,
        },
    }
    assert all(item["status"] != "canonical" for item in manifest["reference_only"])


def test_readme_states_the_exact_fail_closed_foundation_milestone():
    assert Path("README.md").read_text(encoding="utf-8") == EXPECTED_README
