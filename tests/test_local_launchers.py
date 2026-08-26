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
    assert "verify_release.bat" in text
    assert "verify_release.bat preflight" in text
    assert "verify_release.bat full" in text
    assert "verify_h3.bat preflight" in text
    assert "verify_h3.bat" in text
    assert "run.bat diagnose" not in text
    assert "run.bat generate" not in text


def test_verify_h3_bat_runs_preflight_before_smoke_and_fails_closed() -> None:
    text = _read("verify_h3.bat")

    preflight = "python tools\\h3_unified_live_gate.py"
    smoke = (
        "python tools\\h3_unified_live_gate.py --submit --mode T2VA "
        "--duration 5 --resolution 480p --aspect-ratio 9:16 --steps 12"
    )

    assert preflight in text
    assert smoke in text
    assert text.index(preflight) < text.index(smoke)
    assert "if errorlevel 1 goto :verify_failed" in text
    assert "exit /b 1" in text
    assert "storage\\live\\h3_unified_live_gate.json" in text


def test_verify_h3_bat_supports_preflight_only_mode() -> None:
    text = _read("verify_h3.bat")

    assert 'if /I "%~1"=="preflight" goto :verify_passed' in text
    assert "verify_h3.bat preflight" in text
    assert "verify_h3.bat" in text


def test_verify_release_bat_runs_code_gates_before_optional_hardware() -> None:
    text = _read("verify_release.bat")

    launcher = "python -m pytest -q tests/test_local_launchers.py"
    h3 = "python -m pytest -q tests/video/test_h3_unified.py"
    frontend = "call npm run typecheck"
    hardware = "call verify_h3.bat"

    assert launcher in text
    assert h3 in text
    assert frontend in text
    assert "call npm test -- --run" in text
    assert "call npm run build" in text
    assert text.index(launcher) < text.index(h3) < text.index(frontend) < text.index(hardware)
    assert "if errorlevel 1 goto :release_failed" in text
    assert "exit /b 1" in text


def test_verify_release_bat_defaults_to_safe_code_only_and_has_explicit_modes() -> None:
    text = _read("verify_release.bat")

    assert 'if /I "%~1"=="full" goto :hardware_full' in text
    assert 'if /I "%~1"=="preflight" goto :hardware_preflight' in text
    assert 'if "%~1"=="" goto :release_passed' in text
    assert "call verify_h3.bat preflight" in text
    assert "call verify_h3.bat" in text
    assert "verify_release.bat full" in text
    assert "verify_release.bat preflight" in text


def test_verify_release_bat_calls_npm_probe_and_does_not_exit_into_npm_cmd() -> None:
    text = _read("verify_release.bat")

    assert "call npm --version >nul 2>&1" in text
    assert "\nnpm --version >nul 2>&1\n" not in text
