from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path


class AcceptanceRunner:
    def __init__(self, project_root: str = "."):
        self.project_root = Path(project_root)
        self.results: list[dict] = []
        self.passed = 0
        self.failed = 0
        self.skipped = 0

    def run_all(self) -> dict:
        self._run("backend imports", self._test_backend_imports)
        self._run("orchestration schema", self._test_orchestration_schema)
        self._run("production contracts", self._test_production_contracts)
        self._run("migration scanner", self._test_migration_scanner)
        self._run("media validation", self._test_media_validation)
        self._run("job service create", self._test_job_service_create)
        self._run("database init", self._test_database_init)
        self._run("env diagnostics", self._test_env_diagnostics)
        self._run("frontend build check", self._test_frontend_build)
        self._run("config file check", self._test_config_files)

        report = {
            "timestamp": datetime.now().isoformat(),
            "passed": self.passed,
            "failed": self.failed,
            "skipped": self.skipped,
            "results": self.results,
        }
        return report

    def _run(self, name: str, fn) -> None:
        try:
            fn()
            self.results.append({"name": name, "status": "passed"})
            self.passed += 1
        except Exception as e:
            self.results.append({"name": name, "status": "failed", "error": str(e)})
            self.failed += 1

    def _test_backend_imports(self) -> None:
        from backend.orchestration import enums, schemas, config, database, repository
        from backend.production import contracts, input_loader

    def _test_orchestration_schema(self) -> None:
        from backend.orchestration.schemas import JobCreate, JobSettings, JobOptions
        opts = JobOptions(style="anime")
        settings = JobSettings(options=opts)
        data = JobCreate(project_id="test", input_path="test.txt")
        assert data.project_id == "test"

    def _test_production_contracts(self) -> None:
        from backend.production.contracts import InputContract, InputType
        c = InputContract(path="test.txt", type=InputType.NOVEL, title="Test")
        assert c.type == InputType.NOVEL

    def _test_migration_scanner(self) -> None:
        from backend.migration.scanner import ProjectScanner
        import tempfile, os
        tmpdir = os.path.join(tempfile.gettempdir(), "v5_test_projects")
        os.makedirs(tmpdir, exist_ok=True)
        scanner = ProjectScanner(tmpdir)
        projects = scanner.scan()
        assert isinstance(projects, list)

    def _test_media_validation(self) -> None:
        from backend.production.media_validation import MediaValidator
        v = MediaValidator()
        assert v.ffprobe_path == "ffprobe"

    def _test_job_service_create(self) -> None:
        from backend.orchestration.schemas import JobCreate
        data = JobCreate(project_id="p1", input_path="test.txt")
        assert data.project_id == "p1"
        assert data.input_type == "novel"

    def _test_database_init(self) -> None:
        import tempfile, uuid, os
        from backend.orchestration.database import OrchestrationDatabase
        db_path = os.path.join(tempfile.gettempdir(), f"test_v5_acceptance_{uuid.uuid4().hex[:8]}.db")
        db = OrchestrationDatabase(db_path)
        with db.connect() as conn:
            tables = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
            table_names = {r["name"] for r in tables}
            assert "jobs" in table_names
            assert "job_steps" in table_names
            assert "artifacts" in table_names
            assert "checkpoints" in table_names
        try:
            os.unlink(db_path)
        except OSError:
            pass

    def _test_env_diagnostics(self) -> None:
        from backend.migration.diagnostics import EnvironmentDiagnostics
        diag = EnvironmentDiagnostics()
        result = diag.run()
        assert result.overall in ("pass", "warn", "fail")

    def _test_frontend_build(self) -> None:
        frontend_dir = self.project_root / "frontend"
        if not frontend_dir.exists():
            self.results.append({"name": "frontend build check", "status": "skipped", "error": "no frontend dir"})
            self.skipped += 1
            return
        pkg_json = frontend_dir / "package.json"
        if not pkg_json.exists():
            self.results.append({"name": "frontend build check", "status": "skipped", "error": "no package.json"})
            self.skipped += 1
            return

    def _test_config_files(self) -> None:
        required = ["backend/main.py", "backend/orchestration/__init__.py", "backend/production/__init__.py"]
        for r in required:
            if not (self.project_root / r).exists():
                raise FileNotFoundError(f"Missing: {r}")
