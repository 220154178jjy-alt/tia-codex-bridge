import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from tia_bridge.content import validate_source
from tia_bridge.errors import BridgeError
from tia_bridge.mcp import MCPServer, MAX_FRAME_BYTES
from tia_bridge.mock import MockBackend
from tia_bridge.paths import digest, relative_file
from tia_bridge.service import Bridge


class BridgeFixture:
    def make_symlink(self, link, target):
        try:
            link.symlink_to(target)
        except OSError as exc:
            if os.name == "nt" and getattr(exc, "winerror", None) == 1314:
                self.skipTest("Windows symlink privilege unavailable (WinError 1314)")
            raise

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        self.projects, self.work = root / "projects", root / "work"
        (self.projects / "Demo").mkdir(parents=True)
        (self.work / "staging").mkdir(parents=True)
        self.original = self.projects / "Demo" / "Demo.ap20"
        self.original.write_bytes(b"FAKE TIA PROJECT FOR TEST ONLY")
        self.source = self.work / "staging" / "example.scl"
        self.source.write_bytes(b"// ASCII test source; mock does not validate SCL")
        self.backend = MockBackend()
        self.bridge = Bridge(self.backend, self.projects, self.work, allow_writes=True)


class BridgeTest(BridgeFixture, unittest.TestCase):
    def test_open_uses_complete_copy_and_preserves_original(self):
        (self.projects / "Demo" / "sub").mkdir()
        (self.projects / "Demo" / "sub" / "data").write_bytes(b"companion")
        result = self.bridge.open_project("Demo/Demo.ap20")
        target = self.work / result["working_project"]
        self.assertNotEqual(target, self.original)
        self.assertEqual((target.parent / "sub" / "data").read_bytes(), b"companion")
        target.write_bytes(b"changed working copy")
        self.assertEqual(self.original.read_bytes(), b"FAKE TIA PROJECT FOR TEST ONLY")
        self.assertEqual(self.backend.calls[0][1][0], str(target))

    def test_root_directory_cannot_be_copied_as_one_project(self):
        (self.projects / "Root.ap20").write_bytes(b"fake")
        with self.assertRaises(BridgeError):
            self.bridge.open_project("Root.ap20")

    def test_nested_config_roots_rejected(self):
        with self.assertRaises(BridgeError):
            Bridge(self.backend, self.projects, self.projects / "work")

    def test_wrong_version_rejected(self):
        with self.assertRaises(BridgeError):
            self.bridge.open_project("Demo/Demo.ap19")

    def test_read_only_blocks_mutations_before_backend(self):
        self.bridge.allow_writes = False
        self.bridge.open_project("Demo/Demo.ap20")
        count = len(self.backend.calls)
        for operation in (lambda: self.bridge.save_project(),
                          lambda: self.bridge.compile_plc("mock/plc"),
                          lambda: self.bridge.import_source("mock/plc", "staging/example.scl", "0" * 64, True)):
            with self.assertRaisesRegex(BridgeError, "allow-writes"):
                operation()
        self.assertEqual(len(self.backend.calls), count)

    def test_source_changed_after_review_is_rejected(self):
        self.bridge.open_project("Demo/Demo.ap20")
        sha = self.bridge.read_artifact("staging/example.scl")["sha256"]
        self.source.write_bytes(b"// changed since review")
        with self.assertRaises(BridgeError) as caught:
            self.bridge.import_source("mock/plc", "staging/example.scl", sha, True)
        self.assertEqual(caught.exception.code, "SOURCE_CHANGED")
        self.assertFalse(any(name == "import_source" for name, _ in self.backend.calls))

    def test_import_pins_exact_reviewed_bytes(self):
        self.bridge.open_project("Demo/Demo.ap20")
        data = self.source.read_bytes()
        self.bridge.import_source("mock/plc", "staging/example.scl", digest(data), True)
        path = Path(self.backend.calls[-1][1][1])
        self.assertNotEqual(path, self.source)
        self.source.write_bytes(b"// later edit")
        self.assertEqual(path.read_bytes(), data)
        self.assertTrue(self.bridge.dirty)
        self.bridge.save_project()
        self.assertFalse(self.bridge.dirty)

    def test_scl_overwrite_is_acknowledged(self):
        self.bridge.open_project("Demo/Demo.ap20")
        with self.assertRaises(BridgeError) as caught:
            self.bridge.import_source("mock/plc", "staging/example.scl", digest(self.source.read_bytes()))
        self.assertEqual(caught.exception.code, "REPLACE_ACK_REQUIRED")

    def test_failed_import_stays_dirty(self):
        self.bridge.open_project("Demo/Demo.ap20")
        with self.assertRaises(BridgeError):
            self.bridge.import_source("unknown", "staging/example.scl", digest(self.source.read_bytes()), True)
        self.assertTrue(self.bridge.dirty)

    def test_windows_and_posix_path_attacks(self):
        for path in ["../bad.scl", "staging/../../bad.scl", "staging\\..\\bad.scl", "/bad.scl",
                     "C:/bad.scl", "C:bad.scl", "\\\\host\\share\\bad.scl", "//host/bad.scl",
                     "staging/file.scl:secret", "staging/NUL.scl", "staging/file.scl.", "staging/a\x00.scl"]:
            with self.subTest(path=path), self.assertRaises(BridgeError):
                relative_file(self.work, path, suffixes={".scl"})

    def test_link_escape_rejected(self):
        self.make_symlink(self.work / "staging" / "link.scl", self.original)
        with self.assertRaises(BridgeError):
            self.bridge.read_artifact("staging/link.scl")

    def test_project_link_rejected(self):
        self.make_symlink(self.original.parent / "leak", self.source)
        with self.assertRaises(BridgeError):
            self.bridge.open_project("Demo/Demo.ap20")

    def test_unexpected_symlink_creation_error_is_not_skipped(self):
        with patch.object(Path, "symlink_to", side_effect=FileExistsError("existing link")):
            with self.assertRaises(FileExistsError):
                self.make_symlink(self.work / "staging" / "link.scl", self.original)

    def test_xml_entities_and_non_block_xml_rejected(self):
        for data in [b'<!DOCTYPE Document [<!ENTITY x SYSTEM "file:///x">]><Document/>',
                     b'<Project/>', b'<Document><Device/></Document>',
                     b'<Document><SW.Blocks.FC/><Device/></Document>']:
            with self.subTest(data=data), self.assertRaises(BridgeError):
                validate_source(data, ".xml")

    def test_oversize_artifact_rejected(self):
        self.source.write_bytes(b"x" * (2 * 1024 * 1024 + 1))
        with self.assertRaises(BridgeError):
            self.bridge.read_artifact("staging/example.scl")

    def test_arbitrary_workspace_files_are_not_readable(self):
        with self.assertRaises(BridgeError):
            self.bridge.read_artifact("sessions/private.xml")


