# Verification — CleanUpInSyncoidSnapshots 0.0.4

Verified on 2026-09-16 in the release workspace using Python 3.13.5.
The application targets Linux/ZFS. Destructive ZFS operations were not run.

## Automated results

- **41 tests run: 38 passed and 3 skipped.**
- The three skipped tests are the optional real-Paho loopback MQTT integration tests
  because `paho-mqtt` is not installed in this verification environment.
- A new log-location regression confirms that the program resolves the actual script
  through a symlink, creates `<actual-script-dir>/logs/`, and creates both the `.log`
  and `.err` files inside that folder.
- TOML schema/default/path tests passed, including coverage of every supported setting
  in `config-example.toml`.
- Lifecycle tests passed for normal success, MQTT-disabled operation, root rejection,
  command failure diagnostics, missing input files, finalization failure, nonfatal mail
  failure/warning reporting, keyboard interrupt, and invalid config rejection.
- Snapshot/log retention regression tests passed with ZFS commands mocked.
- Home Assistant blueprint structural tests passed.

## Compile and CLI checks

- `CleanUpInSyncoidSnapshots.py`, `config_loader.py`, `mqtt_notifications.py`, and
  `tests/test_project.py` compiled successfully in memory without generating bytecode.
- Importing the application reports `__version__ == "0.0.4"`.
- Running the main script with no options exits 2 and shows required usage
  `CleanUpInSyncoidSnapshots.py -c CONFIG`.
- Supplying an old operational option such as `--command dry-run` exits 2 with an
  `unrecognized arguments` error; cleanup is not entered.
- The public main application parser still exposes only `-c CONFIG`.

## Log-location fix checks

- `get_script_log_folder()` uses `os.path.realpath(__file__)` and therefore anchors
  logging to the actual script file rather than the current working directory or a
  symlink launcher directory.
- The directory is always `<actual-script-dir>/logs` and is created with
  `os.makedirs(..., exist_ok=True)`.
- There is no `/tmp` or other temporary-directory fallback in the application.
- If the script-local log directory cannot be created, the run raises an error instead
  of silently relocating its log files.
- Existing log filenames, `.log`/`.err` pairing, retention, and mail attachment lookup
  still use the same resolved `log_folder`.

## 0.0.3-to-0.0.4 manifest comparison

The 0.0.3 input archive contained **16 files**. The 0.0.4 release also contains
**16 files**. No project file was added or removed.

Changed intentionally:

- `CleanUpInSyncoidSnapshots.py`
- `README.md`
- `VERIFICATION.md`
- `VERSIONING.md`
- `commented_code_map.md`
- `config-example.toml`
- `tests/test_project.py`

Preserved byte-for-byte from 0.0.3:

- `.github/CODEOWNERS`
- `DISCLAIMER.md`
- `config_loader.py`
- `datasets-example`
- `home-assistant/CleanUpInSyncoidSnapshots-mqtt-persistent-notification.yaml`
- `hostnames-example`
- `mqtt_notifications.py`
- `requirements-mqtt.txt`
- `requirements.txt`

## Packaging checks

The final archive is checked for ZIP CRC integrity and byte-for-byte equality against
its release source tree after extraction. It must contain no `__pycache__`, `.pyc`,
`.pyo`, virtual environment, generated `logs/`, build/cache directories, local credential
files, or temporary verification files. A SHA-256 sidecar is generated for the ZIP.

## What was not fully tested

- No real `zfs destroy` was executed; destructive ZFS behavior is covered with mocks and
  its existing command construction/selection logic is unchanged.
- No real mail server or host `mail` delivery was exercised.
- `paho-mqtt` is not installed here, so the three real loopback QoS/rejection/timeout
  integration tests were skipped. MQTT worker/auth/TLS/timeout paths remain covered by mocks.
- No production MQTT broker or credentials were used.
- Home Assistant itself was not installed, so the automation/blueprint was parsed and
  structurally tested rather than executed in a live instance.
- Python 3.10 is not installed in this workspace, so the `tomli` fallback could not be
  executed directly here; Python 3.13 uses standard `tomllib`.
