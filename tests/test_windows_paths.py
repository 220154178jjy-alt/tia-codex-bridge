"""Exercise actual Windows directory junctions without symlink privileges."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

from tia_bridge.errors import BridgeError
from tia_bridge.mock import MockBackend
from tia_bridge.service import Bridge


@unittest.skipUnless(os.name == "nt", "Windows junction integration tests")
class WindowsJunctionTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root = Path(temp.name)
        self.projects, self.work = root / "projects", root / "work"
        (self.projects / "Demo").mkdir(parents=True)
        (self.work / "staging").mkdir(parents=True)
        self.original = self.projects / "Demo" / "Demo.ap20"
        self.original.write_bytes(b"MOCK PROJECT")
        self.source = self.work / "staging" / "test.scl"
        self.source.write_bytes(b"// synthetic fixture")
        self.backend = MockBackend()
        self.bridge = Bridge(self.backend, self.projects, self.work)

    def make_junction(self, link, target):
        # Environment parameters avoid interpreting filesystem paths as shell code.
        env = dict(os.environ, TIA_TEST_LINK=str(link), TIA_TEST_TARGET=str(target))
        subprocess.run([
            "powershell.exe", "-NoProfile", "-NonInteractive", "-Command",
            "New-Item -ItemType Junction -Path $env:TIA_TEST_LINK "
            "-Target $env:TIA_TEST_TARGET -ErrorAction Stop | Out-Null",
        ], env=env, check=True, capture_output=True, timeout=20)
        # Remove only the junction, before cleaning up the temporary directory.
        self.addCleanup(link.rmdir)

    def test_staging_junction_escape_is_rejected(self):
        self.make_junction(self.work / "staging" / "escape", self.original.parent)
        (self.original.parent / "outside.scl").write_bytes(b"// outside staging")
        with self.assertRaises(BridgeError) as caught:
            self.bridge.read_artifact("staging/escape/outside.scl")
        self.assertEqual(caught.exception.code, "UNSAFE_PATH")
        self.assertEqual(self.backend.calls, [])
        self.assertEqual(self.original.read_bytes(), b"MOCK PROJECT")

    def test_project_junction_is_rejected_before_copy(self):
        self.make_junction(self.original.parent / "escape", self.source.parent)
        with self.assertRaises(BridgeError) as caught:
            self.bridge.open_project("Demo/Demo.ap20")
        self.assertEqual(caught.exception.code, "UNSAFE_PATH")
        self.assertEqual(self.backend.calls, [])
        self.assertFalse((self.work / "sessions").exists())
        self.assertEqual(self.source.read_bytes(), b"// synthetic fixture")
