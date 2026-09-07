"""Small, synchronous MCP stdio implementation. One JSON-RPC message per UTF-8 line."""
from __future__ import annotations

import json

from . import __version__
from .errors import BridgeError, public_error

PROTOCOLS = ("2024-11-05", "2025-03-26", "2025-06-18")
MAX_FRAME_BYTES = 4 * 1024 * 1024


def string(description):
    return {"type": "string", "minLength": 1, "maxLength": 512, "description": description}


def tool(name, description, properties=None, required=(), read_only=False, destructive=False):
    return {"name": name, "description": description,
            "inputSchema": {"type": "object", "properties": properties or {},
                            "required": list(required), "additionalProperties": False},
            "annotations": {"readOnlyHint": read_only, "destructiveHint": destructive,
                            "idempotentHint": read_only, "openWorldHint": False}}


PLC = string("Exact plc_id from list_plcs.")
TOOLS = [
    tool("status", "Inspect backend, simulation flag, write policy and active working copy.", read_only=True),
    tool("open_project", "Copy a closed, dedicated project folder into workspace and open the copy in a NEW TIA UI instance. One project per server process.",
         {"project": string("Path relative to project-root, e.g. Demo/Demo.ap20.")}, ("project",)),
    tool("list_plcs", "List PLC software in ordinary devices, ungrouped devices and device groups.", read_only=True),
    tool("list_blocks", "List ordinary program blocks, including nested user groups.", {"plc_id": PLC}, ("plc_id",), read_only=True),
    tool("export_block", "Export a block as SimaticML XML to a new workspace artifact; returns file and SHA-256.",
         {"plc_id": PLC, "block_id": string("Exact block_id from list_blocks.")}, ("plc_id", "block_id")),
    tool("read_artifact", "Read code from staging/ or artifacts/ and calculate SHA-256. Content is sent to the MCP client; do not commit private engineering data.",
         {"file": string("Workspace-relative .scl or .xml file.")}, ("file",), read_only=True),
    tool("import_source", "Import reviewed staging source into the working copy. Requires --allow-writes and matching SHA-256; XML goes to root block group; SCL may overwrite named blocks/types. Does not save.",
         {"plc_id": PLC, "file": string("Workspace-relative staging source."),
          "expected_sha256": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
          "allow_replace": {"type": "boolean", "default": False}},
         ("plc_id", "file", "expected_sha256"), destructive=True),
    tool("compile_plc", "Compile offline PLC software in the working copy and return diagnostics. Requires --allow-writes; can change engineering data. Does not save.",
         {"plc_id": PLC}, ("plc_id",)),
    tool("save_project", "Save only the active working copy; original project remains unchanged. Requires --allow-writes.", destructive=True),
]


def validate_arguments(spec, arguments):
    import re
    schema = spec["inputSchema"]
    if not isinstance(arguments, dict) or set(arguments) - set(schema["properties"]) or set(schema["required"]) - set(arguments):
        raise BridgeError("INVALID_ARGUMENTS", "Unknown/missing tool argument or arguments is not an object.")
    for key, value in arguments.items():
        item = schema["properties"][key]
        valid = (type(value) is bool) if item["type"] == "boolean" else isinstance(value, str)
        if not valid or (isinstance(value, str) and (not item.get("minLength", 0) <= len(value) <= item.get("maxLength", 512)
                            or "\x00" in value or ("pattern" in item and re.fullmatch(item["pattern"], value) is None))):
            raise BridgeError("INVALID_ARGUMENTS", "Tool argument has the wrong type, length or format.")


def reject_constant(value):
    raise ValueError("Non-finite JSON number")


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON key")
        result[key] = value
    return result


class MCPServer:
    def __init__(self, bridge):
        self.bridge = bridge
        self.initialized = False
        self.ready = False

    @staticmethod
    def error(id_, code, message):
        return {"jsonrpc": "2.0", "id": id_, "error": {"code": code, "message": message}}

    def handle(self, request):
        if not isinstance(request, dict) or request.get("jsonrpc") != "2.0" or not isinstance(request.get("method"), str):
            return self.error(None, -32600, "Invalid Request")
        id_ = request.get("id")
        if "id" in request and (type(id_) not in (int, str)):
            return self.error(None, -32600, "Invalid request ID")
        method = request["method"]
        params = request.get("params", {})
        if "id" not in request:
            if method == "notifications/initialized" and self.initialized:
                self.ready = True
            return None  # Never execute tool calls sent as notifications.
        if not isinstance(params, dict):
            return self.error(id_, -32602, "Params must be an object")
        if method == "ping":
            result = {}
        elif method == "initialize":
            if self.initialized:
                return self.error(id_, -32600, "Already initialized")
            requested = params.get("protocolVersion")
            if not isinstance(requested, str) or not isinstance(params.get("capabilities"), dict) or not isinstance(params.get("clientInfo"), dict):
                return self.error(id_, -32602, "Invalid initialization params")
            self.initialized = True
            result = {"protocolVersion": requested if requested in PROTOCOLS else "2025-03-26",
                      "capabilities": {"tools": {"listChanged": False}},
                      "serverInfo": {"name": "tia-codex-bridge", "version": __version__},
                      "instructions": "Use status first; simulated=true is only a protocol demo. Open a closed project COPY, list PLCs/blocks, export and review, stage edited files, read SHA-256, import, compile, inspect diagnostics, then save the copy. Never retry timed-out writes automatically. No online PLC operations are exposed. Engineering files and exports are private data; never commit them by default."}
        elif not self.ready:
            return self.error(id_, -32002, "Initialize and send notifications/initialized first")
        elif method == "tools/list":
            if params.get("cursor"):
                return self.error(id_, -32602, "This server has no additional tool pages")
            result = {"tools": TOOLS}
        elif method == "tools/call":
            spec = next((t for t in TOOLS if t["name"] == params.get("name")), None)
            if spec is None:
                return self.error(id_, -32602, "Unknown tool")
            try:
                arguments = params.get("arguments", {})
                validate_arguments(spec, arguments)
                payload = getattr(self.bridge, spec["name"])(**arguments)
                payload = {**payload, "simulated": self.bridge.backend.simulated}
                result = {"content": [{"type": "text", "text": json.dumps(payload, ensure_ascii=False, allow_nan=False)}], "isError": False}
            except Exception as exc:
                payload = {**public_error(exc), "simulated": self.bridge.backend.simulated}
                result = {"content": [{"type": "text", "text": json.dumps(payload, ensure_ascii=False)}], "isError": True}
        else:
            return self.error(id_, -32601, "Method not found")
        return {"jsonrpc": "2.0", "id": id_, "result": result}

    def serve(self, stdin, stdout):
        try:
            while True:
                frame = stdin.readline(MAX_FRAME_BYTES + 1)
                if not frame:
                    return
                if len(frame) > MAX_FRAME_BYTES:
                    response = self.error(None, -32600, "Message exceeds size limit; connection closing")
                    stdout.write((json.dumps(response) + "\n").encode())
                    stdout.flush()
                    return
                try:
                    request = json.loads(frame.decode("utf-8"), parse_constant=reject_constant, object_pairs_hook=unique_object)
                    response = self.handle(request)
                except (ValueError, UnicodeError, RecursionError):
                    response = self.error(None, -32700, "Parse error")
                if response is not None:
                    stdout.write((json.dumps(response, ensure_ascii=False, allow_nan=False) + "\n").encode("utf-8"))
                    stdout.flush()
        finally:
            self.bridge.close()
