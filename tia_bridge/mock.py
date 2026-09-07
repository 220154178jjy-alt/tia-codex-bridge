"""Explicit protocol demo. Never claims to compile or simulate a Siemens PLC."""
from pathlib import Path

from .errors import BridgeError


class MockBackend:
    name = "mock"
    simulated = True
    loaded = True

    def __init__(self):
        self.calls = []

    def call(self, name, *args):
        self.calls.append((name, args))
        if name == "open_project":
            return {"name": "MOCK project", "plc_count": 1}
        if name == "list_plcs":
            return {"plcs": [{"plc_id": "mock/plc", "name": "MOCK PLC"}]}
        if name in {"list_blocks", "export_block", "import_source", "compile_plc"} and args[0] != "mock/plc":
            raise BridgeError("PLC_NOT_FOUND", "Unknown mock PLC ID.")
        if name == "list_blocks":
            return {"blocks": [{"block_id": "MockBlock", "name": "MockBlock", "language": "SCL", "number": 1}]}
        if name == "export_block":
            if args[1] != "MockBlock":
                raise BridgeError("BLOCK_NOT_FOUND", "Unknown mock block ID.")
            Path(args[2]).write_text('<Document><SW.Blocks.FC ID="0"><AttributeList><Name>MockBlock</Name></AttributeList></SW.Blocks.FC></Document>', encoding="utf-8")
            return {"note": "MOCK XML only, not a valid TIA round-trip fixture"}
        if name == "import_source":
            return {"accepted_by_mock": True, "note": "No Siemens import or validation occurred."}
        if name == "compile_plc":
            return {"state": "MOCK_NOT_COMPILED", "errors": None, "warnings": None,
                    "messages": [], "note": "Mock backend does not validate or execute PLC code."}
        if name == "save_project":
            return {}
        raise BridgeError("UNKNOWN_OPERATION", "Unknown mock operation.")

    def close(self):
        pass
