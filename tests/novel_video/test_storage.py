from hashlib import sha256
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

import pytest

from backend.novel_video.storage import AtomicAssetStore


def test_publish_creates_parent_moves_file_and_returns_exact_digest(tmp_path: Path):
    temp_path = tmp_path / "render.tmp"
    final_path = tmp_path / "published" / "take.mp4"
    payload = b"rendered-video-bytes"
    temp_path.write_bytes(payload)

    published_path, digest = AtomicAssetStore().publish(temp_path, final_path)

    assert published_path == final_path
    assert digest == sha256(payload).hexdigest()
    assert final_path.read_bytes() == payload
    assert not temp_path.exists()


def test_publish_rejects_existing_destination_without_changing_either_file(tmp_path: Path):
    temp_path = tmp_path / "render.tmp"
    final_path = tmp_path / "published" / "take.mp4"
    final_path.parent.mkdir(parents=True)
    temp_path.write_bytes(b"new-render")
    final_path.write_bytes(b"approved-render")

    with pytest.raises(FileExistsError, match="already exists"):
        AtomicAssetStore().publish(temp_path, final_path)

    assert final_path.read_bytes() == b"approved-render"
    assert not temp_path.exists()


def test_publish_hashes_by_streaming_without_path_read_bytes(tmp_path: Path, monkeypatch):
    temp_path = tmp_path / "render.tmp"
    final_path = tmp_path / "take.mp4"
    payload = b"stream-me" * 1024
    temp_path.write_bytes(payload)

    def fail_read_bytes(self):
        raise AssertionError("Path.read_bytes must not be used for large assets")

    monkeypatch.setattr(Path, "read_bytes", fail_read_bytes)

    published_path, digest = AtomicAssetStore().publish(temp_path, final_path)

    assert published_path == final_path
    assert digest == sha256(payload).hexdigest()


@pytest.mark.parametrize("contents", [None, b""])
def test_publish_rejects_missing_or_empty_temp_files(tmp_path: Path, contents: bytes | None):
    temp_path = tmp_path / "render.tmp"
    if contents is not None:
        temp_path.write_bytes(contents)

    with pytest.raises(ValueError, match="asset temp file is missing or empty"):
        AtomicAssetStore().publish(temp_path, tmp_path / "take.mp4")


def test_simultaneous_publish_has_one_winner_and_never_overwrites_final(tmp_path: Path):
    final_path = tmp_path / "published" / "take.mp4"
    first, second = tmp_path / "one.tmp", tmp_path / "two.tmp"
    first.write_bytes(b"first-writer")
    second.write_bytes(b"second-writer")

    def publish(path: Path):
        try:
            return AtomicAssetStore().publish(path, final_path)
        except FileExistsError:
            return None

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(publish, [first, second]))

    winner = next(result for result in results if result is not None)
    assert sum(result is not None for result in results) == 1
    assert final_path.read_bytes() in {b"first-writer", b"second-writer"}
    assert winner[1] == sha256(final_path.read_bytes()).hexdigest()
    assert not first.exists()
    assert not second.exists()


def test_cross_device_link_fallback_stages_complete_bytes_then_publishes_atomically(tmp_path: Path, monkeypatch):
    temp_path = tmp_path / "other-volume.tmp"
    final_path = tmp_path / "published" / "take.mp4"
    payload = b"complete-cross-device-render" * 4096
    temp_path.write_bytes(payload)
    original_link = os.link
    calls: list[tuple[Path, Path]] = []

    def exdev_then_link(source, destination):
        calls.append((Path(source), Path(destination)))
        if len(calls) == 1:
            raise OSError(errno.EXDEV, "cross-device link")
        assert not final_path.exists()
        assert Path(source).parent == final_path.parent
        assert Path(source).read_bytes() == payload
        return original_link(source, destination)

    monkeypatch.setattr(os, "link", exdev_then_link)

    published, digest = AtomicAssetStore().publish(temp_path, final_path)

    assert published == final_path
    assert digest == sha256(payload).hexdigest()
    assert final_path.read_bytes() == payload
    assert len(calls) == 2
    assert not temp_path.exists()
    assert not list(final_path.parent.glob(".asset-stage-*"))
import errno
import os
