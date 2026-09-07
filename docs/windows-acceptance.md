# Windows / TIA acceptance procedure

Status: **not executed during initial development**. This requires your actual Windows machine, licensed TIA and the installed Siemens SDK. Use a disposable offline teaching project with an ordinary S7-1200/1500 PLC; do not use a running production project.

1. Record TIA major version, update level, STEP 7 edition, Python bitness, .NET version and project CPU model locally. Keep host names, usernames and internal network addresses out of any public report.
2. Install the matching Openness option, join the Siemens local group, re-login, and configure `config/codex.example.toml` for local paths. Start in default read-only mode.
3. Call `status`: require `simulated=false`. Note that `runtime_loaded=false` before the first project open is expected.
4. Close/save the source project in TIA. Open `Demo/Demo.ap20` (or `.ap19` with V19 configured). Handle any genuine Siemens permission prompt locally. Verify TIA opens the returned workspace session path, and original files are unchanged.
5. Call `list_plcs`, then `list_blocks`. Compare names/counts with the TIA tree, including a nested device group and user block group if present. Missing targets must be investigated before modifications.
6. Export a harmless FC, open the resulting XML locally and read it through `read_artifact`. Verify XML contents and SHA-256. Read-only mode must reject `import_source`, `compile_plc` and `save_project`.
7. Restart with `--allow-writes`, open a fresh copy and import the included ASCII `BridgeDemo.scl` after review. Confirm the exact PLC ID and overwrite semantics. Verify a real FC appears in TIA, then compile. Require actual TIA compiler output; mock output is never acceptance evidence.
8. For LAD: create a small ordinary LAD FC in TIA, export its valid SimaticML XML, copy/edit it into staging, import and compile. Inspect contacts/coils, connectivity, symbol references, block number and target group in the TIA editor. Do not use the mock XML fixture.
9. Make a deliberate SCL syntax error in a disposable copy and verify TIA reports nonzero errors. Restore a valid source, import and compile again. A failed call may leave partial changes; inspect them.
10. Change a staged file after reading its hash. The stale-hash import must fail before reaching Openness. Try a `../` file path; it must fail too.
11. Save the working copy, stop the bridge and close it in TIA. Reopen the saved working project manually and verify the imported blocks persist. Reopen the original separately and verify it is unchanged.
12. For timeout handling, use only a disposable project and a small configured timeout. If it occurs, verify `session_uncertain=true`, backend writes are blocked and the UI can be inspected; do not auto-retry. Increasing a timeout is preferable to deliberately interrupting a valuable project.

Record pass/fail, exact version/update, observed error category and a sanitized screenshot if useful. Do not attach actual private projects, export files, credentials or machine paths publicly. This acceptance covers offline engineering only; it does not validate real equipment behavior.
