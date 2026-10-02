# Commented code map — CleanUpInSyncoidSnapshots 0.0.14

This file explains the current implementation. It is not a version history; release changes belong in `VERSIONING.md`.

## `CleanUpInSyncoidSnapshots.py`

| Function/class | What it does and why |
| --- | --- |
| `ReportWarningHandler` | Logging handler used only when MQTT is enabled. It remembers that an ERROR-level message occurred so a run that still exits successfully can publish `warning: true`, even if log retention later deletes the original error file. |
| `ReportWarningHandler.__init__` | Stores the shared lifecycle state and configures the handler for ERROR and above. |
| `ReportWarningHandler.emit` | Sets `state["warning"] = True`; it deliberately does not duplicate message output. |
| `setup_logger` | Creates the main DEBUG-file/INFO-console logger and separate ERROR-file/ERROR-console logger, returning the error-file path for final empty-file cleanup. |
| `setup_logger._build_logger` | Shared nested helper that resets an existing named logger, applies the formatter, and attaches the requested handlers so repeated test/app invocations do not accumulate handlers. |
| `application_base_dir` | Returns the persistent runtime directory. Source runs use the real script directory; PyInstaller-frozen runs use the real executable directory instead of PyInstaller's temporary one-file extraction directory. This keeps logs beside the installed app. |
| `get_script_log_folder` | Creates and returns the `logs/` child of `application_base_dir`. There is deliberately no `/tmp` or current-directory fallback, so both source and frozen builds have deterministic log placement and permission failures remain visible. |
| `script_base_name` | Produces a filesystem-safe basename from the source script or, when frozen, from the real executable name for default log naming. |
| `CommandError` | Carries failed command, return code, stdout, and stderr so failures retain useful diagnostics for logging and MQTT reporting. |
| `CommandError.__init__` | Stores command diagnostics and builds the human-readable failure message. |
| `DatasetFailuresError` | Represents one or more dataset-level checked ZFS failures for final reporting. It can combine explicit missing-dataset failures and other list/destroy failures without changing the existing MQTT schema. |
| `DatasetFailuresError.__init__` | Stores each dataset/kind/`CommandError`, combines original stderr diagnostics, separates missing from other failures in the human-readable summary, and exposes combined `stderr` for MQTT. |
| `is_missing_dataset_error` | Recognizes only ZFS command failures whose stderr explicitly contains `dataset does not exist`; `run_cleanup` uses that classification to choose the matching continuation option. |
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
| `delete_syncoid_snapshots` | Lists snapshots for one explicit dataset, matches only configured Syncoid hosts, sorts newest-first, applies retain/age protection, and previews or destroys selected snapshots one at a time. It returns the matched/selected counts so dry-run reporting reuses the actual selection logic. Checked list/destroy failures propagate to `run_cleanup`; a failed destroy stops further work inside that dataset before any configured outer-loop continuation. |
| `log_dry_run_report` | Writes the final aggregate dry-run summary after snapshot selection and, on successful dry-runs, after old-log retention preview. The summary is written before optional success mail so the email body/attachment includes it. |
| `delete_old_files` | Applies the existing shared retention policy to timestamp-paired `.log`/`.err` groups. It returns matched/selected group and selected-file counts for the final report; in dry-run it only reports candidates and never removes files. |
| `main` | Public entry point. Before public argument parsing, a private frozen-worker environment marker can route a PyInstaller child process directly into `publish_worker`; report/config data still arrives on stdin. Normal invocations provide standard `-h/--help` and `--version`, accept equivalent `-c CONFIG` / `--config CONFIG`, reject old operational flags, load/validate TOML before cleanup, preserve exit/exception behavior, and build the final MQTT report after finalization. Before calling MQTT it applies the shared success/failure gate, so successful delete and dry-run runs with `mqtt.on_success=false` never enter the notifier. The help/version actions exit before config loading or destructive work. |
| `run_cleanup` | Cleanup lifecycle reused by the TOML interface: logger setup, root guard, input-file loading, dry-run/delete processing, optional mail, log retention, and empty `.err` cleanup. It aggregates dry-run snapshot counts, previews old-log retention before the final dry-run report on successful previews, applies identical mail success gating to delete and dry-run, and logs `Success mail report suppressed by mail.on_success=false.` on either successful mode when mail is enabled but success reporting is disabled. It records/classifies dataset failures, applies continuation settings, and prunes old logs destructively only after a successful delete run. |
| Imported `parse_older_than` | Re-exported from `config_loader.py` so existing callers/tests can still use `CleanUpInSyncoidSnapshots.parse_older_than` while parsing logic lives with configuration validation. |

