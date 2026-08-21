import errno
import os
import tempfile
from hashlib import sha256
from pathlib import Path


class AtomicAssetStore:
    def publish(self, temp_path: Path, final_path: Path) -> tuple[Path, str]:
        if not temp_path.is_file() or temp_path.stat().st_size == 0:
            raise ValueError("asset temp file is missing or empty")
        final_path.parent.mkdir(parents=True, exist_ok=True)
        if final_path.exists():
            temp_path.unlink(missing_ok=True)
            raise FileExistsError(f"asset destination already exists: {final_path}")
        digest = sha256()
        with temp_path.open("rb") as source:
            for chunk in iter(lambda: source.read(1024 * 1024), b""):
                digest.update(chunk)
        # A hard link is an atomic no-overwrite publication primitive on the
        # filesystems used for project assets.  Unlike replace/rename, it can
        # never replace a winner that appeared after the existence check.
        try:
            os.link(temp_path, final_path)
        except FileExistsError:
            temp_path.unlink(missing_ok=True)
            raise FileExistsError(f"asset destination already exists: {final_path}") from None
        except OSError as exc:
            if exc.errno not in {errno.EXDEV, errno.EPERM, errno.EOPNOTSUPP, errno.EINVAL}:
                temp_path.unlink(missing_ok=True)
                raise
            # Cross-device callers first get a fully-written, fsync'd stage in
            # the destination directory.  Publishing that local file by hard
            # link means no reader can ever observe a partially copied final.
            stage_path: Path | None = None
            try:
                with tempfile.NamedTemporaryFile(
                    mode="wb", prefix=".asset-stage-", dir=final_path.parent,
                    delete=False,
                ) as stage, temp_path.open("rb") as source:
                    stage_path = Path(stage.name)
                    staged_digest = sha256()
                    for chunk in iter(lambda: source.read(1024 * 1024), b""):
                        staged_digest.update(chunk)
                        stage.write(chunk)
                    stage.flush()
                    os.fsync(stage.fileno())
                if staged_digest.hexdigest() != digest.hexdigest():
                    raise ValueError("asset temp file changed while being staged")
                os.link(stage_path, final_path)
            except FileExistsError:
                raise FileExistsError(f"asset destination already exists: {final_path}") from None
            finally:
                if stage_path is not None:
                    stage_path.unlink(missing_ok=True)
                # A failed publish has no usable caller temp to retry: exact
                # completed staging is either published or discarded.
                temp_path.unlink(missing_ok=True)
            if not final_path.exists():
                # Defensive: an unsupported local link must not silently fall
                # back to writing visible final bytes.
                raise RuntimeError("local staged asset was not atomically published")
            return final_path, digest.hexdigest()
        temp_path.unlink(missing_ok=True)
        return final_path, digest.hexdigest()
