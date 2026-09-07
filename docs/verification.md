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
