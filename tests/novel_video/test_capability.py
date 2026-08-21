from __future__ import annotations

from pathlib import Path

import pytest

from backend.novel_video.capability import CAPABILITY_FILENAME, write_desktop_capability


def test_capability_refuses_precreated_symlink_without_touching_target(tmp_path: Path) -> None:
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    outside = tmp_path / "outside-secret"
    outside.write_text("outside remains private", encoding="utf-8")
    target = runtime / CAPABILITY_FILENAME
    try:
        target.symlink_to(outside)
    except OSError:
        pytest.skip("symlink creation is unavailable on this Windows test host")

    with pytest.raises(RuntimeError, match="unsafe"):
        write_desktop_capability(runtime, "new-secret")

    assert outside.read_text(encoding="utf-8") == "outside remains private"
    assert target.is_symlink()


def test_capability_acl_failure_removes_private_temp_without_publishing(tmp_path: Path, monkeypatch) -> None:
    import backend.novel_video.capability as capability

    runtime = tmp_path / "runtime"
    monkeypatch.setattr(capability, "_secure_windows_acl", lambda _path: (_ for _ in ()).throw(RuntimeError("acl")))

    with pytest.raises(RuntimeError, match="secure"):
        write_desktop_capability(runtime, "test-secret")

    assert not (runtime / CAPABILITY_FILENAME).exists()
    assert not list(runtime.glob(".novel-video-capability.*.tmp"))