## `config_loader.py`

| Function/constant | What it does and why |
| --- | --- |
| `TOP_LEVEL_SECTIONS` | Exact accepted TOML sections. Unknown sections are rejected to catch misspelled configuration before destructive work. |
| `SECTION_KEYS` | Exact accepted keys in each section, including both cleanup continuation booleans and matching `on_success` switches for mail/MQTT. Tests use it to ensure `config-example.toml` documents every supported setting. |
| `parse_older_than` | Converts `Nd`, `Nw`, or `Nm` into `timedelta`, preserving the original 30-day-month rule. Empty/optional handling is done by `load_config`. |
| `_table` | Reads one TOML table, verifies its type, enforces required sections, rejects unknown keys, and gives a targeted migration error when obsolete `mqtt.publish_dry_run` is found. |
| `_required_string` | Validates nonempty string settings such as command and required file paths without coercing wrong TOML types. |
| `_optional_string` | Validates optional string settings such as report text and log prefix while allowing empty values. |
| `_boolean` | Requires real TOML booleans rather than accepting integer lookalikes. |
| `_resolve_config_relative` | Expands `~` and resolves relative paths against the TOML file directory so service/cron current working directory does not change which input/certificate file is used. |
| `load_config` | Opens TOML with `tomllib`/`tomli`, validates all application sections, converts age/defaults, defaults both continuation switches to `true`, maps mail `on_success`, validates enabled MQTT settings including MQTT `on_success`, and returns the runtime namespace before any ZFS work. |
| `tomllib` / `tomli` import fallback | Python 3.11+ uses the standard library; Python 3.10 falls back to the dependency in `requirements.txt` to preserve the project's prior Python 3.10 minimum. |

## `mqtt_notifications.py`

| Function/constant | What it does and why |
| --- | --- |
| `DEFAULTS` | MQTT defaults for port, credentials, client ID, QoS, timeout, TLS paths, and success publishing (`on_success=false`). |
| `should_send_notification` | Single shared notification-policy helper used by both the main mail lifecycle and MQTT lifecycle. It returns true for every failure, and for success only when the channel's `on_success=true`, preventing dry-run from having a separate success rule. |
| `validate_mqtt_config` | Validates the enabled `[mqtt]` TOML settings, rejects unknown/wrong types and wildcard publish topics, normalizes empty optional strings to absent values, enforces username/password and certificate/key relationships, and resolves certificate files relative to the TOML directory. |
| `build_mqtt_report` | Produces the Home Assistant-facing JSON schema using cleanup result, report metadata, warning state, command, version, and bounded command diagnostics. Dry-run payloads additionally receive the aggregate `dry_run_report` object supplied by the cleanup lifecycle. |
| `notify_mqtt` | Defensive MQTT notification wrapper. It re-applies `should_send_notification` so a successful report with `mqtt.on_success=false` cannot launch the publisher even if a caller bypasses the main lifecycle gate. In source mode it starts `mqtt_notifications.py --publish`; in a PyInstaller build it relaunches the same frozen executable with a private environment marker. Both forms pass config/report on stdin, enforce the hard timeout, keep credentials off argv, and leave cleanup outcome unchanged if publishing fails. |
| `publish_worker` | Internal Paho one-shot MQTT 3.1.1 publisher. Builds auth/TLS context, publishes with configured QoS, and always uses `retain=False`. |
| `if __name__ == "__main__"` worker gate | Accepts only the internal `--publish` argument. This is not a public application option; normal users run `CleanUpInSyncoidSnapshots.py -c CONFIG`. Unexpected worker arguments exit immediately. |

## `tests/test_project.py`

### Shared helpers

| Function | What it verifies/enables |
| --- | --- |
| `arguments` | Builds representative runtime values for MQTT report tests without invoking cleanup. |
| `write_config` | Creates temporary TOML/input files so lifecycle tests exercise the real configuration-selector path while ZFS/mail remain mocked. |
| `receive_packet` | Decodes a complete MQTT packet from the loopback integration fixture. |
| `receive_packet.read_exact` | Handles partial socket reads and detects disconnects while decoding MQTT packets. |

