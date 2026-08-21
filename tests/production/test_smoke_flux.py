import os
import subprocess
import sys
from pathlib import Path


def test_direct_smoke_script_reports_missing_flux2_model_before_queueing(
    tmp_path: Path,
):
    root = Path(__file__).resolve().parents[2]
    env = os.environ.copy()
    env["FLUX2_MODEL_DIR"] = str(tmp_path)

    result = subprocess.run(
        [sys.executable, str(root / "scripts" / "smoke_flux.py")],
        cwd=root,
        env=env,
        capture_output=True,
        text=True,
        check=False,
        timeout=10,
    )

    assert result.returncode != 0
    assert "flux-2-klein-4b-fp8.safetensors" in result.stderr
    assert str(tmp_path) in result.stderr
