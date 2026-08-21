"""Local desktop capability handoff, deliberately outside HTTP responses."""
from __future__ import annotations

import os
import secrets
import stat
import subprocess
from pathlib import Path


CAPABILITY_FILENAME = "novel-video-capability"


def _is_reparse_or_link(path: Path) -> bool:
    try:
        info = path.lstat()
    except FileNotFoundError:
        return False
    if stat.S_ISLNK(info.st_mode):
        return True
    return bool(getattr(info, "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0))


def _safe_runtime_root(runtime_root: Path) -> Path:
    runtime_root.mkdir(parents=True, exist_ok=True)
    if _is_reparse_or_link(runtime_root) or not runtime_root.is_dir():
        raise RuntimeError("unsafe capability runtime directory")
    return runtime_root.resolve(strict=True)


def _secure_windows_acl(path: Path) -> None:
    """Tighten the temporary file before it becomes discoverable as final."""
    username = os.environ.get("USERNAME", "")
    if not username:
        raise RuntimeError("could not identify the local capability owner")
    try:
        result = subprocess.run(
            ["icacls", str(path), "/inheritance:r", "/grant:r", f"{username}:(R,W,D)"],
            check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise RuntimeError("could not secure local capability handoff") from exc
    if result.returncode != 0:
        raise RuntimeError("could not secure local capability handoff")


def _write_all(descriptor: int, value: bytes) -> None:
    offset = 0
    while offset < len(value):
        written = os.write(descriptor, value[offset:])
        if written <= 0:
            raise OSError("capability write did not advance")
        offset += written


def _remove_owned_regular(path: Path) -> None:
    """Remove only a regular inode in the capability directory; never follow a link."""
    try:
        info = path.lstat()
    except FileNotFoundError:
        return
    if _is_reparse_or_link(path) or not stat.S_ISREG(info.st_mode):
        raise RuntimeError("unsafe existing capability file")
    path.unlink()


def write_desktop_capability(runtime_root: Path, capability: str) -> Path:
    """Write a private launcher-to-UI handoff file without logging its value.

    The launcher passes the same value in the backend and UI process
    environments.  This file is a recovery/diagnostic handoff for a local
    desktop launcher only; it is never served by FastAPI or included in an API
    response.  POSIX permissions are exact and Windows ACL tightening is best
    effort for installations where ``icacls`` is available.
    """
    runtime_root = _safe_runtime_root(runtime_root)
    path = runtime_root / CAPABILITY_FILENAME
    # Do not write through a predictable name.  The temporary inode is private
    # and is hard-linked into the final name only after its bytes and ACL are
    # durable.  ``link`` also refuses to replace a concurrently-created final.
    if path.exists() or _is_reparse_or_link(path):
        _remove_owned_regular(path)
    flags = (os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
             | getattr(os, "O_BINARY", 0))
    temporary = runtime_root / f".{CAPABILITY_FILENAME}.{secrets.token_hex(16)}.tmp"
    descriptor = os.open(str(temporary), flags, 0o600)
    try:
        _write_all(descriptor, capability.encode("utf-8"))
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    try:
        temporary.chmod(stat.S_IRUSR | stat.S_IWUSR)
        if _is_reparse_or_link(temporary):
            raise RuntimeError("unsafe capability temporary file")
        if os.name == "nt":
            _secure_windows_acl(temporary)
        elif temporary.stat().st_mode & 0o077:
            raise RuntimeError("could not secure local capability handoff")
        # A last lstat catches an attacker that created the predictable name
        # while this process was preparing its private inode.
        if path.exists() or _is_reparse_or_link(path):
            raise RuntimeError("unsafe existing capability file")
        os.link(temporary, path)
        if _is_reparse_or_link(path) or not path.is_file():
            raise RuntimeError("unsafe published capability file")
    except OSError as exc:
        if path.exists() and not _is_reparse_or_link(path):
            _remove_owned_regular(path)
        raise RuntimeError("could not secure local capability handoff") from exc
    except Exception as exc:
        # A failure before publication must not leak the new secret.  A final
        # reparse point is deliberately left alone so its target is untouched.
        if path.exists() and not _is_reparse_or_link(path):
            _remove_owned_regular(path)
        if isinstance(exc, RuntimeError) and "secure" in str(exc):
            raise
        raise RuntimeError("could not secure local capability handoff") from exc
    finally:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass
    return path


def remove_desktop_capability(path: Path | None) -> None:
    if path is not None:
        try:
            _remove_owned_regular(path)
        except RuntimeError:
            # Shutdown must never follow or remove an attacker-owned link.
            return
