# Sensitive information and local operation boundaries

## Publication scope

Publish source code, tests, generic examples and documentation only. Keep actual Codex configuration, environment files, credentials, private keys, server inventory, TIA projects/archives, exports, imported production source, binaries and logs outside this repository. `.gitignore` is preventive housekeeping; it does not remove already tracked files or rewrite past commits.

`scripts/scan_publish.py` checks exact index blobs and, with `--history`, all reachable local commits/tags/blobs plus every committed file path. It detects common provider credentials, private-key headers, credential assignments, authorization strings, JWTs, IP addresses, internal hostnames, personal email addresses, URL credentials/query parameters, non-reviewed URL hosts and some high-entropy quoted literals. File types and paths are allowlisted; unknown binaries, symlinks and submodules fail the check. Findings never print the matched value.

Only explicit public documentation hosts are allowed for normal links. Such URLs still undergo credential and query checks. Synthetic test secrets are assembled at runtime in temporary folders; no real credentials are embedded in tests. The scanner's tests verify both a staged secret hidden by a clean working file and a secret removed from the current tree but still in history.

Limitations: heuristic rules can miss unusual, encoded, split, low-entropy, or context-dependent credentials. Allowed public domains can themselves host confidential paths; manually review all outgoing files. The scan covers local reachable history, not unreachable objects, un-fetched remote branches, GitHub issues/PR text or external Git LFS storage. None of those are used in this initial source-only upload. Commit author metadata also needs review; use a GitHub noreply email if personal email should stay private.

A successful scan does not make a public repository uncrawlable. If a credential was ever published, revoke/rotate it first, then clean the affected history and references. Merely deleting it from the latest file does not invalidate it.

## Runtime

The bridge has no HTTP listener, remote transport, outbound networking code, credential store or automatic telemetry. STDIO talks to a local Codex process. Codex may send returned project source, identifiers and diagnostics to its configured model service; local bridge transport does not mean local model processing. `read_artifact` intentionally returns the requested source content. Use only projects whose contents may be shared with that client.

Real backend loading requires an explicitly selected local Siemens installation, native Windows x64 Python and .NET Framework. Openness authorizations, licenses, group membership and access controls remain enforced by Siemens. Do not replace installed DLLs with untrusted downloads or whitelist Python broadly for untrusted scripts.

Project operations use a fresh copy of a complete, closed project folder. Input/workspace roots must be separate local directories. Paths reject traversal, absolute tool arguments, alternate data streams, Windows reserved names, links and junctions. These checks are not a sandbox against another malicious process with the same filesystem privileges: a hostile same-user process could race file access or replace code/SDK files. Protect the host and workspace with normal OS permissions. Restrict Codex's own filesystem permissions separately if needed; this bridge cannot restrict Codex's other tools.

Import is bound to reviewed SHA-256 and pinned bytes. Project writes require the startup switch. SCL generation can overwrite existing blocks/types. Failed imports can partially modify a working copy; the original stays available, and the bridge marks the copy dirty. Compilation can change engineering data and does not imply functional correctness.

The MCP catalog exposes no PLC download, RUN/STOP, force, arbitrary online writes, hardware editor or general code-execution tools. All discovered PLCs must be offline for import/compile/save. This is an engineering assistant, not a certified machine safety component. Use the Windows acceptance procedure before relying on it for real engineering work.

On a timeout the native operation may still be in progress; further backend calls are blocked. Inspect the TIA UI before restart and never treat timeout as a rollback. Shutdown never implicitly saves or kills TIA; UI sessions and unsaved changes may remain.

Report security problems without posting credentials, customer projects or internal addresses into public issues. Use private reporting if the repository owner enables it; no contact address is hardcoded here.
