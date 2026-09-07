"""Windows-only Siemens adapter. No UI automation, shell execution or online PLC APIs."""
from __future__ import annotations

import os
from pathlib import Path
import queue
import struct
import sys
from types import SimpleNamespace
from urllib.parse import quote

from .content import redact_diagnostic
from .errors import BridgeError, public_error
from .paths import check_no_links, local_root


def load_api(api_dir: str, version: int):
    if sys.platform != "win32" or struct.calcsize("P") != 8:
        raise BridgeError("WINDOWS_REQUIRED", "Real Openness requires native 64-bit Windows Python with TIA installed.")
    directory = local_root(api_dir)
    dll = directory / "Siemens.Engineering.dll"
    check_no_links(dll)
    if not dll.is_file():
        raise BridgeError("SDK_MISSING", "Install matching TIA Openness and set --tia-api-dir to its PublicAPI directory.")
    try:
        from pythonnet import load
        load("netfx")  # TIA V19/V20 use .NET Framework, not CoreCLR.
        import clr
        from System import Console, AppDomain
        from System.IO import FileInfo, TextWriter
        from System.Reflection import Assembly, AssemblyName
        from System.Threading import Thread, ThreadStart, ApartmentState

        identity = AssemblyName.GetAssemblyName(str(dll))
        if str(identity.Name) != "Siemens.Engineering" or int(identity.Version.Major) != version:
            raise BridgeError("SDK_VERSION", "Siemens DLL identity/version does not match --tia-version.")

        # Resolve only Siemens assemblies from the explicitly configured local SDK folder.
        def resolver(sender, args):
            name = str(AssemblyName(args.Name).Name)
            if not name.startswith("Siemens.Engineering") or any(c in name for c in "/\\:"):
                return None
            candidate = directory / (name + ".dll")
            check_no_links(candidate)
            return Assembly.LoadFrom(str(candidate)) if candidate.is_file() else None

        AppDomain.CurrentDomain.AssemblyResolve += resolver
        clr.AddReference(str(dll))
        from Siemens.Engineering import TiaPortal, TiaPortalMode, IEngineeringServiceProvider, ExportOptions, ImportOptions
        from Siemens.Engineering.HW.Features import SoftwareContainer
        from Siemens.Engineering.SW import PlcSoftware
        from Siemens.Engineering.Compiler import ICompilable
        from Siemens.Engineering.Online import OnlineProvider
        Console.SetOut(TextWriter.Null)  # stdout belongs exclusively to MCP.
        return SimpleNamespace(**{k: v for k, v in locals().items() if k in {
            "TiaPortal", "TiaPortalMode", "IEngineeringServiceProvider", "ExportOptions",
            "ImportOptions", "SoftwareContainer", "PlcSoftware", "ICompilable", "OnlineProvider",
            "FileInfo", "Thread", "ThreadStart", "ApartmentState", "resolver"}})
    except BridgeError:
        raise
    except ImportError:
        raise BridgeError("RUNTIME_MISSING", "Install this package with the windows extra and .NET Framework 4.8.") from None
    except Exception:
        raise BridgeError("SDK_LOAD_FAILED", "Unable to load the configured Siemens SDK. Check matching TIA/Openness versions.") from None


