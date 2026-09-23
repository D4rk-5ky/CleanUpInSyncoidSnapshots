# Verification — CleanUpInSyncoidSnapshots 0.0.5

Verified on 2026-09-23 in the release workspace using Python 3.13.5.
The application targets Linux/ZFS. Destructive ZFS operations were not run.

## Automated results

- **46 tests run: 43 passed and 3 skipped.**
- The three skipped tests are the optional real-Paho loopback MQTT integration tests
  because `paho-mqtt` is not installed in this verification environment.
- The reported fatal-command pattern is covered with a mocked `CommandError` equivalent
  to a failing `zfs list`: when mail and MQTT are enabled, one failure email and one
  failure MQTT report are both attempted, and command stderr is included in MQTT diagnostics.
- Early runtime failure before log setup is covered: enabled mail falls back to a minimal
  no-attachment failure message and MQTT is still attempted independently.
- Late log-retention/finalization failure is covered: the final MQTT status is failure and
  enabled failure mail is still attempted.
- Failed dry-runs are covered: `publish_dry_run = false` suppresses only routine successful
  previews; a failed dry-run still publishes when MQTT is enabled.
- Successful MQTT worker completion is covered and logs `MQTT report sent successfully`.
- TOML schema/default/path tests passed, including every supported setting in
  `config-example.toml`.
- Snapshot/log retention tests passed with ZFS commands mocked.
- Home Assistant blueprint structural tests passed.

## Compile and CLI checks

- `CleanUpInSyncoidSnapshots.py`, `config_loader.py`, `mqtt_notifications.py`, and
  `tests/test_project.py` compiled successfully in memory without generating bytecode.
- Importing the application reports `__version__ == "0.0.5"`.
- Running the main script with no options exits 2 and shows required usage
  `CleanUpInSyncoidSnapshots.py -c CONFIG`.
- Supplying an old operational option such as `--command dry-run` exits 2 with an
  `unrecognized arguments` error; cleanup is not entered.
- The public main application parser still exposes only `-c CONFIG`.

## Failure-notification checks

- Normal cleanup/ZFS exceptions keep the existing log-attached failure email path.
- `state["failure_mail_attempted"]` prevents duplicate failure-mail attempts for the same
  normal failure while allowing `main()` to cover errors outside the normal mail block.
- If logger state exists for a late runtime error, `send_failure_mail_if_needed()` reuses
  `MailTo()` so log attachments remain available.
- If logger setup never completed, the fallback uses `send_mail()` without attachments so
  email is still attempted rather than silently skipped.
- MQTT is attempted after the email path and remains independent of email success/failure.
- `notify_mqtt()` returns `True` only when its isolated publisher exits successfully and
  returns `False` for disabled/suppressed/failed delivery without changing cleanup status.
- Fatal exceptions are still re-raised after notification attempts, preserving nonzero
  service/process behavior.

## 0.0.4-to-0.0.5 manifest comparison

The supplied 0.0.4 archive contains **17 files**. The 0.0.5 release also contains
**17 files**. No project file was added or removed.

Changed intentionally:

- `CleanUpInSyncoidSnapshots.py`
- `README.md`
- `VERIFICATION.md`
- `VERSIONING.md`
- `commented_code_map.md`
- `config-example.toml`
- `mqtt_notifications.py`
- `tests/test_project.py`

Preserved byte-for-byte from the supplied 0.0.4 archive:

- `.github/CODEOWNERS`
- `.gitignore`
- `DISCLAIMER.md`
- `config_loader.py`
- `datasets-example`
- `home-assistant/CleanUpInSyncoidSnapshots-mqtt-persistent-notification.yaml`
- `hostnames-example`
- `requirements-mqtt.txt`
- `requirements.txt`

## Packaging checks

The final archive is checked for ZIP CRC integrity and byte-for-byte equality against
its release source tree after extraction. It must contain no `__pycache__`, `.pyc`,
`.pyo`, virtual environment, generated `logs/`, build/cache directories, local credential
files, or temporary verification files. A SHA-256 sidecar is generated for the ZIP.

## What was not fully tested

- No real `zfs destroy` or production ZFS dataset operation was executed; destructive ZFS
  behavior is covered with mocks and its snapshot-selection/destruction construction remains
  unchanged.
- No real mail server or host `mail` delivery was exercised.
- `paho-mqtt` is not installed here, so the three real loopback QoS/rejection/timeout
  integration tests were skipped. Worker/auth/TLS/timeout behavior remains covered by mocks.
- No production MQTT broker or credentials were used.
- Home Assistant itself was not installed, so the packaged blueprint was structurally tested
  rather than executed in a live instance.
- Python 3.10 is not installed in this workspace, so the `tomli` fallback could not be
  executed directly here; Python 3.13 uses standard `tomllib`.