### `TomlConfigTests`

| Test | Purpose |
| --- | --- |
| `test_example_contains_every_supported_setting` | Ensures `config-example.toml` has every supported section/key and no undocumented extras. |
| `test_example_loads_and_is_safe_by_default` | Confirms the packaged example parses, defaults to dry-run, leaves mail/MQTT disabled, and resolves paths correctly. |
| `test_defaults_and_negative_retain_compatibility` | Confirms optional defaults, both continuation defaults are `true` when omitted, and negative-retain normalization remains zero. |
| `test_invalid_cleanup_and_unknown_keys_are_rejected` | Confirms invalid commands/types, misspelled keys, and unknown sections fail before cleanup. |
| `test_continuation_options_require_real_booleans` | Confirms both continuation settings accept only real TOML booleans and reject integer lookalikes. |
| `test_mail_requires_recipient_only_when_enabled` | Confirms explicit mail enablement cannot proceed without a recipient. |
| `test_relative_paths_are_config_relative` | Confirms dataset/hostname paths follow the TOML file rather than current working directory. |
| `test_cli_rejects_old_operational_options` | Confirms an old operational CLI option is rejected and cleanup is not called. |
| `test_cli_help_is_available_without_cleanup` | Confirms standard `-h/--help` is available, documents `--version` plus both configuration spellings, shows examples, exits 0, and never enters cleanup. |
| `test_cli_version_is_available_without_cleanup` | Confirms `--version` prints the current application version, exits 0, and never enters cleanup or configuration loading. |
| `test_gitignore_keeps_examples_and_excludes_release_artifacts` | Guards the release rules that shipped examples remain explicitly unignored, malformed spaced negation rules are absent, and Python cache/build/temp artifacts are covered by repository ignore patterns. |
| `test_cli_long_config_alias_loads_same_toml` | Confirms `--config CONFIG` loads the same TOML path and reaches the same cleanup lifecycle as `-c CONFIG`. |

### `MqttConfigTests`

| Test/helper | Purpose |
| --- | --- |
| `validate` | Supplies valid minimal broker/topic settings around each MQTT validation test. |
| `test_defaults` | Confirms MQTT defaults and empty credential normalization. |
| `test_plain_string_password_is_supported` | Protects the intended simple TOML `password = "<String>"` behavior. |
| `test_invalid_options` | Rejects invalid port/QoS/timeout/TLS/auth/certificate/client-ID combinations and unknown keys. |
| `test_invalid_topic_and_shape` | Rejects non-table input, wildcard topics, and empty topics. |
| `test_removed_publish_dry_run_has_clear_migration_error` | Confirms obsolete `mqtt.publish_dry_run` fails with a direct migration message pointing to `mqtt.on_success`. |
| `test_relative_certificate_paths` | Confirms certificate files are resolved relative to the TOML directory. |

### `ReportTests`

| Test | Purpose |
| --- | --- |
| `test_success_schema_and_types` | Protects MQTT success status/type contract and JSON serializability. |
| `test_dry_run_report_summary_is_included_in_mqtt_payload` | Confirms the aggregate dry-run summary is preserved in published MQTT JSON. |
| `test_failure_command_diagnostics` | Confirms command failures include useful bounded stderr. |
| `test_fallback_title_and_output_limit` | Confirms blank title fallback and 4096-character diagnostic bound. |
| `test_shared_notification_gate` | Verifies the one shared truth table: failures always notify; successes notify only when `on_success=true`. |
| `test_disabled_and_default_success_reports_do_not_launch_worker` | Confirms disabled MQTT and default-suppressed success reports for both delete and dry-run do not launch the publisher. |
| `test_worker_input_and_timeout` | Confirms secrets are not placed on the worker command line and timeout is applied. |
| `test_failures_publish_for_delete_and_dry_run_when_success_reports_are_disabled` | Confirms failures publish for both delete and dry-run whenever MQTT is enabled, even with `on_success=false`. |
| `test_success_requires_same_explicit_opt_in_for_delete_and_dry_run` | Confirms the same `mqtt.on_success=true` opt-in enables successful delete and successful dry-run reports. |
| `test_delivery_failure_is_logged_and_secret_not_echoed` | Confirms publisher failures are nonfatal and worker stderr is not copied into logs where credentials could leak. |
| `test_timeout_is_nonfatal` | Confirms a stuck publisher is bounded and only logged. |
| `test_worker_tls_and_auth` | Verifies Paho receives the configured TLS context and username/password. |

