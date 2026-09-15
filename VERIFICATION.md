# Verification — CleanUpInSyncoidSnapshots 0.0.2

Verified on 2026-09-15 in the release workspace using Python 3.
The application targets Linux/ZFS; destructive ZFS operations were not run.

## Results

- **33 tests run: 30 passed and 3 skipped.**
- The three skipped tests are the optional real-Paho loopback broker tests because
  `paho-mqtt` is not installed in this verification environment.
- Existing configuration, report-schema, lifecycle, retention, timeout, TLS/auth
  mocks, root-rejection, error-reporting, dry-run, and mail-warning tests passed.
- Three new blueprint regression tests passed: receive-only MQTT behavior,
  report-contract validation, and notification-control inputs.
- The Home Assistant blueprint parsed as valid YAML with the Home Assistant
  `!input` tag recognized by the verification loader.
- Blueprint structure contains an MQTT trigger and
  `persistent_notification.create`, and contains no MQTT publish action or ZFS
  command.
- `CleanUpInSyncoidSnapshots.py --version` reports **0.0.2**.
- All Python source/test files compiled in memory without creating bytecode.
- README documents the packaged blueprint, local installation path, topic matching,
  result classes, notification replacement behavior, and manual integration path.

## Home Assistant verification limits

- Home Assistant itself is not installed in this workspace, so the blueprint was
  not imported into a live Home Assistant instance.
- The blueprint syntax and constructs were checked against current Home Assistant
  MQTT-trigger, blueprint, and persistent-notification documentation, plus generic
  YAML parsing with `!input` support.
- No production MQTT broker, Home Assistant MQTT integration, frontend notification,
  user credentials, TLS endpoint, or mobile notification target was exercised.
- The blueprint is intentionally receive-only. It cannot prove that the cleanup
  host published a report if the host loses power, the broker is unavailable, or
  the application exits before final reporting.

## MQTT verification continuity

Version 0.0.2 does not change `mqtt_notifications.py`, the MQTT JSON schema, broker
configuration, QoS handling, timeout behavior, or transport. Version 0.0.1 already
verified actual Paho 2.1.0 loopback publishing at QoS 0/1/2, broker rejection, and
stalled-broker timeout. The current environment lacks the optional Paho dependency,
so those three integration tests are skipped rather than replaced with weaker claims.

## Preserved assets and behavior

The following original/reference assets remain byte-for-byte unchanged from the
0.0.1 input archive:

- `.github/CODEOWNERS`
- `datasets-example`
- `hostnames-example`
- `mqtt-config-example.json`
- `mqtt_notifications.py`
- `requirements-mqtt.txt`
- `DISCLAIMER.md`

Snapshot selection/deletion, root enforcement, dry-run protections, email policy,
log retention, and MQTT delivery behavior are unchanged. The Python application
change in 0.0.2 is the version string only.

## Final archive file manifest

Archive root: `CleanUpInSyncoidSnapshots-0.0.2/`. **14 files**:

- `.github/CODEOWNERS`
- `CleanUpInSyncoidSnapshots.py`
- `DISCLAIMER.md`
- `README.md`
- `VERIFICATION.md`
- `VERSIONING.md`
- `commented_code_map.md`
- `datasets-example`
- `home-assistant/CleanUpInSyncoidSnapshots-mqtt-persistent-notification.yaml`
- `hostnames-example`
- `mqtt-config-example.json`
- `mqtt_notifications.py`
- `requirements-mqtt.txt`
- `tests/test_project.py`

## Packaging rules

The final archive must contain no `__pycache__`, `.pyc`, `.pyo`, virtual environment,
local MQTT credentials/config, logs, downloaded dependencies, build/cache folders,
or temporary verification files. ZIP CRC integrity and archive/source byte equality
are checked after packaging. A SHA-256 sidecar is generated for the final archive.
