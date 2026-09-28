# Verification — CleanUpInSyncoidSnapshots 0.0.8

Verified on 2026-09-28 in the release workspace using Python 3.13.5.
The application targets Linux/ZFS. Destructive ZFS operations were not run.

## Automated results

- **53 tests run: 50 passed and 3 skipped.**
- The three skipped tests are the optional real-Paho loopback MQTT integration tests because
  `paho-mqtt` is not installed in this verification environment.
- New continuation coverage verifies:
  - omitted continuation settings default to `true`;
  - both settings require real TOML booleans;
  - a missing dataset continues by default and still produces final failure mail/MQTT/exit 1;
  - `continue_on_missing_dataset=false` stops before later datasets and still follows the failure
    notification path;
  - another checked ZFS list failure continues by default and still produces final failure;
  - `continue_on_other_failures=false` stops before later datasets;
  - a checked `zfs destroy` failure is covered by `continue_on_other_failures=true`, stops further
    work in the current dataset, and resumes with the next configured dataset;
  - mixed missing/other continued failures are combined in the final MQTT error/stderr report.
- MQTT regression coverage verifies that `publish_dry_run=false` suppresses successful dry-run
  previews only; failure reports still publish when MQTT is enabled.
- Existing retention, root guard, input validation, logging-location, mail-warning, interrupt,
  MQTT report/worker, Home Assistant blueprint, and version/help tests continue to pass.
- `config-example.toml` was checked against `TOP_LEVEL_SECTIONS` and `SECTION_KEYS`; it contains
  every supported setting, defaults to `command = "dry-run"`, defaults both continuation switches
  to `true`, and leaves mail/MQTT disabled.

## Compile, CLI, and documentation checks

- `CleanUpInSyncoidSnapshots.py`, `config_loader.py`, `mqtt_notifications.py`, and
  `tests/test_project.py` compiled successfully in memory without requiring release bytecode.
- Import/version metadata is `__version__ == "0.0.8"`.
- `CleanUpInSyncoidSnapshots.py --help` exits successfully and documents every public flag:
  - `-h, --help`
  - `--version`
  - `-c, --config CONFIG`
- The `-c/--config` help text states that cleanup, retention, continuation, logging, mail, report,
  and MQTT settings come from TOML.
- `CleanUpInSyncoidSnapshots.py --version` prints `CleanUpInSyncoidSnapshots.py 0.0.8` and exits 0
  before configuration loading or cleanup.
- Running the main script with no options still exits 2 and reports that `-c/--config` is required.
- Supplying old operational flags still fails argument parsing; the two continuation switches are
  configuration settings rather than new CLI flags.
- A static AST/documentation audit found every class/function/helper in the three application
  modules and the test module represented in `commented_code_map.md`, including nested helpers.
- Current-behavior source, README, code map, config example, and tests contain no stale 0.0.7
  application-version reference. `VERSIONING.md` retains release history and this verification file
  intentionally refers to the supplied 0.0.7 baseline for manifest comparison.

## Requested behavior verified

1. `continue_on_missing_dataset = true` records an explicit `dataset does not exist` command
   failure, moves to the next configured dataset, and leaves the final result failed.
2. `continue_on_missing_dataset = false` records that failure and stops cleanup immediately.
3. `continue_on_other_failures = true` records other checked ZFS list/destroy failures and moves to
   the next configured dataset. A failed destroy does not continue with later snapshots in the same
   dataset.
4. `continue_on_other_failures = false` records the failure and stops cleanup immediately.
5. Both settings default to `true` when omitted from TOML.
6. Continued failures are accumulated so the final error can identify missing datasets and other
   failed datasets together while preserving original ZFS stderr for the existing MQTT schema.
7. Any dataset-level checked ZFS failure keeps process exit code 1. Enabled mail uses the FAILED
   path. Enabled MQTT reports `status = "failure"` / `exit_code = 1`.
8. MQTT failure reports are published even when the command is `dry-run` and
   `publish_dry_run = false`; that option now controls successful preview reports only.
9. Failed runs do not prune old log groups.
10. Root/config/input/global process failures and interrupts are not converted into recoverable
    per-dataset failures by these settings.

## Safety boundaries retained

- Configuration validation still occurs before ZFS commands.
- Dry-run never calls `zfs destroy` and never deletes old log groups.
- Snapshot matching remains limited to configured datasets, exact configured Syncoid hostnames, and
  the existing timestamp pattern.
- `zfs destroy` still receives exactly one selected snapshot per checked command; no recursive,
  force, wildcard, or shell-expanded destruction was added.
- Continuation changes only whether the outer configured-dataset loop proceeds after a checked ZFS
  command failure. It does not reinterpret the failed command as successful or retry it implicitly.
- Mail and MQTT remain optional notification layers and do not broaden snapshot selection.
- MQTT publishing remains non-retained and timeout-isolated.

## 0.0.7-to-0.0.8 manifest comparison

The supplied 0.0.7 archive contains **17 project files**. The 0.0.8 release contains the same
**17 relative project file paths**. No project file was added or removed.

Changed intentionally:

- `CleanUpInSyncoidSnapshots.py`
- `README.md`
- `VERIFICATION.md`
- `VERSIONING.md`
- `commented_code_map.md`
- `config-example.toml`
- `config_loader.py`
- `mqtt_notifications.py`
- `tests/test_project.py`

Preserved byte-for-byte from the supplied 0.0.7 archive:

- `.github/CODEOWNERS`
- `.gitignore`
- `DISCLAIMER.md`
- `datasets-example`
- `home-assistant/CleanUpInSyncoidSnapshots-mqtt-persistent-notification.yaml`
- `hostnames-example`
- `requirements-mqtt.txt`
- `requirements.txt`

## Packaging checks

The final archive is checked for:

- exact project-file manifest equality with the supplied 0.0.7 archive;
- exact project-file manifest equality with the final 0.0.8 source tree;
- ZIP CRC integrity;
- byte-for-byte equality after extracting the final ZIP;
- executable mode preservation for `CleanUpInSyncoidSnapshots.py`;
- absence of `__pycache__`, `.pyc`, `.pyo`, generated `logs/`, build/cache directories, local
  credential/config files, and temporary verification files;
- a SHA-256 sidecar generated for the final ZIP.

## What was not fully tested

- No real ZFS pool was modified and no real `zfs destroy` was executed. ZFS continuation and final
  failure behavior are covered with mocked checked command results, including list, missing-dataset,
  permission-style, mixed, and destroy-failure cases.
- No real host `mail`/`mailx` delivery was performed; selection of failure/success mail paths and mail
  failure handling are covered by mocks.
- `paho-mqtt` is not installed here, so the three real loopback QoS/rejection/timeout integration
  tests were skipped. MQTT config/report/worker behavior remains covered by non-network tests.
- No production MQTT broker or credentials were used.
- Home Assistant itself was not installed; the packaged blueprint is structurally tested against the
  current MQTT JSON contract.
- Python 3.10 is not installed in this workspace, so the `tomli` fallback could not be executed;
  Python 3.13.5 used standard-library `tomllib`.