### `FrozenBuildTests`

| Test | Purpose |
| --- | --- |
| `test_frozen_runtime_paths_use_real_executable_directory` | Confirms one-file builds use the installed executable directory, not PyInstaller's temporary extraction directory, for persistent runtime paths and default naming. |
| `test_frozen_mqtt_worker_relaunches_same_executable_with_private_marker` | Confirms frozen MQTT delivery relaunches the same executable, uses the private worker marker, sends report/config through stdin, and does not place credentials on argv. |
| `test_internal_frozen_worker_bypasses_public_cli_parser` | Confirms the private frozen worker route calls `publish_worker` directly and never enters normal config loading or public argument parsing. |
| `test_pyinstaller_build_files_bundle_runtime_dependencies` | Confirms build requirements include MQTT, Tomli and PyInstaller; the spec explicitly collects Paho/Tomli modules; and the build script starts with an empty `dist/`, explicitly targets that directory, enforces that the only final entry is the executable, and smoke-tests it without a second `bin/` copy. |

### `BlueprintTests`

| Test/helper | Purpose |
| --- | --- |
| `setUp` | Loads the packaged Home Assistant blueprint text for structural checks. |
| `test_blueprint_is_receive_only_mqtt_reporter` | Confirms MQTT receive + persistent notification behavior and absence of publish/ZFS commands. |
| `test_blueprint_validates_cleanup_report_contract` | Confirms the blueprint consumes the base report plus dry-run summary fields produced by `build_mqtt_report`. |
| `test_blueprint_notification_controls_are_present` | Confirms success/warning/failure/dry-run and replacement controls remain available. |

### `LifecycleTests`

