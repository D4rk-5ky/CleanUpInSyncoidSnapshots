# Verification — CleanUpInSyncoidSnapshots 0.0.20

Date: 2026-10-27. Previous release: 0.0.19. Current source: 0.0.20 (one patch step).

## Layout

- `modules/`: config_loader.py, mqtt_notifications.py and mqtt_reporting.py, with a minimal __init__.py package marker. Root main imports use modules.*; internal imports are relative. Source workers still launch their own absolute file paths. Frozen hooks, build helper/spec and requirements are unchanged.
- `configs/`: config.toml, config-example.toml, datasets-example and hostnames-example. Both TOML files remain identical and their parsed values are identical to 0.0.19. Input paths stay relative to the selected TOML; the input examples remain beside it. Root help/README commands now use `-c configs/config.toml`; external custom config paths continue to work.
- `examples/`: live-preview-card.yaml, success-failure-automation.yaml and the relocated persistent-notification blueprint formerly under home-assistant/. All three YAML files retain their exact bytes. The now-empty home-assistant directory is removed in the new release.
- No standalone JSON example existed. PACKAGE_MANIFEST.json is actual release metadata and remains at root. No new JSON configuration/state/cache/log files are introduced.

Ten existing files are relocated, one package marker is added, and every one of the previous 28 project files is retained at its existing or mapped destination. The release contains 29 files. No duplicate root wrappers or copied config/example files are left behind. VERSIONING.md/versioning.md record the change and retain all previous entries verbatim; README and the code map describe current paths. Disclaimers remain verbatim.

The configs directory/example is explicitly unignored so Git does not hide the shipped reference; site-local configs/config.toml remains ignored. Packaging deliberately includes the safe distributed config copy, as in the previous release.

## Verification completed

Environment: Linux x86-64, Python 3.14.4, Paho MQTT 2.1.0, Jinja2 and PyYAML.

- 141 tests passed, zero failures/skips, in 7.008 seconds. All previous dataset progress (2/5), cleanup/retention, exit-code, notification, stderr, live state, HA/Pushover rendering and ephemeral localhost broker coverage remains passing.
- Four new layout regressions verify unique relocated paths, help/version and config loading from a foreign working directory, both actual source worker subprocesses under fake Paho from that directory, and real Git ignore behavior in an isolated temporary repository.
- Real MQTT protocol tests use ephemeral localhost fixtures only. ZFS, mail and production notification effects are intercepted; no destructive job, live Pushover notification or installed HA change occurs.
- Compile seven Python files (including the new package marker) plus the PyInstaller spec. Bytecode is written only to scratch outside the release. Bash syntax passes. Twenty source/preserved-executable CLI help/version/invalid-input checks pass without runtime logs; four further checks run after fresh ZIP extraction.
- AST comparison confirms every runtime function/class matches 0.0.19 after normalizing package-import syntax and the CLI help's config path. The only other source edits are version metadata and usage documentation. Dataset progress, snapshot selection, exact ZFS argv, retention, root guard, continuation/error codes, notifications, log placement and scheduling are unchanged.
- Both TOML configs have identical bytes and unchanged parsed settings, including every non-MQTT value, completion topic, disabled defaults and placeholder credential. All 61 supported settings remain represented, including optional/legacy examples in comments.
- Unchanged input examples and YAML files match their prior content hashes at the new destinations. Binary, build helper/spec, requirements, ownership metadata and DISCLAIMER.md are byte-identical to 0.0.19. README disclaimers and prior version entries are verbatim; paired ledgers match.
- The code map covers all 261 functions/methods/nested helpers and all 25 classes. The package marker has no functions or job actions and is explained in the file/layout map.

Run from the project root:

```bash
python3 -B -m unittest discover -s tests -v
python3 CleanUpInSyncoidSnapshots.py --help
python3 CleanUpInSyncoidSnapshots.py --version
```

For a reviewed job configuration, use the same public CLI with the relocated sample path:

```bash
sudo python3 CleanUpInSyncoidSnapshots.py -c configs/config.toml
```

No operational cleanup command above was run during verification; actual effects are exercised only with safe test substitutes.

## Archive audit

PACKAGE_MANIFEST.json records the supplied original archive and previous 0.0.19 archive, both SHA-256 digests, explicit source-to-destination relocation mappings, source/release content hashes and sizes, file permission modes, and per-file unchanged/modified/relocated/added status. A moved path is audited against its original source path, not reported as a lost file. Every original and previous file resolves to a unique packaged destination, with no unmapped missing files.

Verify safe unique relative ZIP paths, CRCs, complete tree/archive equality, all file hashes/sizes/modes, relocation completeness and a fresh extraction. Preserve recorded executable permissions; use 0644 data files and 0755 directories where no original Unix mode is recorded. Manifest self-hash/size are omitted to avoid circular metadata; the external ZIP checksum covers it. Report/manifest sidecars have the same bytes as their packaged copies.

No __pycache__, .pyc/.pyo, venvs, build/cache intermediates, runtime logs, temporary files or test Git repository is packaged. The original final dist executable is retained as a deliverable.

## Live-test limits

Production ZFS, mail/Pushover, MQTT credentials/ACLs/TLS and an installed Home Assistant instance remain untested. Actual deployment of discovery/cards/automations and another Python/platform require live testing. No scheduling or installed HA state was changed.

The preserved dist/CleanUpInSyncoidSnapshots remains version 0.0.16 and does not include the integration/layout changes. Use the current Python source, or rebuild in a disposable project copy using the unchanged helper. PyInstaller is unavailable in the active interpreter; no dependency installation or rebuilt frozen executable was attempted. Import/package wiring is compiled and source-worker tested; a new frozen build remains unverified.
