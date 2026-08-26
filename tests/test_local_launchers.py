from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _read(name: str) -> str:
    return (ROOT / name).read_text(encoding="utf-8-sig")


def test_run_py_reports_v08_and_binds_backend_to_loopback_only() -> None:
    text = _read("run.py")

    assert "AI Manga Studio v0.8" in text
    assert '"--host", "127.0.0.1"' in text
    assert '"--host", "0.0.0.0"' not in text


def test_run_bat_prefers_built_frontend_before_starting_dev_server() -> None:
    text = _read("run.bat")

    dist_gate = 'if exist "frontend\\dist\\index.html" goto :frontend_dist'
    dev_gate = 'if exist "frontend\\package.json" goto :frontend_dev'

    assert dist_gate in text
    assert dev_gate in text
    assert text.index(dist_gate) < text.index(dev_gate)


def test_setup_bat_fails_closed_for_core_install_and_build_errors() -> None:
    text = _read("setup.bat")

    assert "python -m pip install -r requirements.txt" in text
    assert "if errorlevel 1 goto :setup_failed" in text
    assert "\n:setup_failed\n" in text
    assert "exit /b 1" in text

    success = "echo  Setup complete!"
    failure_label = "\n:setup_failed\n"
    assert success in text
    assert text.index(success) < text.index(failure_label)


def test_setup_bat_uses_reproducible_frontend_install_and_real_commands() -> None:
    text = _read("setup.bat")

    assert 'if exist "package-lock.json"' in text
    assert "call npm ci" in text
    assert "call npm install" in text
    assert "python -m backend.cli diagnose" in text
    assert "python -m backend.cli generate -i novel.txt -o output.mp4" in text
    assert "python tools\\h3_unified_live_gate.py" in text
    assert "run.bat diagnose" not in text
    assert "run.bat generate" not in text