class OpennessSession:
    """All instances and methods live on one STA worker. Injectable API enables contract tests."""
    def __init__(self, api):
        self.api = api
        self.portal = None
        self.project = None
        self.plcs = {}

    def service(self, obj, kind):
        return self.api.IEngineeringServiceProvider(obj).GetService[kind]()

    def open_project(self, path: str) -> dict:
        if self.portal is not None:
            raise BridgeError("PROJECT_ALREADY_OPEN", "An Openness session is already active.")
        self.portal = self.api.TiaPortal(self.api.TiaPortalMode.WithUserInterface)
        try:
            self.project = self.portal.Projects.Open(self.api.FileInfo(path))
            self._index_plcs()
        except Exception:
            self.dispose()
            raise
        return {"name": str(self.project.Name), "plc_count": len(self.plcs)}

    def _index_plcs(self):
        self.plcs = {}

        def items(collection, prefix):
            for item in collection:
                path = prefix + "/" + quote(str(item.Name), safe="")
                container = self.service(item, self.api.SoftwareContainer)
                if container is not None and isinstance(container.Software, self.api.PlcSoftware):
                    self.plcs[path] = container.Software
                items(item.DeviceItems, path)

        def devices(collection, prefix):
            for device in collection:
                items(device.DeviceItems, prefix + "/" + quote(str(device.Name), safe=""))

        def groups(collection, prefix):
            for group in collection:
                path = prefix + "/" + quote(str(group.Name), safe="")
                devices(group.Devices, path)
                groups(group.Groups, path)

        devices(self.project.Devices, "devices")
        devices(self.project.UngroupedDevicesGroup.Devices, "ungrouped")
        groups(self.project.DeviceGroups, "groups")

    def plc(self, plc_id):
        if plc_id not in self.plcs:
            raise BridgeError("PLC_NOT_FOUND", "Use a plc_id returned by list_plcs for this session.")
        return self.plcs[plc_id]

    def require_offline(self):
        for plc in self.plcs.values():
            online = self.service(plc, self.api.OnlineProvider)
            if online is None:
                raise BridgeError("OFFLINE_UNVERIFIED", "Could not verify offline status; operation refused.")
            if online.IsOnline:
                raise BridgeError("PLC_ONLINE", "Set all project PLCs offline in TIA before this operation.")

    def list_plcs(self):
        return {"plcs": [{"plc_id": k, "name": str(v.Name)} for k, v in self.plcs.items()]}

    def blocks(self, group, prefix=""):
        for block in group.Blocks:
            yield prefix + quote(str(block.Name), safe=""), block
        for child in group.Groups:
            yield from self.blocks(child, prefix + quote(str(child.Name), safe="") + "/")

    def list_blocks(self, plc_id):
        rows = []
        for key, block in self.blocks(self.plc(plc_id).BlockGroup):
            rows.append({"block_id": key, "name": str(block.Name), "number": int(block.Number),
                         "language": str(block.ProgrammingLanguage), "type": str(block.GetType().Name)})
            if len(rows) > 10000:
                raise BridgeError("RESULT_TOO_LARGE", "Project has too many blocks for this initial bridge.")
        return {"blocks": rows, "scope": "ordinary program blocks and nested user groups"}

    def export_block(self, plc_id, block_id, path):
        block = next((b for k, b in self.blocks(self.plc(plc_id).BlockGroup) if k == block_id), None)
        if block is None:
            raise BridgeError("BLOCK_NOT_FOUND", "Use a block_id returned by list_blocks.")
        block.Export(self.api.FileInfo(path), getattr(self.api.ExportOptions, "None"))
        return {}

    def import_source(self, plc_id, path, allow_replace):
        self.require_offline()
        plc = self.plc(plc_id)
        if Path(path).suffix.lower() == ".scl":
            source = plc.ExternalSourceGroup.ExternalSources.CreateFromFile(Path(path).name, path)
            # Siemens documents this overload as void. Do not iterate its return value.
            source.GenerateBlocksFromSource()
            return {"generated": True, "note": "Source retained in External sources; compile and inspect the working copy."}
        options = self.api.ImportOptions.Override if allow_replace else getattr(self.api.ImportOptions, "None")
        blocks = plc.BlockGroup.Blocks.Import(self.api.FileInfo(path), options)
        return {"imported_blocks": [str(b.Name) for b in blocks], "target_group": "root"}

    def compile_plc(self, plc_id):
        self.require_offline()
        compiler = self.service(self.plc(plc_id), self.api.ICompilable)
        if compiler is None:
            raise BridgeError("COMPILE_UNAVAILABLE", "This PLC does not expose ICompilable.")
        result = compiler.Compile()
        messages = []
        truncated = False

        def collect(items, depth=0):
            nonlocal truncated
            for message in items:
                if len(messages) >= 300 or depth > 32:
                    truncated = True
                    return
                messages.append({"state": str(message.State),
                                 "description": redact_diagnostic(message.Description),
                                 "errors": int(message.ErrorCount), "warnings": int(message.WarningCount)})
                collect(message.Messages, depth + 1)

        collect(result.Messages)
        return {"state": str(result.State), "errors": int(result.ErrorCount),
                "warnings": int(result.WarningCount), "messages": messages,
                "messages_truncated": truncated, "saved": False}

    def save_project(self):
        self.require_offline()
        self.project.Save()
        return {}

    def dispose(self):
        if self.portal is not None:
            self.portal.Dispose()  # Disconnect only; GUI and unsaved project can remain for inspection.
        self.portal = None
        self.project = None
        self.plcs = {}


class OpennessBackend:
    name = "siemens-openness"
    simulated = False

    def __init__(self, api_dir, version, timeout=240):
        self.api_dir, self.version, self.timeout = api_dir, version, timeout
        self.loaded = False
        self.poisoned = False
        self.queue = queue.Queue()
        self.thread = None
        self.api = None

    def _run(self):
        session = OpennessSession(self.api)
        try:
            while True:
                task = self.queue.get()
                if task is None:
                    return
                name, args, reply = task
                try:
                    reply.put((True, getattr(session, name)(*args)))
                except Exception as exc:
                    error = public_error(exc)
                    reply.put((False, error))
        finally:
            try:
                session.dispose()
            except Exception:
                pass

    def call(self, name, *args):
        if name not in {"open_project", "list_plcs", "list_blocks", "export_block", "import_source", "compile_plc", "save_project"}:
            raise BridgeError("UNKNOWN_OPERATION", "Backend operation is not exposed.")
        if self.poisoned:
            raise BridgeError("SESSION_UNCERTAIN", "Previous call timed out. Inspect TIA before restarting; do not automatically retry writes.")
        if not self.loaded:
            self.api = load_api(self.api_dir, self.version)
            self.thread = self.api.Thread(self.api.ThreadStart(self._run))
            self.thread.SetApartmentState(self.api.ApartmentState.STA)
            self.thread.IsBackground = True
            self.thread.Start()
            self.loaded = True
        reply = queue.Queue(maxsize=1)
        self.queue.put((name, args, reply))
        try:
            ok, result = reply.get(timeout=self.timeout)
        except queue.Empty:
            self.poisoned = True
            raise BridgeError("OPERATION_TIMEOUT", "TIA call timed out; its result is unknown and may still complete. Inspect TIA, do not retry writes.") from None
        if not ok:
            raise BridgeError(result["code"], result["message"])
        return result

    def close(self):
        if self.loaded:
            self.queue.put(None)
            if not self.poisoned:
                self.thread.Join(3000)
