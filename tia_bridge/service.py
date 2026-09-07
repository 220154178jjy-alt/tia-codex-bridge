from __future__ import annotations

from pathlib import Path
import re
import uuid

from .content import validate_source
from .errors import BridgeError
from .paths import check_no_links, copy_project, digest, limited_read, relative_file


class Bridge:
    def __init__(self, backend, project_root: Path, workspace: Path, *, version: int = 20,
                 allow_writes: bool = False):
        if project_root == workspace or project_root.is_relative_to(workspace) or workspace.is_relative_to(project_root):
            raise BridgeError("INVALID_ROOT", "Project root and workspace must be separate, non-nested directories.")
        self.backend = backend
        self.project_root = project_root
        self.workspace = workspace
        self.version = version
        self.allow_writes = allow_writes
        self.project = None
        self.project_path = None
        self.dirty = False

    def _write(self):
        if not self.allow_writes:
            raise BridgeError("READ_ONLY", "Restart the bridge with --allow-writes to modify the working copy.")

    def _project(self):
        if self.project is None:
            raise BridgeError("NO_PROJECT", "Open a project copy first.")

    def _artifact_dir(self, area: str) -> Path:
        folder = self.workspace / area
        check_no_links(folder)
        folder.mkdir(exist_ok=True)
        return folder

    def status(self) -> dict:
        return {"backend": self.backend.name, "simulated": self.backend.simulated,
                "tia_api_version": self.version, "allow_writes": self.allow_writes,
                "project_open": self.project is not None, "dirty": self.dirty,
                "working_project": self.project_path,
                "transport": "stdio", "online_operations": False,
                "session_uncertain": getattr(self.backend, "poisoned", False),
                "runtime_loaded": self.backend.loaded}

    def open_project(self, project: str) -> dict:
        if self.project is not None:
            raise BridgeError("PROJECT_ALREADY_OPEN", "One project per bridge process. Save as needed before restarting.")
        source = relative_file(self.project_root, project, suffixes={f".ap{self.version}"})
        target = copy_project(source, self.project_root, self.workspace)
        result = self.backend.call("open_project", str(target))
        self.project = True
        self.project_path = target.relative_to(self.workspace).as_posix()
        return {"working_project": self.project_path, "original_unchanged": True, **result}

    def list_plcs(self) -> dict:
        self._project()
        return self.backend.call("list_plcs")

    def list_blocks(self, plc_id: str) -> dict:
        self._project()
        return self.backend.call("list_blocks", plc_id)

    def export_block(self, plc_id: str, block_id: str) -> dict:
        self._project()
        target = self._artifact_dir("artifacts") / (uuid.uuid4().hex + ".xml")
        self.backend.call("export_block", plc_id, block_id, str(target))
        data = limited_read(target)
        return {"file": target.relative_to(self.workspace).as_posix(), "sha256": digest(data), "bytes": len(data)}

    def read_artifact(self, file: str) -> dict:
        # Only explicitly staged input/output text, never arbitrary session/configuration files.
        normal = file.replace("\\", "/")
        if normal.split("/")[0] not in {"artifacts", "staging"}:
            raise BridgeError("UNSAFE_PATH", "Read only files inside workspace artifacts/ or staging/.")
        path = relative_file(self.workspace, file, suffixes={".xml", ".scl"})
        data = limited_read(path)
        try:
            content = data.decode("utf-8-sig")
        except UnicodeError:
            raise BridgeError("UNSUPPORTED_ENCODING", "Use UTF-8 XML or ASCII SCL.") from None
        return {"file": normal, "sha256": digest(data), "content": content}

    def import_source(self, plc_id: str, file: str, expected_sha256: str,
                      allow_replace: bool = False) -> dict:
        self._write()
        self._project()
        if not re.fullmatch(r"[0-9a-f]{64}", expected_sha256):
            raise BridgeError("INVALID_HASH", "Expected a lowercase SHA-256 from read_artifact.")
        if file.replace("\\", "/").split("/")[0] != "staging":
            raise BridgeError("UNSAFE_PATH", "Import only a reviewed source placed in workspace staging/.")
        path = relative_file(self.workspace, file, suffixes={".xml", ".scl"})
        data = limited_read(path)
        if digest(data) != expected_sha256:
            raise BridgeError("SOURCE_CHANGED", "Source differs from the reviewed hash. Read and review it again.")
        validate_source(data, path.suffix.lower())
        if path.suffix.lower() == ".scl" and not allow_replace:
            raise BridgeError("REPLACE_ACK_REQUIRED", "SCL generation can overwrite named blocks/types; set allow_replace=true.")
        # Pin exactly the reviewed bytes under an unpredictable new path, avoiding a later file reread race.
        pinned = self._artifact_dir("imports") / (uuid.uuid4().hex + path.suffix.lower())
        with pinned.open("xb") as stream:
            stream.write(data)
        self.dirty = True  # A failed Siemens call may already have partially changed the project.
        result = self.backend.call("import_source", plc_id, str(pinned), allow_replace)
        return {"sha256": expected_sha256, "saved": False, "dirty": True, **result}

    def compile_plc(self, plc_id: str) -> dict:
        self._write()  # Compiling can change offline engineering data.
        self._project()
        self.dirty = True
        return self.backend.call("compile_plc", plc_id)

    def save_project(self) -> dict:
        self._write()
        self._project()
        self.backend.call("save_project")
        self.dirty = False
        return {"saved": True, "working_project": self.project_path, "original_unchanged": True}

    def close(self):
        self.backend.close()  # Never implicitly saves or overwrites the source project.
