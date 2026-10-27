# Verification — CleanUpInSyncoidSnapshots 0.0.16

Date: 2026-10-27. Runtime: Python 3.14.4, Linux x86_64, glibc 2.43.

## Automated regression suite

```text
python3 -B -m unittest discover -s tests -v
Ran 141 tests in 4.564s
OK
```

All 141 tests passed; none skipped. Full output is in `verification/unittest.txt`.

The suite includes the existing cleanup/config/mail/log-retention checks, the supplied template's completion/live checks, new adapter integration checks, and real frozen worker tests. Test imports and worker isolation/syntax-check paths were adapted to the `modules/` package; the two reporting modules themselves are byte-for-byte copies of the supplied template 1.1.0.

Verified behavior includes:

- All supporting Python modules live under `modules/`, with package imports in the entry point and relative adapter imports. Source workers launch the relocated files; frozen workers use the bundled package.
- Required completion JSON fields, typed booleans/integer code, success/status/code agreement, schema version, UTC timestamp, host, run ID and 4,000-character stderr tail.
- Cleanup's dry-run summary and planned/failed/skipped dataset diagnostics.
- Independent completion/live enable switches in all four combinations, shared run IDs, separate success and dry-run gates, and live-only operation.
- New JSON and equivalent TOML config, exact template option sets, TLS file resolution, strict validation and legacy MQTT defaults/alias conflict checks.
- Real measured dataset progress, unknown transfer values, successful/failed/skipped classifications, checked failures with continuation, immediate stops, interrupts and root rejection.
- Finalization failure remains failure; nonfatal mail errors set warning while preserving success.
- Live transport failure preserves cleanup and completion outcomes. Duplicate live launches do not run ZFS or overwrite active live state.
- Dry-run never destroys snapshots, prunes old logs or overwrites retained real-run live results.
- No Paho imports/transport workers when channels are disabled; credentials remain on worker stdin; errors are sanitized.
- Real Paho 2.1.0 completion delivery against a local fake MQTT broker at QoS 0, 1 and 2, including broker rejection and a deliberately stalled connection.
- Source workers against fake Paho helpers, heartbeat/discovery/retention policies and subprocess deadlines/cancellation.
- Both rebuilt executable private worker routes against a local fake MQTT broker: completion JSON is non-retained, all 14 discovery messages are retained, live state is non-retained and final real-run result is retained. Invalid private requests exit before configuration/cleanup.
- Python 3.10 syntax compatibility for application/reporting/config modules. Runtime execution used Python 3.14.4 only.

## Real frozen build

The existing `./build-pyinstaller.sh` completed successfully using:

- PyInstaller 6.22.3, hooks 2026.9.
- Python 3.14.4, Paho MQTT 2.1.0, Tomli 2.5.0.
- Linux x86_64, glibc 2.43.

`dist/` contains exactly one regular executable: `CleanUpInSyncoidSnapshots`. Its `--version` reports **0.0.16** and `--help` succeeds. It bundles both reporting modules and the optional Python dependencies. The source and build helper are included for rebuilding on the target Linux distribution; this binary is not verified on other architectures or older glibc versions.

## Additional checks

Source and executable version/help checks also passed from an unrelated working directory. Python compilation, shell syntax, config/payload example validation, original-vs-vendored module byte comparisons and package-manifest checks succeeded. Both HA YAML files parse successfully. The notification condition was rendered with Jinja against matching success/failure events and malformed status/code/success variants; matching events pass and malformed events are rejected.

## Limits

No production ZFS operations, mail delivery, production broker/TLS endpoint, or live Home Assistant instance were exercised. ZFS and mail are mocked in tests. Broker tests use local fake MQTT servers, so they confirm transport behavior rather than HA ingestion, notification display or dashboard rendering. Live final delivery is best effort under the template's bounded drain; running sensors can expire during outages. The live lock coordinates identities only within this installation's log directory.
