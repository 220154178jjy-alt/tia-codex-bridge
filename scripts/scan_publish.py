"""Fail-closed, dependency-free review of exact Git index blobs and reachable history.

Findings contain a rule and location, NEVER the matched credential or source line.
Heuristics do not establish that arbitrary text is free of secrets. Review the manifest too.
"""
from __future__ import annotations

import argparse
import hashlib
import ipaddress
import json
import math
from pathlib import Path
import re
import subprocess
from urllib.parse import urlsplit

ALLOWED_PUBLIC_HOSTS = {
    "github.com", "docs.github.com", "developers.openai.com", "learn.chatgpt.com",
    "modelcontextprotocol.io", "pythonnet.github.io", "pypi.org",
    "docs.tia.siemens.cloud", "support.industry.siemens.com",
}
TEXT_SUFFIXES = {".py", ".md", ".toml", ".txt", ".json", ".yaml", ".yml", ".ps1", ".scl", ".sh"}
TEXT_NAMES = {".gitignore", ".gitattributes", "pre-commit", "pre-push"}
DENY_DIRS = {".codex", ".ssh", ".aws", ".azure", "workspace", "projects", "sessions",
             "artifacts", "staging", "imports", "logs", "backups", ".venv", "__pycache__"}
RULES = {
    "private-key": r"-{5}BEGIN (?:[A-Z ]+ )?PRIVATE KEY-{5}",
    "github-token": r"\b(?:gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,})\b",
    "provider-key": r"\bsk-(?:proj-|ant-api\d+-)?[A-Za-z0-9_-]{20,}\b",
    "aws-key": r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b",
    "google-key": r"\bAIza[A-Za-z0-9_-]{30,}\b",
    "slack-token": r"\bxox[baprs]-[A-Za-z0-9-]{16,}\b",
    "jwt": r"\beyJ[A-Za-z0-9_-]{12,}\.[A-Za-z0-9_-]{12,}\.[A-Za-z0-9_-]{12,}\b",
    "internal-host": r"\b[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.(?:internal|local|corp|lan)\b",
    "connection-string": r"(?i)\b(?:AccountKey|SharedAccessSignature|Password)\s*=\s*[^\s;'\"]{8,}",
    "authorization": r"(?i)\b(?:Bearer|Basic)\s+[A-Za-z0-9+/=_-]{20,}",
}
PLACEHOLDERS = {"CHANGE_ME", "REPLACE_ME", "YOUR_API_KEY", "YOUR_TOKEN", "<REDACTED>"}


def scan_text(label: str, data: bytes) -> list[dict]:
    try:
        text = data.decode("utf-8")
    except UnicodeError:
        return [{"file": label, "line": 0, "rule": "non-utf8-content"}]
    if "\x00" in text:
        return [{"file": label, "line": 0, "rule": "binary-content"}]
    findings = []

    def hit(rule, start):
        findings.append({"file": label, "line": text.count("\n", 0, start) + 1, "rule": rule})

    for name, pattern in RULES.items():
        for match in re.finditer(pattern, text):
            hit(name, match.start())
    for match in re.finditer(r"\b(?:\d{1,3}\.){3}\d{1,3}\b", text):
        try:
            ipaddress.IPv4Address(match.group())
            hit("ip-address", match.start())
        except ValueError:
            pass
    for match in re.finditer(r"(?<![\w:])[0-9A-Fa-f]*:[0-9A-Fa-f:]+(?:%\w+)?", text):
        try:
            ipaddress.IPv6Address(match.group())
            hit("ipv6-address", match.start())
        except ValueError:
            pass
    for match in re.finditer(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}", text):
        if not match.group().endswith("@users.noreply.github.com"):
            hit("personal-email", match.start())
    for match in re.finditer(r"\b(?:https?|ssh|ftp|postgres(?:ql)?|mysql|mongodb)://[^\s<>\"')]+", text):
        try:
            uri = urlsplit(match.group())
            if uri.username or uri.password or uri.query or uri.fragment:
                hit("url-credentials-or-parameters", match.start())
            if uri.hostname not in ALLOWED_PUBLIC_HOSTS:
                hit("unreviewed-server-url", match.start())
        except ValueError:
            hit("malformed-url", match.start())
    assigned = r'''(?im)\b(?:api[_-]?key|access[_-]?token|client[_-]?secret|password|passwd|secret[_-]?key)\b["']?\s*[:=]\s*["']?([A-Za-z0-9_./+@:$%=-]{8,})'''
    for match in re.finditer(assigned, text):
        if match.group(1) not in PLACEHOLDERS:
            hit("sensitive-assignment", match.start())
    for match in re.finditer(r'''(?im)\b(?:server|hostname)\b["']?\s*[:=]\s*["']([A-Za-z0-9._:-]{3,})["']''', text):
        hit("server-assignment", match.start())
    for match in re.finditer(r'''["']([A-Za-z0-9_+/=-]{28,})["']''', text):
        value = match.group(1)
        if re.fullmatch(r"[0-9a-fA-F]{32,128}", value):
            continue  # Content hashes; contextual assignment rules still apply.
        entropy = -sum((value.count(c) / len(value)) * math.log2(value.count(c) / len(value)) for c in set(value))
        if entropy >= 4.5 and any(c.isdigit() for c in value):
            hit("high-entropy-literal", match.start())
    return findings