| Test/helper | Purpose |
| --- | --- |
| `invoke` | Runs real `main()`/TOML/lifecycle flow with temporary files and safe mocks for ZFS, log cleanup, mail, and MQTT. |
| `test_success_final_report` | Confirms a successful delete lifecycle emits MQTT success. |
| `test_dry_run_final_report_contains_zero_destructive_actions` | Confirms a successful dry-run carries the aggregate report and records no destructive actions. |
| `test_success_mail_is_suppressed_for_delete_and_dry_run_by_default` | Confirms mail success notifications are silent for both modes when `mail.on_success=false`. |
| `test_mail_success_suppression_message_is_logged_for_delete_and_dry_run` | Confirms the exact mail suppression report line is logged on successful delete and successful dry-run when `mail.on_success=false`. |
| `test_success_dry_run_suppresses_both_mail_and_mqtt_when_on_success_is_false` | End-to-end lifecycle regression for the reported bug: a successful dry-run with both channels enabled and both `on_success=false` invokes neither mail nor MQTT notifier. |
| `test_failed_dry_run_still_sends_both_channels_when_on_success_is_false` | Confirms the stronger success gate does not weaken failure reporting: a failed dry-run still invokes both enabled channels with `on_success=false`. |
| `test_dry_run_success_mail_requires_on_success_and_uses_report_subject` | Confirms successful dry-run mail requires opt-in and uses the dry-run report subject/body. |
| `test_dry_run_failure_mail_ignores_on_success_setting` | Confirms failed dry-runs mail whenever mail is enabled even with `on_success=false`. |
| `test_original_mode_needs_no_mqtt` | Confirms disabled MQTT performs no MQTT call and cleanup still runs. |
| `test_root_rejection_reports_failure` | Confirms root guard stops before ZFS and is reported as failure when MQTT is enabled. |
| `test_command_failure_reports_stderr` | Confirms a dataset-level checked ZFS failure is summarized as final failure and its original stderr reaches MQTT diagnostics. |
| `test_missing_input_reports_failure_before_zfs` | Confirms missing dataset files fail before any ZFS command. |
| `test_missing_dataset_continues_then_reports_failure_and_failed_mail` | Confirms the default missing-dataset continuation attempts later datasets but still exits 1 and reports failure through MQTT and enabled mail. |
| `test_missing_dataset_continues_then_reports_failure_and_failed_mail.zfs_result` | Nested stub that raises the exact missing-dataset diagnostic for one dataset and succeeds for later datasets. |
| `test_missing_dataset_stops_when_continuation_is_disabled` | Confirms `continue_on_missing_dataset=false` records the failure, stops before later datasets, and still reports final failure. |
| `test_missing_dataset_stops_when_continuation_is_disabled.zfs_result` | Nested stub for the stop-immediately missing-dataset path. |
| `test_other_zfs_failure_continues_by_default_then_reports_failure` | Confirms a non-missing checked ZFS failure continues by default to later datasets and still produces failure mail/MQTT/exit. |
| `test_other_zfs_failure_continues_by_default_then_reports_failure.zfs_result` | Nested permission-denied stub for default other-failure continuation. |
| `test_destroy_failure_continues_to_next_dataset_by_default` | Confirms `continue_on_other_failures=true` also covers a checked `zfs destroy` failure and resumes at the next configured dataset. |
| `test_destroy_failure_continues_to_next_dataset_by_default.zfs_result` | Nested list/destroy stub that exposes two matching snapshots, fails the destroy, then allows the following dataset to be listed. |
| `test_other_zfs_failure_stops_when_continuation_is_disabled` | Confirms `continue_on_other_failures=false` stops before later datasets while preserving failure diagnostics. |
| `test_other_zfs_failure_stops_when_continuation_is_disabled.zfs_result` | Nested permission-denied stub for the stop-immediately other-failure path. |
| `test_mixed_continued_failures_are_combined_in_final_report` | Confirms missing and other failures can both be continued and are combined in the final MQTT error/stderr report. |
| `test_mixed_continued_failures_are_combined_in_final_report.zfs_result` | Nested stub that emits one missing error, one permission error, and one successful dataset. |
| `test_finalization_failure_cannot_report_success` | Confirms log-finalization failure cannot be mislabeled successful. |
| `test_dry_run_log_preview_failure_reports_failure_and_failure_mail` | Confirms an error while previewing old-log retention turns the dry-run into failure and still uses failure mail/MQTT semantics. |
| `test_mail_warning_is_nonfatal` | Confirms mail failure leaves cleanup successful but sets MQTT warning. |
| `test_interrupt_is_never_success` | Confirms keyboard interrupt reports exit 130/failure. |
| `test_invalid_config_stops_before_cleanup` | Confirms enabled MQTT with incomplete settings is rejected during config parsing, before `run_cleanup`. |

### `LoggingLocationTests`

| Test | Purpose |
| --- | --- |
| `test_logs_are_created_beside_actual_script_without_tmp_fallback` | Confirms logs are always created in `logs/` beside the actual application script and that there is no silent `/tmp` fallback. |

### `RetentionTests`

