# Commented code map — CleanUpInSyncoidSnapshots 0.0.4

This file explains the current implementation. It is not a version history; release changes belong in `VERSIONING.md`.

## `CleanUpInSyncoidSnapshots.py`

| Function/class | What it does and why |
| --- | --- |
| `ReportWarningHandler` | Logging handler used only when MQTT is enabled. It remembers that an ERROR-level message occurred so a run that still exits successfully can publish `warning: true`, even if log retention later deletes the original error file. |
| `ReportWarningHandler.__init__` | Stores the shared lifecycle state and configures the handler for ERROR and above. |
| `ReportWarningHandler.emit` | Sets `state["warning"] = True`; it deliberately does not duplicate message output. |
| `setup_logger` | Creates the main DEBUG-file/INFO-console logger and separate ERROR-file/ERROR-console logger, returning the error-file path for final empty-file cleanup. |
| `setup_logger._build_logger` | Shared nested helper that resets an existing named logger, applies the formatter, and attaches the requested handlers so repeated test/app invocations do not accumulate handlers. |
| `get_script_log_folder` | Resolves the actual directory containing `CleanUpInSyncoidSnapshots.py`, creates its `logs/` child directory, and always returns that path. There is deliberately no `/tmp` fallback so log location is deterministic and permission failures are visible. |
| `script_base_name` | Produces a filesystem-safe basename from the script filename for default log naming. |
| `CommandError` | Carries failed command, return code, stdout, and stderr so failures retain useful diagnostics for logging and MQTT reporting. |
| `CommandError.__init__` | Stores command diagnostics and builds the human-readable failure message. |
| `run_cmd` | Executes ZFS commands without a shell, captures stdout/stderr, logs details, and raises `CommandError` on checked nonzero exit. Keeping argv as a list avoids shell interpolation. |
| `get_newest_files` | Finds the newest `.log` and `.err` files for the configured prefix so email can attach/read the current report files. |
| `read_hostnames` | Reads exact Syncoid hostnames, ignoring blank lines and whole-line `#` comments. |
| `send_mail` | Invokes the host `mail` command with subject and optional attachments placed before the recipient for broad mail/mailx compatibility. |
| `print_separator` | Writes a visual separator to normal or error logging for readable reports. |
| `log_blank_line` | Adds a blank informational log line without repeating formatting code. |
| `WasMailSent` | Logs whether the external mail command succeeded; mail failure itself remains nonfatal to the cleanup result. |
| `build_backup_mail_header` | Builds the optional title/comment block shared by success and failure email bodies. |
| `MailTo` | Collects the newest log/error files, assembles body text, calls `send_mail`, and records delivery outcome. |
| `parse_syncoid_ts` | Parses Syncoid's timestamp suffix including signed or signless positive GMT offsets and returns a timezone-aware datetime for safe UTC comparison. |
| `delete_syncoid_snapshots` | Lists snapshots for one explicit dataset, matches only configured Syncoid hosts, sorts newest-first, applies retain/age protection, previews or destroys selected snapshots one at a time, and stops on checked ZFS failures. |
| `delete_old_files` | Applies the existing shared retention policy to timestamp-paired `.log`/`.err` groups. In dry-run it only reports candidates. |
| `main` | Public entry point. Parses only `-c CONFIG`, loads/validates TOML before cleanup, runs the existing lifecycle, preserves exit/exception behavior, and sends one optional final MQTT report after finalization. |
| `run_cleanup` | Existing cleanup lifecycle reused by the TOML interface: logger setup, root guard, input-file loading, dry-run/delete processing, optional mail, log retention, and empty `.err` cleanup. |
| Imported `parse_older_than` | Re-exported from `config_loader.py` so existing callers/tests can still use `CleanUpInSyncoidSnapshots.parse_older_than` while parsing logic lives with configuration validation. |

## `config_loader.py`