class ProtocolTest(BridgeFixture, unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.server = MCPServer(self.bridge)

    def initialize(self):
        response = self.server.handle({"jsonrpc": "2.0", "id": 0, "method": "initialize",
                                       "params": {"protocolVersion": "2025-03-26", "capabilities": {}, "clientInfo": {"name": "test", "version": "1"}}})
        self.assertEqual(response["result"]["protocolVersion"], "2025-03-26")
        self.server.handle({"jsonrpc": "2.0", "method": "notifications/initialized"})

    def call(self, name, arguments=None):
        return self.server.handle({"jsonrpc": "2.0", "id": "test-id", "method": "tools/call",
                                   "params": {"name": name, "arguments": arguments or {}}})

    def test_requires_initialization(self):
        self.assertEqual(self.call("status")["error"]["code"], -32002)

    def test_zero_request_id_preserved(self):
        response = self.server.handle({"jsonrpc": "2.0", "id": 0, "method": "ping"})
        self.assertEqual(response["id"], 0)

    def test_unknown_tool_never_dispatches(self):
        self.initialize()
        for name in ["__class__", "download", "run", "stop", "eval", "close"]:
            self.assertIn("error", self.call(name))
        self.assertEqual(self.backend.calls, [])

    def test_notifications_do_not_execute_calls(self):
        self.initialize()
        response = self.server.handle({"jsonrpc": "2.0", "method": "tools/call", "params": {"name": "open_project", "arguments": {"project": "Demo/Demo.ap20"}}})
        self.assertIsNone(response)
        self.assertEqual(self.backend.calls, [])

    def test_invalid_argument_types_and_extra_keys(self):
        self.initialize()
        for args in [{"project": 123}, {"project": "Demo/Demo.ap20", "shell": "unused"}, {}]:
            self.assertTrue(self.call("open_project", args)["result"]["isError"])
        self.assertEqual(self.backend.calls, [])

    def test_simulation_cannot_masquerade_as_compile(self):
        self.initialize()
        self.call("open_project", {"project": "Demo/Demo.ap20"})
        result = json.loads(self.call("compile_plc", {"plc_id": "mock/plc"})["result"]["content"][0]["text"])
        self.assertTrue(result["simulated"])
        self.assertIsNone(result["errors"])
        self.assertEqual(result["state"], "MOCK_NOT_COMPILED")

    def test_exception_does_not_echo_secrets(self):
        self.initialize()
        self.bridge.open_project("Demo/Demo.ap20")
        sensitive = "sk-" + "X9" * 24
        def fail(*args):
            raise RuntimeError(sensitive)
        self.backend.call = fail
        result = self.call("list_plcs")
        self.assertTrue(result["result"]["isError"])
        self.assertNotIn(sensitive, json.dumps(result))

    def test_bad_json_batch_duplicate_keys_and_recovery(self):
        raw = b'garbage\n[]\n{"jsonrpc":"2.0","id":1,"id":2,"method":"ping"}\n{"jsonrpc":"2.0","id":3,"method":"ping"}\n'
        output = io.BytesIO()
        self.server.serve(io.BytesIO(raw), output)
        messages = [json.loads(line) for line in output.getvalue().splitlines()]
        self.assertEqual([x["error"]["code"] for x in messages[:3]], [-32700, -32600, -32700])
        self.assertEqual(messages[-1]["result"], {})

    def test_message_size_limit(self):
        output = io.BytesIO()
        self.server.serve(io.BytesIO(b"x" * (MAX_FRAME_BYTES + 1)), output)
        self.assertEqual(json.loads(output.getvalue())["error"]["code"], -32600)

    def test_escaped_unicode_request_ids_do_not_break_stdio(self):
        ids = ["\ud800", "\udfff", "\u6d4b\u8bd5\U0001f600", 7]
        raw = b"".join((json.dumps({"jsonrpc": "2.0", "id": value, "method": "ping"}) + "\n").encode("utf-8")
                       for value in ids)
        output = io.BytesIO()
        self.server.serve(io.BytesIO(raw), output)
        messages = [json.loads(line) for line in output.getvalue().splitlines()]
        self.assertEqual([message["id"] for message in messages], ids)
        self.assertTrue(all(message["result"] == {} for message in messages))


if __name__ == "__main__":
    unittest.main()
