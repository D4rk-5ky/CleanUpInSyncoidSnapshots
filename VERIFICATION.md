# Verification — CleanUpInSyncoidSnapshots 0.0.6

Verified on 2026-09-25 in the release workspace using Python 3.13.5.
The application targets Linux/ZFS. Destructive ZFS operations were not run.

## Automated results

- **45 tests run: 42 passed and 3 skipped.**
- The three skipped tests are the optional real-Paho loopback MQTT integration tests
  because `paho-mqtt` is not installed in this verification environment.
- The new missing-dataset lifecycle test uses the real ZFS diagnostic form
  `cannot open 'tank/missing': dataset does not exist` and confirms a missing first dataset
  does not prevent the next two configured datasets from being processed.
- That same test confirms the final process result remains exit code 1, the existing MQTT
  report remains `status: failure`, and the existing `error` and `stderr` fields identify
  the missing dataset and retain the original ZFS diagnostic.
- The missing-dataset test also confirms enabled mail follows the existing failed-mail path,
  uses a `FAILED` subject, and receives a specific missing-dataset explanation.
- A separate safety regression confirms an unrelated ZFS failure such as `permission denied`
  still aborts immediately before later datasets are attempted.
- Existing TOML schema/default/path, retention, root guard, mail-warning, interrupt,
  logging-location, MQTT report/worker, and Home Assistant blueprint tests continue to pass.

## Compile and CLI checks

- `CleanUpInSyncoidSnapshots.py`, `config_loader.py`, `mqtt_notifications.py`, and
  `tests/test_project.py` compiled successfully in memory without generating release bytecode.
- Importing the application reports `__version__ == "0.0.6"`.
- `CleanUpInSyncoidSnapshots.py --help` exits successfully and documents:
  - `-h, --help`
  - `-c, --config CONFIG`
- Running the main script with no options exits 2 and reports that `-c/--config` is required.
- Supplying an old operational option such as `--command dry-run` still exits 2 as unrecognized.
- Every top-level function/class in `CleanUpInSyncoidSnapshots.py`, including the new
  missing-dataset helpers, is represented in `commented_code_map.md`.

## Missing-dataset behavior checked

The new special case is deliberately narrow:

1. `delete_syncoid_snapshots` still runs the same checked, nonrecursive per-dataset
   `zfs list -H -t snapshot -o name DATASET` command.
2. `run_cmd` still raises the existing `CommandError` on nonzero return codes and logs the
   original stderr to the `.err` logger.
3. `run_cleanup` recognizes only stderr containing the explicit `dataset does not exist`
   diagnostic, records that configured dataset, and continues with later configured datasets.
4. After all remaining datasets have been attempted, the run is still marked failed. It sends
   failed mail when enabled, skips successful-run log pruning, and exits 1.
5. `main` therefore uses the existing failure-report path. The MQTT JSON schema and status
   names are not changed: `status` remains `failure`, `exit_code` remains 1, and the already
   existing `error`/`stderr` fields carry the specific reason and original diagnostic.
6. Any other checked list failure and every checked `zfs destroy` failure retain the original
   immediate-fatal behavior.

## Unchanged integration contract

The following files are SHA-256 byte-for-byte unchanged from the supplied 0.0.5 archive:

- `mqtt_notifications.py`
- `home-assistant/CleanUpInSyncoidSnapshots-mqtt-persistent-notification.yaml`
- `config_loader.py`
- `DISCLAIMER.md`

This verifies that the MQTT report schema/transport implementation, Home Assistant blueprint
consumer logic, TOML loader, and supplied disclaimer were not modified for this release.

## 0.0.5-to-0.0.6 manifest comparison

The supplied 0.0.5 archive contains **17 project files**. The 0.0.6 release contains the same
**17 relative project file paths**. No project file was added or removed.

Changed intentionally:

- `CleanUpInSyncoidSnapshots.py`
- `README.md`
- `VERIFICATION.md`
- `VERSIONING.md`
- `commented_code_map.md`
- `config-example.toml`
- `tests/test_project.py`

Preserved byte-for-byte from 0.0.5:

- `.github/CODEOWNERS`
- `.gitignore`
- `DISCLAIMER.md`
- `config_loader.py`
- `datasets-example`
- `home-assistant/CleanUpInSyncoidSnapshots-mqtt-persistent-notification.yaml`
- `hostnames-example`
- `mqtt_notifications.py`
- `requirements-mqtt.txt`
- `requirements.txt`

## Packaging checks

The final archive is checked for:

- exact project-file manifest equality with the supplied 0.0.5 archive;
- exact project-file manifest equality with the final release source tree;
- ZIP CRC integrity;
- byte-for-byte equality after extracting the final ZIP;
- absence of `__pycache__`, `.pyc`, `.pyo`, virtual environments, generated `logs/`,
  build/cache directories, local credential/config files, and temporary verification files;
- a SHA-256 sidecar generated for the final ZIP.

## What was not fully tested

- No real ZFS pool was modified and no real `zfs destroy` was executed. ZFS behavior is tested
  with mocked command results, including the exact missing-dataset stderr supplied for this issue.
- No real host `mail`/`mailx` delivery was performed; failed-mail selection, subject, and intro
  are covered by lifecycle mocks.
- `paho-mqtt` is not installed here, so the three real loopback QoS/rejection/timeout integration
  tests were skipped. The MQTT implementation itself is unchanged from 0.0.5, and report/worker
  behavior remains covered by mocks.
- No production MQTT broker or credentials were used.
- Home Assistant itself was not installed; its blueprint is byte-for-byte unchanged from 0.0.5
  and continues to be structurally tested against the existing success/failure contract.
- Python 3.10 is not installed in this workspace, so the `tomli` fallback was not executed here;
  Python 3.13 uses standard `tomllib`.
