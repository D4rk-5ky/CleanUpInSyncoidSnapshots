# Verification — CleanUpInSyncoidSnapshots 0.0.3

Verified on 2026-09-15 in the release workspace using Python 3.13.5.
The application targets Linux/ZFS. Destructive ZFS operations were not run.

## Automated results

- **40 tests run: 37 passed and 3 skipped.**
- The three skipped tests are the optional real-Paho loopback MQTT integration tests
  because `paho-mqtt` is not installed in this verification environment.
- TOML schema/default/path tests passed, including exact coverage of every supported
  setting in `config-example.toml`.
- The packaged example loads as `dry-run` with mail and MQTT disabled.
- The plain TOML MQTT credential form `password = "<String>"` is covered by regression
  testing.
- Lifecycle tests passed for normal success, MQTT-disabled operation, root rejection,
  command failure diagnostics, missing input files, finalization failure, nonfatal mail
  failure/warning reporting, keyboard interrupt, and invalid config rejection.
- Snapshot/log retention regression tests passed with ZFS commands mocked.
- Home Assistant blueprint structural tests passed.

## Compile and CLI checks

- `CleanUpInSyncoidSnapshots.py`, `config_loader.py`, `mqtt_notifications.py`, and
  `tests/test_project.py` compiled successfully in memory without generating bytecode.
- Importing the application reports `__version__ == "0.0.3"`.
- Running the main script with no options exits 2 and shows required usage
  `CleanUpInSyncoidSnapshots.py -c CONFIG`.
- Supplying an old operational option such as `--command dry-run` exits 2 with an
  `unrecognized arguments` error; cleanup is not entered.
- Supplying `-c` with a missing TOML file exits 2 during configuration loading before
  cleanup starts.
- The public main application parser defines only `-c CONFIG`. The MQTT helper's
  `--publish` argument remains an internal worker entry point and is not a public cleanup flag.

## TOML/configuration checks

- `config-example.toml` contains exactly the supported `[cleanup]`, `[logging]`,
  `[report]`, `[mail]`, and `[mqtt]` sections.
- Every supported setting is present in the example and has an adjacent explanatory comment.
- Relative dataset, hostname, and MQTT certificate/key paths resolve against the TOML
  file directory.
- Unknown sections/options and wrong required types are rejected before `run_cleanup`.
- Mail remains opt-in with `mail.enabled = false` by default.
- MQTT remains opt-in with `mqtt.enabled = false` by default.
- The separate `mqtt-config-example.json` was intentionally removed because MQTT now
  uses the unified TOML configuration.

## Home Assistant check

The packaged blueprint was parsed successfully as YAML with a verification loader that
recognizes Home Assistant's `!input` tag. It remains receive-only: regression checks
confirm an MQTT trigger and `persistent_notification.create` action while finding no
MQTT publish action or ZFS destroy command.

## Original-to-release manifest comparison

The 0.0.2 input archive contained **14 files**. The 0.0.3 release contains **16 files**.

Added:

- `config-example.toml`
- `config_loader.py`
- `requirements.txt`

Removed/replaced:

- `mqtt-config-example.json` — replaced by the unified commented `config-example.toml`.

Changed intentionally:

- `CleanUpInSyncoidSnapshots.py`
- `README.md`
- `VERIFICATION.md`
- `VERSIONING.md`
- `commented_code_map.md`
- `home-assistant/CleanUpInSyncoidSnapshots-mqtt-persistent-notification.yaml`
- `mqtt_notifications.py`
- `requirements-mqtt.txt`
- `tests/test_project.py`

Preserved byte-for-byte from the 0.0.2 input archive:

- `.github/CODEOWNERS`
- `DISCLAIMER.md`
- `datasets-example`
- `hostnames-example`

No other original file is missing.

## Final archive manifest

Archive root: `CleanUpInSyncoidSnapshots-0.0.3/`. **16 files**:

- `.github/CODEOWNERS`
- `CleanUpInSyncoidSnapshots.py`
- `DISCLAIMER.md`
- `README.md`
- `VERIFICATION.md`
- `VERSIONING.md`
- `commented_code_map.md`
- `config-example.toml`
- `config_loader.py`
- `datasets-example`
- `home-assistant/CleanUpInSyncoidSnapshots-mqtt-persistent-notification.yaml`
- `hostnames-example`
- `mqtt_notifications.py`
- `requirements-mqtt.txt`
- `requirements.txt`
- `tests/test_project.py`

## Packaging checks

The release archive is checked for ZIP CRC integrity and byte-for-byte equality against
its release source tree after extraction. The ZIP must contain no `__pycache__`, `.pyc`,
`.pyo`, virtual environment, logs, build/cache directories, local credential/config files,
or temporary verification files. A SHA-256 sidecar is generated for the final ZIP.

## What was not fully tested

- No real `zfs destroy` was executed; destructive ZFS behavior is covered with mocks and
  the original command construction/selection logic was retained.
- No real mail server or host `mail` delivery was exercised.
- `paho-mqtt` is not installed here, so the three real loopback QoS/rejection/timeout
  integration tests were skipped. The worker/auth/TLS/timeout paths are still covered by mocks.
- No production MQTT broker or credentials were used.
- Home Assistant itself was not installed, so the blueprint was parsed and structurally
  tested but not imported/executed in a live Home Assistant instance.
- Python 3.10 is not installed in this workspace, so the `tomli` fallback could not be
  executed directly here; Python 3.13 uses standard `tomllib`.
