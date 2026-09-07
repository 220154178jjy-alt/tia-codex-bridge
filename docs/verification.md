# Initial verification record

Date: 2026-09-06. Release: 0.1.0.

| Area | Result / boundary |
| --- | --- |
| Linux automated suite | 38 tests passed on Python 3.12.13; standard-library unittest |
| Package installation | Offline wheel build/install in a temporary venv, import from outside the repository and installed console entry point passed; Windows Python.NET extra not exercised |
| MCP subprocess | Actual Python child process: initialize, initialized notification, tool catalog, project-copy workflow, mock compile and save responses |
| Policy/path checks | Read-only denial; parent traversal; Windows drive/UNC/device/ADS paths; symbolic link rejection; file-size cap; source-copy isolation |
| Import integrity | Stale source hash refused; reviewed bytes pinned separately; failed call leaves dirty state; SCL replacement acknowledgement |
| Protocol robustness | Unknown tools; malformed/batch/duplicate-key JSON; frame limit; notification does not execute a tool; request ID zero; private exception values suppressed |
| Openness adapter contract | Nested device groups; recursive compiler messages; online/unverifiable state refusal; SCL void return; XML import options; timeout blocks duplicate dispatch — tested using API doubles |
| Publication scanner | Synthetic credential/IP/host tests; exact staged blob versus working file; removed secret still found in local history; findings omit matched values |
| Python syntax | All bridge/scanner modules compile with Python compileall |
| Source review | Only code, synthetic tests, generic config/example and documentation staged; no TIA projects, DLLs, live config, logs or credentials included |
| Real Windows/Python.NET/TIA | NOT EXECUTED in the development environment; no Siemens installation or Windows desktop was available |
| TIA compiler / LAD round trip | NOT EXECUTED; follow windows-acceptance.md on the actual licensed workstation |
| PLC hardware / PLCSIM | NOT EXECUTED; no online operations are implemented |

Before each push, run `python scripts/scan_publish.py --staged --history`. A clean result means the included heuristic rules found no matches in that exact index/reachable history. It is not proof that every conceivable secret format is absent. Public repository contents remain readable by crawlers.

The workflow runs Linux and Windows mock/protocol checks after upload. Those CI results are separate from the initial Linux execution above. Windows CI without TIA does not establish real Openness compatibility.

## Maintenance verification: 2026-09-07

The published baseline `e88f4a7` passed all 38 tests on both GitHub-hosted
Windows and Ubuntu, including both symbolic-link rejection tests without skips.
See [baseline workflow run](https://github.com/220154178jjy-alt/tia-codex-bridge/actions/runs/34084098169).

Additional testing reproduced a stdio crash: a JSON-escaped lone surrogate in a
request ID caused `UnicodeEncodeError` while writing the response, disconnecting
the client before subsequent requests could be processed. Response serialization
now escapes Unicode on the wire; decoded text and request IDs are preserved.
The regression test covers high/low lone surrogates, ordinary Unicode and a
following request to verify that the connection remains usable.

Symbolic-link tests now skip only Windows error 1314 (missing privilege), rather
than hiding all creation errors. Two new Windows tests create actual directory
junctions and verify that staging escapes and project-folder links are rejected
before backend dispatch. Junction creation requires no symlink privilege in the
tested environment; cleanup removes the link itself, preserving its target.

Local Windows / Python 3.12.14 verification: 42 tests, 40 passed and 2 skipped
specifically for error 1314. Both junction tests ran and passed. Python syntax and
diff whitespace checks passed. On non-Windows systems only the two Windows
junction tests are intentionally skipped.

No TIA Portal/STEP 7/Openness installation was found in the checked standard
installation locations and uninstall registry. Real Siemens API calls, real
project compilation and PLC hardware acceptance remain unverified.
