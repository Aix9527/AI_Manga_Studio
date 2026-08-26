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