| Function/constant | What it does and why |
| --- | --- |
| `TOP_LEVEL_SECTIONS` | Exact accepted TOML sections. Unknown sections are rejected to catch misspelled configuration before destructive work. |
| `SECTION_KEYS` | Exact accepted keys in each section. This is also used by tests to ensure `config-example.toml` documents every supported setting. |
| `parse_older_than` | Converts `Nd`, `Nw`, or `Nm` into `timedelta`, preserving the original 30-day-month rule. Empty/optional handling is done by `load_config`. |
| `_table` | Reads one TOML table, verifies its type, enforces required sections, and rejects unknown keys. |
| `_required_string` | Validates nonempty string settings such as command and required file paths without coercing wrong TOML types. |
| `_optional_string` | Validates optional string settings such as report text and log prefix while allowing empty values. |
| `_boolean` | Requires real TOML booleans rather than accepting integer lookalikes. |
| `_resolve_config_relative` | Expands `~` and resolves relative paths against the TOML file directory so service/cron current working directory does not change which input/certificate file is used. |
| `load_config` | Opens TOML with `tomllib`/`tomli`, validates all application sections, converts age and defaults, maps mail/MQTT opt-ins, validates enabled MQTT settings, and returns an `argparse.Namespace` matching the fields expected by the existing cleanup/report functions. All of this occurs before ZFS work. |
| `tomllib` / `tomli` import fallback | Python 3.11+ uses the standard library; Python 3.10 falls back to the dependency in `requirements.txt` to preserve the project's prior Python 3.10 minimum. |

## `mqtt_notifications.py`

| Function/constant | What it does and why |
| --- | --- |
| `DEFAULTS` | MQTT defaults for port, credentials, client ID, QoS, timeout, TLS paths, and dry-run publishing. |
| `validate_mqtt_config` | Validates the enabled `[mqtt]` TOML settings, rejects unknown/wrong types and wildcard publish topics, normalizes empty optional strings to absent values, enforces username/password and certificate/key relationships, and resolves certificate files relative to the TOML directory. |
| `build_mqtt_report` | Produces the stable Home Assistant-facing JSON schema using cleanup result, report metadata, warning state, command, version, and bounded command diagnostics. |
| `notify_mqtt` | Skips disabled/dry-run-suppressed reports, then starts a separate Python worker with config/report on stdin and a hard timeout. Publisher failure is logged but cannot change the cleanup exit result. |
| `publish_worker` | Internal Paho one-shot MQTT 3.1.1 publisher. Builds auth/TLS context, publishes with configured QoS, and always uses `retain=False`. |
| `if __name__ == "__main__"` worker gate | Accepts only the internal `--publish` argument. This is not a public application option; normal users run `CleanUpInSyncoidSnapshots.py -c CONFIG`. Unexpected worker arguments exit immediately. |

## `tests/test_project.py`

### Shared helpers

| Function | What it verifies/enables |
| --- | --- |
| `arguments` | Builds representative runtime values for MQTT report tests without invoking cleanup. |
| `write_config` | Creates temporary TOML/input files so lifecycle tests exercise the real new `-c CONFIG` path while ZFS/mail remain mocked. |
| `receive_packet` | Decodes a complete MQTT packet from the loopback integration fixture. |
| `receive_packet.read_exact` | Handles partial socket reads and detects disconnects while decoding MQTT packets. |

### `TomlConfigTests`

| Test | Purpose |
| --- | --- |
| `test_example_contains_every_supported_setting` | Ensures `config-example.toml` has every supported section/key and no undocumented extras. |
| `test_example_loads_and_is_safe_by_default` | Confirms the packaged example parses, defaults to dry-run, leaves mail/MQTT disabled, and resolves paths correctly. |
| `test_defaults_and_negative_retain_compatibility` | Confirms optional defaults and preservation of negative-retain normalization to zero. |
| `test_invalid_cleanup_and_unknown_keys_are_rejected` | Confirms invalid commands/types, misspelled keys, and unknown sections fail before cleanup. |
| `test_mail_requires_recipient_only_when_enabled` | Confirms explicit mail enablement cannot proceed without a recipient. |
| `test_relative_paths_are_config_relative` | Confirms dataset/hostname paths follow the TOML file rather than current working directory. |
| `test_cli_accepts_only_config_option` | Confirms an old CLI option is rejected and cleanup is not called. |

### `MqttConfigTests`

