# Verification — CleanUpInSyncoidSnapshots 0.0.16

Date: 2026-10-26. New version: 0.0.15 → 0.0.16.

## Run name behavior

Reuse the existing setting, without adding a duplicate configuration option:

```toml
[report]
title = "NAS nightly cleanup"
comment = "After Syncoid replication"
```

The configured name is included in MQTT JSON `title`, at the top of the email body, and now at the start of every email subject. For example:

```text
[NAS nightly cleanup] Syncoid cleanup SUCCESS - logs attached
[NAS nightly cleanup] Syncoid cleanup FAILED - logs attached
[NAS nightly cleanup] Syncoid cleanup DRY-RUN SUCCESS - report/logs attached
[NAS nightly cleanup] Syncoid cleanup DRY-RUN FAILED - report/logs attached
[NAS nightly cleanup] Syncoid cleanup FAILED - not run as root
```

The shared `MailTo` function adds the prefix exactly once. It collapses title whitespace for a single-line subject; the email body and MQTT keep the existing stripped title text. Blank titles preserve existing email subjects and the MQTT application-name fallback. MQTT `name` remains the fixed application identifier and `job` remains the logging prefix, preserving Home Assistant's filtering contract.

Notification enablement and success opt-in still control delivery. Configuring a title does not enable mail/MQTT or success notifications. Log filenames, MQTT topics, selection, retention, dry-run protection and root enforcement are unchanged.

## Changes and preserved files

- Increment application/version references to 0.0.16 and rebuild the standalone binary.
- Extend `MailTo` with the shared subject prefix; correct the mail-header docstring and add `report.title` guidance to `--help`.
- Reuse existing report/config modules. No MQTT/config-loader implementation or schema changes.
- Extend the existing test fixtures with configurable titles and real `MailTo` execution while mocking the external mail boundary. Add three meaningful regressions covering named lifecycle paths, blank fallback and multiline subject handling.
- Update README for current behavior, config example comments, every-function/command map and VERSIONING history.
- Preserve DISCLAIMER.md and its exact owner-supplied text; retain all original project files and build metadata.
- Refresh this verification report and PACKAGE_MANIFEST.json.

The complete project was inspected in 0.0.15 and relevant paths were reread before this change. AST comparison against 0.0.15 confirms all main-module functions/classes are unchanged except `main` (version/help), `MailTo` (subject) and the `build_backup_mail_header` docstring. Config loader, MQTT module, Home Assistant blueprint, build helper/spec, requirements and disclaimer remain byte-for-byte unchanged from 0.0.15. The existing publisher process-group timeout fix is retained.

## Automated verification

| Check | Result |
| --- | --- |
| Full suite on Python 3.14 | 73 passed, 0 failed, 0 skipped |
| Full suite on Python 3.12 | 73 passed, 0 failed, 0 skipped |
| Named lifecycle regressions | Delete/dry-run success, checked-command failure and root rejection all carry matching subject/body/MQTT names |
| Blank and multiline names | Legacy blank fallback retained; CR/LF/tab whitespace normalized only in subjects |
| Frozen MQTT worker | All 3 localhost integration tests pass: QoS 0/1/2, rejection and process-group timeout |
| Actual frozen application | Configured name reached a captured local mail subject/body and real localhost MQTT report during non-root rejection; exit 1 retained, no ZFS calls |
| Python compile | App, config loader, MQTT module, tests and PyInstaller spec compile |
| Shell syntax | `bash -n build-pyinstaller.sh` passes |
| Documentation coverage | Every Python function/method/nested helper appears in commented_code_map.md |
| Config example | All supported settings represented; dry-run and disabled notifications remain the defaults |

Full-suite command from the project directory:

```bash
python3 -B -m unittest discover -s tests -v
```

ZFS and external mail delivery were mocked. Real MQTT protocol checks used only an ephemeral localhost broker fixture. The actual frozen app test captured a fake local `mail` command and relied on verified non-root rejection before dataset input or ZFS processing.

## CLI and standalone executable

The actual unchanged build helper recreated `dist/` and built the final Linux x86-64 executable using Python 3.12.14 and the declared build dependencies. It verified that `dist/` contains exactly one regular executable and ran its help/version smoke checks.

Both source and frozen modes pass `-h`, `--help`, `--version`, missing-argument, unsupported/obsolete-flag, missing-config-via-either-alias, and malformed-TOML checks. Help includes the run-name setting. Version output is 0.0.16. Help/version/invalid-config checks create no runtime logs. Fresh extraction of the final ZIP passes the same checks.

Executable SHA-256:

```text
e4b450b7ad507dde5d10a733de620dfd80867fe32eb9677ec55f40d2fb9647b7
```

## Archive verification

Original input: `CleanUpInSyncoidSnapshots-main.zip`.

Original SHA-256:

```text
6f2b272f947e0536c5bc6f5c981c915b1eb76d715bddd50050aaeb89327b3c8d
```

Final archive: `CleanUpInSyncoidSnapshots-0.0.16.zip`.

- Original files: 21. Final files: 22. Missing original paths: 0.
- Against the original input: 9 intentionally modified files, 12 byte-for-byte unchanged files, and PACKAGE_MANIFEST.json added.
- Against 0.0.15: all 22 relative file paths retained; 9 changed files including regenerated PACKAGE_MANIFEST.json, 13 unchanged.
- Executable permissions retained on app script, build helper and standalone binary.
- ZIP CRC, file paths, sizes, modes and hashes verified against the prepared project.
- Fresh extraction matches every manifest hash and compiles successfully.
- No Python bytecode/cache, build intermediates, virtualenvs, runtime logs or temporary files included.

Changed since 0.0.15:

```text
CleanUpInSyncoidSnapshots.py
PACKAGE_MANIFEST.json
README.md
VERIFICATION.md
VERSIONING.md
commented_code_map.md
config-example.toml
dist/CleanUpInSyncoidSnapshots
tests/test_project.py
```

PACKAGE_MANIFEST.json records both baseline comparisons and file hashes. It excludes its own content hash to avoid circular metadata. SHA256SUMS-0.0.16.txt covers the final ZIP and separately supplied verification/manifest files. The 0.0.15 artifacts remain available unchanged.

## Limits

No real ZFS listing/destruction, production email delivery, production MQTT credentials/ACLs/TLS handshake, or running Home Assistant instance was tested. Frozen compatibility on other Linux systems/architectures and source compatibility under Python 3.10 were not tested. Existing source tests cover config/auth/TLS wiring using mocks; actual MQTT protocol delivery was checked locally.

The app has no run lock; concurrent cleanup runs require external coordination. Verification is not a professional audit.
