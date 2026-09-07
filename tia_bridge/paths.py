from __future__ import annotations

import hashlib
import os
from pathlib import Path, PureWindowsPath
import re
import shutil
import stat
import uuid

from .errors import BridgeError

MAX_SOURCE_BYTES = 2 * 1024 * 1024
MAX_PROJECT_BYTES = 2 * 1024 * 1024 * 1024
MAX_PROJECT_ENTRIES = 20000
RESERVED = {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)),
            *(f"LPT{i}" for i in range(1, 10))}


def check_no_links(path: Path) -> None:
    for part in (path, *path.parents):
        if not os.path.lexists(part):
            continue
        info = part.lstat()
        if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
            raise BridgeError("UNSAFE_PATH", "Symbolic links and Windows reparse points are not allowed.")


def local_root(value: str, *, create: bool = False) -> Path:
    if value.startswith(("\\\\", "//")) or not Path(value).is_absolute():
        raise BridgeError("INVALID_ROOT", "Use an absolute local directory, not a network or relative path.")
    path = Path(os.path.abspath(value))
    check_no_links(path)
    if create:
        path.mkdir(parents=True, exist_ok=True)
    if not path.is_dir():
        raise BridgeError("INVALID_ROOT", "Configured directory does not exist.")
    if os.name == "nt":
        import ctypes
        drive_type = ctypes.windll.kernel32.GetDriveTypeW(str(path.anchor))
        if drive_type != 3:  # DRIVE_FIXED; rejects mapped network drives too.
            raise BridgeError("INVALID_ROOT", "Use a fixed local Windows drive.")
    return path


def relative_file(root: Path, value: str, *, suffixes: set[str] | None = None) -> Path:
    if not isinstance(value, str) or not value or len(value) > 512:
        raise BridgeError("UNSAFE_PATH", "Expected a nonempty relative file path.")
    parts = value.replace("\\", "/").split("/")
    if PureWindowsPath(value).drive or value.startswith(("/", "\\")) or any(
        p in {"", ".", ".."} or p[-1:] in {" ", "."} or
        p.split(".")[0].upper() in RESERVED or
        re.search(r'[\x00-\x1f<>:"|?*]', p) for p in parts
    ):
        raise BridgeError("UNSAFE_PATH", "Path traversal, device paths, and special path characters are forbidden.")
    path = root.joinpath(*parts)
    check_no_links(path)
    if not path.resolve().is_relative_to(root.resolve()):
        raise BridgeError("UNSAFE_PATH", "File must remain inside its configured root.")
    if suffixes and path.suffix.lower() not in suffixes:
        raise BridgeError("UNSUPPORTED_FILE", "This file extension is not supported by this operation.")
    return path


def limited_read(path: Path) -> bytes:
    if not path.is_file():
        raise BridgeError("FILE_NOT_FOUND", "Requested local file does not exist.")
    check_no_links(path)
    with path.open("rb") as stream:
        data = stream.read(MAX_SOURCE_BYTES + 1)
    if len(data) > MAX_SOURCE_BYTES:
        raise BridgeError("FILE_TOO_LARGE", "Source and artifact files must not exceed 2 MiB.")
    return data


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def inventory(folder: Path) -> dict:
    result = {}
    total = 0
    for base, dirs, files in os.walk(folder, followlinks=False):
        for name in dirs + files:
            path = Path(base) / name
            check_no_links(path)
            info = path.stat()
            if not stat.S_ISREG(info.st_mode) and not stat.S_ISDIR(info.st_mode):
                raise BridgeError("UNSAFE_PROJECT", "Project folder contains a special file.")
            if path.is_file():
                total += info.st_size
            result[path.relative_to(folder).as_posix()] = (info.st_size, info.st_mtime_ns)
            if total > MAX_PROJECT_BYTES or len(result) > MAX_PROJECT_ENTRIES:
                raise BridgeError("PROJECT_TOO_LARGE", "Project exceeds the 2 GiB / 20,000-entry copy limit.")
    return result


def copy_project(project: Path, project_root: Path, workspace: Path) -> Path:
    if not project.is_file() or project.parent == project_root:
        raise BridgeError("PROJECT_LAYOUT", "Use a closed project in its own subfolder, e.g. Demo/Demo.ap20.")
    before = inventory(project.parent)
    sessions = workspace / "sessions"
    check_no_links(sessions)
    sessions.mkdir(exist_ok=True)
    target = sessions / uuid.uuid4().hex
    try:
        # Each open starts a new copy. The source project is never passed to Openness.
        shutil.copytree(project.parent, target, symlinks=True)
        inventory(target)  # Also reject a link substituted during the copy.
        if before != inventory(project.parent):
            raise BridgeError("PROJECT_CHANGED", "Source changed during copy. Close TIA and retry with a stable project.")
        return target / project.name
    except Exception:
        shutil.rmtree(target, ignore_errors=True)
        raise