| Test/helper | Purpose |
| --- | --- |
| `validate` | Supplies valid minimal broker/topic settings around each MQTT validation test. |
| `test_defaults` | Confirms MQTT defaults and empty credential normalization. |
| `test_plain_string_password_is_supported` | Protects the intended simple TOML `password = "<String>"` behavior. |
| `test_invalid_options` | Rejects invalid port/QoS/timeout/TLS/auth/certificate/client-ID combinations and unknown keys. |
| `test_invalid_topic_and_shape` | Rejects non-table input, wildcard topics, and empty topics. |
| `test_relative_certificate_paths` | Confirms certificate files are resolved relative to the TOML directory. |

### `ReportTests`

| Test | Purpose |
| --- | --- |
| `test_success_schema_and_types` | Protects MQTT success status/type contract and JSON serializability. |
| `test_failure_command_diagnostics` | Confirms command failures include useful bounded stderr. |
| `test_fallback_title_and_output_limit` | Confirms blank title fallback and 4096-character diagnostic bound. |
| `test_disabled_and_default_dry_run_do_not_launch_worker` | Confirms disabled MQTT and default dry-run suppression do no publish work. |
| `test_worker_input_and_timeout` | Confirms secrets are not placed on the worker command line and timeout is applied. |
| `test_dry_run_requires_explicit_publish_opt_in` | Confirms dry-run publishing requires `publish_dry_run=true`. |
| `test_delivery_failure_is_logged_and_secret_not_echoed` | Confirms publisher failures are nonfatal and worker stderr is not copied into logs where credentials could leak. |
| `test_timeout_is_nonfatal` | Confirms a stuck publisher is bounded and only logged. |
| `test_worker_tls_and_auth` | Verifies Paho receives the configured TLS context and username/password. |

### `BlueprintTests`

| Test/helper | Purpose |
| --- | --- |
| `setUp` | Loads the packaged Home Assistant blueprint text for structural checks. |
| `test_blueprint_is_receive_only_mqtt_reporter` | Confirms MQTT receive + persistent notification behavior and absence of publish/ZFS commands. |
| `test_blueprint_validates_cleanup_report_contract` | Confirms the blueprint consumes the fields produced by `build_mqtt_report`. |
| `test_blueprint_notification_controls_are_present` | Confirms success/warning/failure/dry-run and replacement controls remain available. |

### `LifecycleTests`

| Test/helper | Purpose |
| --- | --- |
| `invoke` | Runs real `main()`/TOML/lifecycle flow with temporary files and safe mocks for ZFS, log cleanup, mail, and MQTT. |
| `test_success_final_report` | Confirms a successful delete lifecycle emits MQTT success. |
| `test_original_mode_needs_no_mqtt` | Confirms disabled MQTT performs no MQTT call and cleanup still runs. |
| `test_root_rejection_reports_failure` | Confirms root guard stops before ZFS and is reported as failure when MQTT is enabled. |
| `test_command_failure_reports_stderr` | Confirms a ZFS command failure remains the raised error and reaches MQTT diagnostics. |
| `test_missing_input_reports_failure_before_zfs` | Confirms missing dataset files fail before any ZFS command. |
| `test_finalization_failure_cannot_report_success` | Confirms log-finalization failure cannot be mislabeled successful. |
| `test_mail_warning_is_nonfatal` | Confirms mail failure leaves cleanup successful but sets MQTT warning. |
| `test_interrupt_is_never_success` | Confirms keyboard interrupt reports exit 130/failure. |
| `test_invalid_config_stops_before_cleanup` | Confirms enabled MQTT with incomplete settings is rejected during config parsing, before `run_cleanup`. |

### `RetentionTests`

| Test/helper | Purpose |
| --- | --- |
| `prune` | Captures safe mocked ZFS command sequences for retention assertions. |
| `test_matching_count_and_dry_run` | Protects host matching, count retention, and dry-run no-destroy behavior. |
| `test_original_no_retention_behavior_is_preserved` | Explicitly protects the existing behavior where no age + retain 0 selects every matching snapshot. |
| `test_age_and_count_work_together` | Protects combined age/count selection. |
| `test_log_dry_run_and_group_retention` | Protects paired log-group retention and dry-run no-delete behavior. |