def path_findings(name: str, mode: str) -> list[dict]:
    parts = Path(name).parts
    base = Path(name).name.lower()
    denied = any(p.lower() in DENY_DIRS for p in parts) or base.startswith((".env", "credentials", "secrets")) or ".local." in base
    approved_type = Path(name).suffix.lower() in TEXT_SUFFIXES or base in TEXT_NAMES
    if denied or not approved_type or mode not in {"100644", "100755"}:
        return [{"file": name, "line": 0, "rule": "unapproved-file-or-mode"}]
    return []


def git(root, *args):
    result = subprocess.run(["git", "-C", str(root), *args], stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    if result.returncode:
        raise RuntimeError("Git scan failed; publication must stop.")
    return result.stdout


def scan_repository(root: Path, history: bool) -> dict:
    findings, manifest = [], []
    entries = git(root, "ls-files", "--stage", "-z").split(b"\x00")
    for entry in filter(None, entries):
        head, name_raw = entry.split(b"\t", 1)
        mode, sha, stage = head.decode().split()
        name = name_raw.decode("utf-8")
        if stage != "0":
            raise RuntimeError("Unmerged index; publication must stop.")
        data = git(root, "cat-file", "blob", sha)
        findings.extend(path_findings(name, mode))
        findings.extend(scan_text(name, data))
        manifest.append({"path": name, "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()})
    if not manifest:
        raise RuntimeError("Empty index; nothing has been approved for publication.")
    objects_checked = 0
    if history:
        # Check every reachable blob, including files removed from the latest tree.
        for line in git(root, "rev-list", "--objects", "--all").splitlines():
            sha = line.split(b" ", 1)[0].decode()
            kind = git(root, "cat-file", "-t", sha).strip()
            if kind in {b"blob", b"commit", b"tag"}:
                data = git(root, "cat-file", "-p", sha)
                findings.extend(scan_text("history:" + sha[:12], data))
                objects_checked += 1
        # Also catch sensitive filenames and modes from every committed tree.
        for commit in git(root, "rev-list", "--all").decode().splitlines():
            for entry in filter(None, git(root, "ls-tree", "-r", "-z", commit).split(b"\x00")):
                head, name = entry.split(b"\t", 1)
                findings.extend(path_findings(name.decode(), head.decode().split()[0]))
    return {"passed": not findings, "scope": "exact Git index" + (" and all reachable local history" if history else ""),
            "files_checked": len(manifest), "history_objects_checked": objects_checked,
            "findings": findings, "manifest": manifest,
            "limitation": "Heuristic scan; no guarantee against unknown secret formats. Review the full manifest before pushing."}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path.cwd())
    parser.add_argument("--staged", action="store_true", help="Exact Git index is always scanned.")
    parser.add_argument("--history", action="store_true")
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    try:
        report = scan_repository(args.repo, args.history)
    except Exception:
        print("Scan could not complete. Publication must stop.")
        return 2
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in report.items() if k != "manifest"}, indent=2, ensure_ascii=False))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