| Test/helper | Purpose |
| --- | --- |
| `prune` | Captures safe mocked ZFS command sequences for retention assertions. |
| `test_matching_count_and_dry_run` | Protects host matching, count retention, and dry-run no-destroy behavior. |
| `test_dry_run_returns_counts_for_final_report_without_destroy` | Confirms dry-run snapshot selection returns aggregate counts without issuing a destroy command. |
| `test_original_no_retention_behavior_is_preserved` | Explicitly protects the existing behavior where no age + retain 0 selects every matching snapshot. |
| `test_age_and_count_work_together` | Protects combined age/count selection. |
| `test_log_dry_run_and_group_retention` | Protects paired log-group retention, returned report counts, and dry-run no-delete behavior. |

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
| `sudo python3 CleanUpInSyncoidSnapshots.py -c config.toml` | Public cleanup invocation using the short configuration selector. `-c` chooses the TOML file; every cleanup/retention/reporting setting comes from it. |
| `sudo python3 CleanUpInSyncoidSnapshots.py --config config.toml` | Equivalent public cleanup invocation using the long configuration selector. |
| `python3 CleanUpInSyncoidSnapshots.py -h` / `--help` | Displays the standard CLI help, every public flag, and examples, then exits before configuration loading, root checks, logging, or ZFS work. |
| `python3 CleanUpInSyncoidSnapshots.py --version` | Prints `CleanUpInSyncoidSnapshots.py 0.0.14` and exits before configuration loading, logging, root checks, or ZFS work. |
| `sudo .venv/bin/python CleanUpInSyncoidSnapshots.py -c config.toml` | Same cleanup invocation when using the documented virtual environment. |
| `zfs list -H -t snapshot -o name DATASET` | Lists snapshot names for one explicit dataset in machine-readable form; no recursive traversal is requested. Checked failures are recorded and the matching cleanup continuation setting decides whether the outer loop advances to the next dataset. |
| `zfs destroy SNAPSHOT` | Deletes exactly one selected snapshot. No `-r`, force, wildcard, or shell expansion is used. A checked failure is classified as an “other” dataset failure; it stops work inside that dataset and the outer loop then follows `continue_on_other_failures`. |
| `mail -s SUBJECT [--attach FILE ...] RECIPIENT` | Optional external mail delivery using the current log/error files. |
| `python -B mqtt_notifications.py --publish` | Internal timeout-isolated MQTT worker launched only by `notify_mqtt`; credentials/report arrive on stdin. `--publish` is not a public application flag. |
| `python3 -m venv .venv` | Creates an isolated Python environment when desired. |
| `.venv/bin/python -m pip install -r requirements.txt` | Installs `tomli` only when Python <3.11 requires it. |
| `.venv/bin/python -m pip install -r requirements-mqtt.txt` | Installs base requirements plus optional Paho MQTT. |
| `./build-pyinstaller.sh` | Recreates a clean `.venv-build`, removes prior `build/` and `dist/`, recreates `dist/` empty, installs `requirements-build.txt`, runs the one-file PyInstaller spec with explicit build/dist paths, fails unless `dist/` contains exactly one executable named `CleanUpInSyncoidSnapshots`, then smoke-tests that executable. |
| `sudo ./dist/CleanUpInSyncoidSnapshots -c config.toml` | Runs the frozen one-file build. It accepts the same public CLI/config as source mode; Python, Paho and Tomli are bundled, while host `zfs` and optional `mail` remain external. |
| `./dist/CleanUpInSyncoidSnapshots --help` / `--version` | Smoke-safe help/version actions on the frozen build. |
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
| `requirements-build.txt` | PyInstaller build environment requirements: runtime MQTT dependency set, forced Tomli fallback, and PyInstaller itself. |
| `CleanUpInSyncoidSnapshots.spec` | One-file PyInstaller definition. Explicit hidden-import collection includes all Paho and Tomli submodules; project/stdlib modules are discovered normally. |
| `build-pyinstaller.sh` | Build helper that recreates the isolated build venv and leaves the final executable at `dist/CleanUpInSyncoidSnapshots`, then smoke-tests it. |
| `dist/` | Generated final executable output directory. It is intentionally ignored by Git and recreated for builds. |
| `datasets-example` | Original dataset-list example. |
| `hostnames-example` | Original hostname-list example. |
| `home-assistant/CleanUpInSyncoidSnapshots-mqtt-persistent-notification.yaml` | Receive-only example blueprint for final MQTT reports. |
| `tests/test_project.py` | Regression and loopback integration tests. |
| `README.md` | Current usage/configuration documentation only. |
| `VERSIONING.md` | Release history and version policy. |
| `VERIFICATION.md` | Evidence and test limitations for the packaged release. |
| `DISCLAIMER.md` | Existing liability/data-loss warning. |
| `.gitignore` | Keeps local runtime TOML/input files, logs, Python caches, virtual environments, and build outputs out of commits while explicitly preserving `config-example.toml`. |
| `.github/CODEOWNERS` | Existing repository ownership metadata. |

## Safety boundaries retained

- Configuration validation occurs before `run_cleanup` and therefore before ZFS commands.
- The ZFS runner uses argument lists, never a shell command string.
- Dry-run never calls `zfs destroy` and never removes old log groups.
- Snapshot matching remains limited to exact configured hostnames and the existing Syncoid timestamp pattern.
- `zfs destroy` remains one snapshot at a time with checked failure handling.
- Dataset-level checked ZFS failures always make the final result fail. The two explicit continuation settings only control whether the next configured dataset is attempted; setting either to `false` restores stop-immediately behavior for that category.
- Mail and MQTT remain optional notification layers; neither can make snapshot-selection logic broader.
- MQTT publishing stays in a separate timeout-bounded worker and remains non-retained.