### `BrokerIntegrationTests`

| Test/helper | Purpose |
| --- | --- |
| `exchange` | Starts a loopback-only miniature MQTT broker fixture and invokes the real isolated Paho publisher. |
| `exchange.serve` | Accepts the client, sends success/rejection/stall responses, captures publish topic/payload/flags, and performs QoS acknowledgements. |
| `test_real_qos_0_1_2_delivery` | Verifies actual Paho QoS 0/1/2 loopback delivery and non-retained messages when Paho is installed. |
| `test_broker_rejection` | Confirms broker rejection is logged by the parent and does not leak into cleanup outcome. |
| `test_stalled_broker_is_killed_at_timeout` | Confirms stalled publisher work is terminated within the configured timeout. |

## Public and internal commands

| Command | What it does and why |
| --- | --- |
| `sudo python3 CleanUpInSyncoidSnapshots.py -c config.toml` | **Only public application invocation.** `-c` selects the TOML file; every operational setting comes from it. |
| `sudo .venv/bin/python CleanUpInSyncoidSnapshots.py -c config.toml` | Same invocation when using the documented virtual environment. |
| `zfs list -H -t snapshot -o name DATASET` | Lists snapshot names for one explicit dataset in machine-readable form; no recursive dataset traversal is requested. |
| `zfs destroy SNAPSHOT` | Deletes exactly one selected snapshot. No `-r`, force, wildcard, or shell expansion is used. |
| `mail -s SUBJECT [--attach FILE ...] RECIPIENT` | Optional external mail delivery using the current log/error files. |
| `python -B mqtt_notifications.py --publish` | Internal timeout-isolated MQTT worker launched only by `notify_mqtt`; credentials/report arrive on stdin. |
| `python3 -m venv .venv` | Creates an isolated Python environment when desired. |
| `.venv/bin/python -m pip install -r requirements.txt` | Installs `tomli` only when Python <3.11 requires it. |
| `.venv/bin/python -m pip install -r requirements-mqtt.txt` | Installs base requirements plus optional Paho MQTT. |
| `cp config-example.toml config.toml` | Creates a local editable config from the complete reference. |
| `chmod 600 config.toml` | Protects a config that may hold MQTT credentials and mail destinations. |
| `python3 -B -m unittest discover -s tests -v` | Runs safe regression tests; ZFS/mail are mocked, and real MQTT tests use loopback only. |

## Files

| File | Why it exists |
| --- | --- |
| `CleanUpInSyncoidSnapshots.py` | Public application entry point and retained cleanup/email/log logic. |
| `config_loader.py` | Single-TOML parsing and validation boundary before destructive work. |
| `config-example.toml` | Complete commented reference for every supported runtime setting. |
| `mqtt_notifications.py` | Optional status-report validation and isolated publisher. |
| `requirements.txt` | Python 3.10 TOML parser compatibility dependency. |
| `requirements-mqtt.txt` | Optional Paho dependency plus base requirements. |
| `datasets-example` | Original dataset-list example. |
| `hostnames-example` | Original hostname-list example. |
| `home-assistant/CleanUpInSyncoidSnapshots-mqtt-persistent-notification.yaml` | Receive-only example blueprint for final MQTT reports. |
| `tests/test_project.py` | Regression and loopback integration tests. |
| `README.md` | Current usage/configuration documentation only. |
| `VERSIONING.md` | Release history and version policy. |
| `VERIFICATION.md` | Evidence and test limitations for the packaged release. |
| `DISCLAIMER.md` | Existing liability/data-loss warning. |
| `.github/CODEOWNERS` | Existing repository ownership metadata. |

## Safety boundaries retained

- Configuration validation occurs before `run_cleanup` and therefore before ZFS commands.
- The ZFS runner uses argument lists, never a shell command string.
- Dry-run never calls `zfs destroy` and never removes old log groups.
- Snapshot matching remains limited to exact configured hostnames and the existing Syncoid timestamp pattern.
- `zfs destroy` remains one snapshot at a time with checked failure handling.
- Mail and MQTT remain optional notification layers; neither can make snapshot-selection logic broader.
- MQTT publishing stays in a separate timeout-bounded worker and remains non-retained.
