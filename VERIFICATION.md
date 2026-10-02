# Verification — CleanUpInSyncoidSnapshots 0.0.12

Verification date: 2026-10-02.

## Requested behavior

This release adds the mail-side local suppression report that mirrors the existing MQTT suppression report.

For a **successful delete** or a **successful dry-run**:

- if mail is enabled and `mail.on_success=false`, the normal log contains exactly:
  `Success mail report suppressed by mail.on_success=false.`
- if MQTT is enabled and `mqtt.on_success=false`, the normal log contains exactly:
  `Success MQTT report suppressed by mqtt.on_success=false.`

The notification policy itself is unchanged:

- success + `on_success=false` -> suppress that channel's success notification;
- success + `on_success=true` -> send/publish that channel's success notification;
- failure -> send/publish through every enabled channel regardless of `on_success`;
- disabled channels never send/publish.

Dry-run remains non-destructive and follows the same notification/suppression policy as delete mode.

## Automated tests

Command:

```text
python3 -m unittest discover -s tests
```

Final result:

```text
Ran 65 tests
OK (skipped=3)
```

That is **62 passed, 3 skipped, 0 failed**.

The three skipped tests are the optional real-Paho MQTT broker/loopback tests because the optional `paho-mqtt` dependency is not installed in this verification environment.

New regression coverage verifies that the exact line
`Success mail report suppressed by mail.on_success=false.` is logged for both successful `delete` and successful `dry-run` executions while the mail sender itself remains uncalled.

Existing regressions still verify that successful dry-runs with both channels enabled and both `on_success=false` invoke neither mail nor MQTT notification path, while failed dry-runs still invoke both enabled channels.

## Compile and CLI checks

The following modules compiled successfully with `python3 -m py_compile`:

- `CleanUpInSyncoidSnapshots.py`
- `config_loader.py`
- `mqtt_notifications.py`
- `tests/test_project.py`

`python3 CleanUpInSyncoidSnapshots.py --version` returns:

```text
CleanUpInSyncoidSnapshots.py 0.0.12
```

`python3 CleanUpInSyncoidSnapshots.py --help` exits successfully and documents the public `-h/--help`, `--version`, and `-c/--config` options. Operational behavior remains TOML-configured.

## Documentation/config checks

- `README.md` describes current 0.0.12 behavior only and documents the exact mail and MQTT suppression messages.
- `VERSIONING.md` contains the 0.0.12 release record and preserves prior release history.
- `commented_code_map.md` identifies the lifecycle behavior and regression test for both delete and dry-run mail suppression reporting.
- `config-example.toml` is unchanged because no configuration key or default changed in 0.0.12.
- `DISCLAIMER.md` is unchanged from 0.0.11.

## 0.0.11-to-0.0.12 manifest comparison

The supplied 0.0.11 archive contains **17 project files**. The 0.0.12 source keeps the same **17 relative project file paths**; no required project file was added or removed.

Intentionally changed project files:

- `CleanUpInSyncoidSnapshots.py`
- `README.md`
- `VERIFICATION.md`
- `VERSIONING.md`
- `commented_code_map.md`
- `tests/test_project.py`

All other project files remain byte-for-byte unchanged from 0.0.11.

## Safety and limitations

No snapshot-selection, ZFS destroy, retention, dataset-continuation, mail-delivery, MQTT-delivery, or Home Assistant logic was changed in this release. The change is limited to the local mail success-suppression report, version/docs, and regression coverage.

No real ZFS destruction, production mail delivery, production MQTT broker connection, or Home Assistant runtime test was performed. Those external/integration behaviors remain covered only by existing mocked/static tests in this environment.
