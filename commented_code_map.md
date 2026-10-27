# Current code map — 0.0.16

This map describes the current implementation. Earlier release behavior is recorded in VERSIONING.md.

All supporting modules are in the `modules/` package. Its `__init__.py` has no startup side effects. Source imports use the package; subprocess workers still launch their resolved file paths and frozen workers relaunch the executable.

## Data flow

`main()` dispatches private workers first, loads one JSON/TOML config, creates a per-run monitor and ID, acquires the live identity lock when publishing live state, and runs the existing cleanup lifecycle. Final live state and completion JSON reflect the cleanup outcome after email and log retention. All locks/monitor handlers are released during finalization.

`run_cleanup()` validates root privileges and reads datasets/hostnames, then prunes each configured dataset under the existing continuation policies. Progress uses datasets as its counting unit. A checked ZFS failure remains an overall failure; remaining datasets are classified as unattempted/skipped when continuation is disabled. Mail/log-retention behavior remains in this runner.

`delete_syncoid_snapshots()` retains the existing snapshot matching, count/age selection and exact one-snapshot-at-a-time destruction. It now supplies listing/deletion/preview phases and current snapshot to the monitor. `run_cmd()` passes actual captured stderr to the bounded diagnostic tail.

`modules/config_loader.py` validates JSON/TOML sections, maps legacy mqtt to completion while preserving its defaults, and validates independent completion/live template configs. It resolves external paths relative to the config and derives a stable per-host/config live ID when omitted.

`modules/mqtt_notifications.py` adapts cleanup arguments and diagnostics to the template builder/publisher. It contains no snapshot operations. `modules/mqtt_status.py` and `modules/ha_live_preview.py` are unchanged template 1.1.0 modules: the former owns completion JSON and delivery, the latter owns live state, discovery, heartbeat, retained result and its independent worker.

## Function/class index

### CleanUpInSyncoidSnapshots.py

- `ReportWarningHandler` — line 21.
- `setup_logger` — line 32.
- `application_base_dir` — line 85.
- `get_script_log_folder` — line 97.
- `script_base_name` — line 109.
- `CommandError` — line 116.
- `DatasetFailuresError` — line 125.
- `is_missing_dataset_error` — line 161.
- `run_cmd` — line 166.
- `get_newest_files` — line 215.
- `read_hostnames` — line 234.
- `send_mail` — line 246.
- `print_separator` — line 264.
- `log_blank_line` — line 273.
- `WasMailSent` — line 276.
- `build_backup_mail_header` — line 290.
- `MailTo` — line 314.
- `parse_syncoid_ts` — line 354.
- `delete_syncoid_snapshots` — line 384.
- `log_dry_run_report` — line 508.
- `delete_old_files` — line 532.
- `main` — line 608.
- `run_cleanup` — line 731.

### modules/config_loader.py

- `parse_older_than` — line 58.
- `_table` — line 77.
- `_required_string` — line 97.
- `_optional_string` — line 105.
- `_boolean` — line 113.
- `_resolve_config_relative` — line 121.
- `load_config` — line 129.

### modules/mqtt_notifications.py

- `should_send_notification` — line 21.
- `resolve_certificates` — line 25.
- `validate_mqtt_config` — line 46.
- `build_mqtt_report` — line 59.
- `notify_mqtt` — line 77.
- `publish_worker` — line 95.

### modules/mqtt_status.py

- `_text` — line 26.
- `_json_text` — line 32.
- `_dataset_list` — line 51.
- `build_report` — line 64.
- `encode_report` — line 134.
- `build_mqtt_status_payload` — line 163.
- `MQTTConfig` — line 173.
- `PublishResult` — line 219.
- `publish_report` — line 228.
- `_publish_once` — line 259.
- `run_worker_if_requested` — line 273.

### modules/ha_live_preview.py

- `_now` — line 28.
- `_json` — line 32.
- `make_device_id` — line 38.
- `LiveConfig` — line 49.
- `discovery_messages` — line 118.
- `LivePreview` — line 177.
- `run_worker_if_requested` — line 441.

## Configuration, HA and packaging

- `config-example.json` / `config-example.toml`: complete safe examples with canonical completion/live options.
- `config-legacy-example.toml`: legacy mqtt form with preserved defaults.
- `payload-examples.json`: valid template completion success/failure/dry-run events.
- `home-assistant/CleanUpInSyncoidSnapshots-mqtt-persistent-notification.yaml`: completion-only receive blueprint with strict schema/result checks and notification controls.
- `home-assistant/CleanUpInSyncoidSnapshots-live-dashboard.yaml`: separate live sensor/progress/diagnostic dashboard.
- `CleanUpInSyncoidSnapshots.spec`: one-file build, automatically includes imported reporting modules and explicitly collects Paho/Tomli.
- `build-pyinstaller.sh`: clean build, executable-only dist guard and version/help smoke checks.
- `tests/test_project.py`: existing cleanup/mail/log/MQTT regression suite updated for the new contract.
- `tests/test_mqtt_status.py` / `tests/test_ha_live_preview.py`: supplied template suites with project-relative test paths.
- `tests/test_template_integration.py`: config, channel independence, adapter progress, failure and policy regressions.
- `tests/test_frozen_workers.py`: both actual executable worker routes and local MQTT delivery.
- `VERIFICATION.md` / `verification/unittest.txt`: performed checks, evidence and limitations.
