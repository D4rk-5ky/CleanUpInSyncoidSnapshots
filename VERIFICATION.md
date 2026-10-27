# Verification — CleanUpInSyncoidSnapshots 0.0.19

Date: 2026-10-27. Previous source: 0.0.18; current source: 0.0.19 (one patch step).

## Change

Main live progress now follows the existing parsed datasets_file list. Its total is the number of nonempty entries, available immediately after reading the file. Blank lines are ignored and repeated entries count separately in file order, exactly as the existing cleanup parser processes them.

`completed` counts finished dataset attempts: successful dataset returns plus checked dataset failures. `total` remains fixed even if a ZFS listing fails. Two finished entries in a five-entry file therefore report 2 / 5 and 40%. `details.current_dataset_index` shows the current one-based position, so the third running entry is position 3 / 5 while processed progress is still 2 / 5. An interruption leaves its current entry unfinished; stop-on-failure leaves later entries unprocessed.

`item_unit` is datasets. Snapshot outcomes remain separate, labeled by the new `outcome_item_unit = snapshots`; snapshot matches, retention skips, invalid timestamps, dry-run decisions, failed destroys and successful destroys never advance dataset progress. Snapshot decision counts remain available as details.snapshots_processed. A failed job can legitimately reach 100% dataset progress when every entry was attempted; its job status/code remains failure. No finish call forces a percentage or counter. Before the input file can be read, total remains null; an empty file has total 0 and unknown percentage.

The updated Markdown card shows processed dataset ratio, current file position, successful/failed dataset results and separate snapshot outcome lists. Generic live adapters default outcome units to their progress unit; older payloads without outcome_item_unit fall back to item_unit. Discovery IDs, manufacturer/role markers, completion topic, delivery behavior, Pushover guards, input rules, ZFS arguments, retention, root enforcement, mail, continuation policy, job exit codes and scheduling are unchanged. No new runtime setting or project file is added.

## Verification

- Full regression suite: 137 tests passed, zero failures/skips, on Python 3.14.4 in 4.627 seconds. Existing localhost Paho completion/live tests, worker timeout tests and offline HA/Pushover renders remain passing. Cleanup commands and actual notifications are intercepted; real protocol tests use only temporary localhost brokers.
- Five new regressions and one reused lifecycle helper cover the exact 2/5 state before the third entry in both delete/dry-run, continued failures, stopped failure at 1/5, interrupt at 2/5, duplicate/blank/empty input and actual card rendering with renamed sensors and separate snapshot outcomes.
- Snapshot selection and ZFS command functions retain their 0.0.18 ASTs. Cleanup lifecycle differs only in observation placement and enumerating the same dataset list to observe its one-based position; normalizing those observations/index returns the original lifecycle AST.
- Compile all six Python files and the PyInstaller spec with bytecode only in scratch. Verify source/preserved-executable help/version and safe invalid-argument/config cases (20 checks), Bash syntax, and four more help/version checks after fresh archive extraction.
- All 257 functions/methods/nested helpers and all 24 classes are covered by commented_code_map.md. README/module/config comments describe current dataset progress. VERSIONING.md and versioning.md are byte-identical, with all earlier release entries preserved verbatim.
- Both config examples are byte-identical and contain the same parsed values as 0.0.18, including all non-MQTT values, existing completion topic and disabled reporting defaults. All 61 supported keys remain represented, including optional/legacy examples in comments. No credential values are added.
- README disclaimer sections and DISCLAIMER.md are preserved verbatim. The original standalone binary, build helper/spec, requirements, input examples and repository metadata retain their bytes. No integration JSON configuration/state/cache/log files are introduced.

Run tests from the project directory:

```bash
python3 -B -m unittest discover -s tests -v
```

## Package

Keep all 28 previous project files and all 22 original archive paths. Regenerate PACKAGE_MANIFEST.json against the supplied original archive and previous 0.0.18 ZIP with per-file SHA-256 hashes, sizes, permission modes and no missing paths. Preserve original executable modes and use 0644 for data files without recorded Unix modes. The manifest self-hash/size are omitted to avoid circular metadata; an external archive SHA-256 covers the complete ZIP.

Verify unique safe paths, ZIP CRCs, tree/archive equality, per-file hashes/sizes/modes, synchronized ledgers/configs, fresh extraction and its CLI. Package no __pycache__, bytecode, virtualenv, build/cache intermediates, runtime logs or temporary files. The preserved final dist executable is a deliverable, not cache. Sidecar report/manifest bytes match the packaged copies.

## Live-test limits

No production ZFS listing/destruction, mail/Pushover, MQTT credentials/ACLs/TLS, installed Home Assistant or scheduling changes are exercised. Actual HA rendering/discovery under this configuration still needs a user-run live test; the automated renders use fake HA registries. No alternate Python/runtime/platform or rebuilt frozen binary was tested.

The preserved bundled executable remains 0.0.16 and does not include dataset progress or the reporting integration. Use current 0.0.19 Python source, or rebuild a disposable project copy with the included helper. PyInstaller is unavailable in the active interpreter; no dependency installation/build was attempted. Reporting delivery remains bounded best-effort and never replaces job failure.
