import importlib.util
from pathlib import Path
import subprocess
import tempfile
import unittest

SCANNER = Path(__file__).resolve().parents[1] / "scripts" / "scan_publish.py"
spec = importlib.util.spec_from_file_location("scanner", SCANNER)
scanner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(scanner)


class PublicationTests(unittest.TestCase):
    def test_detects_generated_credentials_without_printing_them(self):
        samples = ["sk-" + "pQ7z" * 10, "ghp_" + "Ab9" * 14,
                   "-----BEGIN " + "PRIVATE KEY-----", "AKIA" + "A9" * 8,
                   "password=" + "secret-value-123", "Authorization: Bearer " + "Q9" * 20]
        for sample in samples:
            result = scanner.scan_text("example", sample.encode())
            self.assertTrue(result, sample[:3])
            self.assertNotIn(sample, str(result))

    def test_server_addresses_and_personal_email(self):
        samples = [".".join(["10", "42", "0", "5"]), "https://" + "private" + ".internal/api",
                   "host" + "@" + "example.net", "fe80" + ":" * 2 + "cafe"]
        for sample in samples:
            self.assertTrue(scanner.scan_text("example", sample.encode()))

    def test_credentials_on_public_host_are_not_allowlisted(self):
        sample = "https://" + "user:pass" + "@github.com/repo"
        self.assertTrue(scanner.scan_text("example", sample.encode()))

    def test_public_docs_and_hash_are_accepted(self):
        self.assertFalse(scanner.scan_text("example", b"https://developers.openai.com/codex/mcp"))
        self.assertFalse(scanner.scan_text("example", ('"' + "abcd0123" * 8 + '"').encode()))

    def test_sensitive_files_and_symlinks_are_rejected(self):
        for name, mode in [(".env", "100644"), ("workspace/source.scl", "100644"),
                           ("Sdk.dll", "100644"), ("config." + "local.toml", "100644"), ("README.md", "120000")]:
            self.assertTrue(scanner.path_findings(name, mode))

    def test_staged_blob_not_working_tree_is_scanned(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            subprocess.run(["git", "init", "-q", str(root)], check=True)
            path = root / "code.py"
            path.write_text("api_key = '" + "sk-" + "Q7" * 20 + "'", encoding="utf-8")
            scanner.git(root, "add", "code.py")
            path.write_text("# harmless working tree", encoding="utf-8")
            self.assertFalse(scanner.scan_repository(root, history=False)["passed"])

    def test_secret_removed_from_current_tree_still_fails_history(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            scanner.git(root, "init", "-q")
            scanner.git(root, "config", "user.name", "Bridge Test")
            scanner.git(root, "config", "user.email", "bridge-test@users.noreply.github.com")
            path = root / "code.py"
            path.write_text("api_key = '" + "sk-" + "Q7" * 20 + "'", encoding="utf-8")
            scanner.git(root, "add", "code.py")
            scanner.git(root, "commit", "-qm", "Test fixture only")
            path.write_text("# removed secret", encoding="utf-8")
            scanner.git(root, "add", "code.py")
            self.assertTrue(scanner.scan_repository(root, history=False)["passed"])
            self.assertFalse(scanner.scan_repository(root, history=True)["passed"])


if __name__ == "__main__":
    unittest.main()
