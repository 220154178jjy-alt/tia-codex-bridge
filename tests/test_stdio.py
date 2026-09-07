import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


class StdioIntegration(unittest.TestCase):
    def test_real_child_process_mcp_handshake_and_workflow(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            projects = root / "projects"
            (projects / "Demo").mkdir(parents=True)
            (projects / "Demo" / "Demo.ap20").write_bytes(b"MOCK INPUT")
            requests = [
                {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-03-26", "capabilities": {}, "clientInfo": {"name": "stdio-test", "version": "1"}}},
                {"jsonrpc": "2.0", "method": "notifications/initialized"},
                {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
                {"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "open_project", "arguments": {"project": "Demo/Demo.ap20"}}},
                {"jsonrpc": "2.0", "id": 4, "method": "tools/call", "params": {"name": "compile_plc", "arguments": {"plc_id": "mock/plc"}}},
                {"jsonrpc": "2.0", "id": 5, "method": "tools/call", "params": {"name": "save_project", "arguments": {}}},
            ]
            run = subprocess.run([sys.executable, "-m", "tia_bridge", "--backend", "mock", "--project-root", str(projects),
                                  "--workspace", str(root / "work"), "--allow-writes"],
                                 input="\n".join(json.dumps(x) for x in requests) + "\n",
                                 text=True, capture_output=True, timeout=20)
            self.assertEqual(run.returncode, 0, run.stderr)
            self.assertEqual(run.stderr, "")
            responses = [json.loads(x) for x in run.stdout.splitlines()]
            self.assertEqual([x["id"] for x in responses], [1, 2, 3, 4, 5])
            self.assertEqual(len(responses[1]["result"]["tools"]), 9)
            self.assertTrue(json.loads(responses[3]["result"]["content"][0]["text"])["simulated"])
            self.assertTrue(json.loads(responses[4]["result"]["content"][0]["text"])["saved"])


if __name__ == "__main__":
    unittest.main()
