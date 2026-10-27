# Commented code map — CleanUpInSyncoidSnapshots 0.0.20

This file explains the current 0.0.20 source implementation. Release changes belong in the synchronized `VERSIONING.md` and `versioning.md` files. The preserved `dist/CleanUpInSyncoidSnapshots` executable reports 0.0.16; run source for this release or build a disposable copy for a current executable.

## `CleanUpInSyncoidSnapshots.py`

| Function/class | What it does and why |
| --- | --- |
| `ReportWarningHandler` | Logging handler enabled for either completion MQTT or live preview. It remembers that an ERROR-level message occurred so a run that still exits successfully can publish `warning: true`, even if log retention later deletes the original error file. |
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
| `is_missing_dataset_error` | Recognizes checked ZFS list OR destroy failures whose stderr contains `dataset does not exist` (case-insensitive); `run_cleanup` uses that classification to choose the matching continuation option. |
| `run_cmd` | Executes ZFS commands without a shell, captures stdout/stderr, logs details, and raises `CommandError` on checked nonzero exit. Keeping argv as a list avoids shell interpolation. Capture real stderr before the existing trimming/logging logic; mark CommandError diagnostics as captured to prevent duplication. |
| `get_newest_files` | Finds the newest `.log` and `.err` files for the configured prefix so email can attach/read the current report files. |
| `read_hostnames` | Reads exact Syncoid hostnames, ignoring blank lines and whole-line `#` comments. |
| `send_mail` | Invokes the host `mail` command with subject and optional attachments placed before the recipient for broad mail/mailx compatibility. Observe its phase and actual stderr for the shared in-memory report, without changing mail outcome handling. |
| `print_separator` | Writes a visual separator to normal or error logging for readable reports. |
| `log_blank_line` | Adds a blank informational log line without repeating formatting code. |
| `WasMailSent` | Logs whether the external mail command succeeded; mail failure itself remains nonfatal to the cleanup result. |
| `build_backup_mail_header` | Builds the optional title/comment block shared by success and failure email bodies; `report.title` is the same run name used by MQTT and the subject. |
| `MailTo` | Collects the newest log/error files, assembles body text, and reuses `backup_title` (`report.title`) as a run-name prefix for the subject before calling `send_mail` and recording delivery outcome. Subject whitespace is collapsed to keep multiline titles on one line; the body keeps the full title/comment. Blank titles preserve existing subjects. This shared path covers success, failure, dry-run and root rejection. |
| `parse_syncoid_ts` | Parses Syncoid's timestamp suffix including signed or signless positive GMT offsets and returns a timezone-aware datetime for safe UTC comparison. |
| `delete_syncoid_snapshots` | Lists snapshots for one explicit dataset, matches only configured Syncoid hosts, sorts newest-first, applies retain/age protection, and previews or destroys selected snapshots one at a time. It returns the matched/selected counts so dry-run reporting reuses the actual selection logic. Checked list/destroy failures propagate to `run_cleanup`; a failed destroy stops further work inside that dataset before any configured outer-loop continuation. |
| `log_dry_run_report` | Writes the final aggregate dry-run summary after snapshot selection and, on successful dry-runs, after old-log retention preview. The summary is written before optional success mail so the email body/attachment includes it. |
| `delete_old_files` | Applies the existing shared retention policy to timestamp-paired `.log`/`.err` groups. It returns matched/selected group and selected-file counts for the final report; in dry-run it only reports candidates and never removes files. |
| `main` | Public entry point. Before public argument parsing, a private frozen-worker environment marker can route a PyInstaller child process directly into `publish_worker`; report/config data still arrives on stdin. Normal invocations explicitly derive argparse `prog` from the invoked filename so help/version naming also stays consistent on Python 3.14+. Help explains both TOML modes, root, notification gating, relative paths, and the no-age/zero-retention deletion case. Normal invocations provide standard `-h/--help` and `--version`, accept equivalent `-c CONFIG` / `--config CONFIG`, reject old operational flags, load/validate TOML before cleanup, preserve exit/exception behavior, and build the final MQTT report after finalization. Before calling MQTT it applies the shared success/failure gate, so successful delete and dry-run runs with `mqtt.on_success=false` never enter the notifier. The help/version actions exit before config loading or destructive work. A second private hook handles live workers. Bind RunReporting around the existing lifecycle, preserve the actual outcome/interrupt code, finalize live independently, and protect completion construction/delivery from replacing the job outcome. |
| `run_cleanup` | Cleanup lifecycle reused by the TOML interface: logger setup, root guard, input-file loading, dry-run/delete processing, optional mail, log retention, and empty `.err` cleanup. It aggregates dry-run snapshot counts, previews old-log retention before the final dry-run report on successful previews, applies identical mail success gating to delete and dry-run, and logs `Success mail report suppressed by mail.on_success=false.` on either successful mode when mail is enabled but success reporting is disabled. It records/classifies dataset failures, applies continuation settings, and prunes old logs destructively only after a successful delete run. |
| Imported `parse_older_than` | Re-exported from `modules/config_loader.py` so existing callers/tests can still use `CleanUpInSyncoidSnapshots.parse_older_than` while parsing logic lives with configuration validation. |

## `modules/config_loader.py`

| Function/constant | What it does and why |
| --- | --- |
| `TOP_LEVEL_SECTIONS` | Exact accepted TOML sections. Unknown sections are rejected to catch misspelled configuration before destructive work. |
| `SECTION_KEYS` | Exact accepted keys in each section, including both cleanup continuation booleans and matching `on_success` switches for mail/MQTT. Tests use it to ensure `configs/config-example.toml` documents every supported setting. |
| `parse_older_than` | Converts `Nd`, `Nw`, or `Nm` into `timedelta`, preserving the original 30-day-month rule. Empty/optional handling is done by `load_config`. |
| `_table` | Reads one TOML table, verifies its type, enforces required sections, rejects unknown keys, and gives a targeted migration error when obsolete `mqtt.publish_dry_run` is found. |
| `_required_string` | Validates nonempty string settings such as command and required file paths without coercing wrong TOML types. |
| `_optional_string` | Validates optional string settings such as report text and log prefix while allowing empty values. |
| `_boolean` | Requires real TOML booleans rather than accepting integer lookalikes. |
| `_resolve_config_relative` | Expands `~` and resolves relative paths against the TOML file directory so service/cron current working directory does not change which input/certificate file is used. |
| `load_config` | Opens TOML with `tomllib`/`tomli`, validates all application sections, converts age/defaults, defaults both continuation switches to `true`, maps mail `on_success`, validates enabled MQTT settings including MQTT `on_success`, and calls configure_reporting for canonical/legacy MQTT aliases plus independent live settings before returning the runtime namespace. The friendly MQTT name uses report.title, then LiveBackupName, then the application name. No non-MQTT setting is remapped. |
| `tomllib` / `tomli` import fallback | Python 3.11+ uses the standard library; Python 3.10 falls back to the dependency in `requirements.txt` to preserve the project's prior Python 3.10 minimum. |

## `modules/mqtt_notifications.py`

| Function/constant | What it does and why |
| --- | --- |
| `DEFAULTS` | MQTT defaults for port, credentials, client ID, QoS, timeout, TLS paths, and success publishing (`on_success=false`). |
| `should_send_notification` | Single shared notification-policy helper used by both the main mail lifecycle and MQTT lifecycle. It returns true for every failure, and for success only when the channel's `on_success=true`, preventing dry-run from having a separate success rule. |
| `validate_mqtt_config` | Validates the enabled `[mqtt]` TOML settings, rejects unknown/wrong types and wildcard publish topics, normalizes empty optional strings to absent values, enforces username/password and certificate/key relationships, and resolves certificate files relative to the TOML directory. |
| `build_mqtt_report` | Uses the configured run name (`report.title`) in JSON `title`, with application-name fallback when blank. Sets both `name` and `title` to the friendly name, keeps `job` as the stable log prefix, and identifies this application by `job_type`. Produces the Home Assistant-facing JSON schema using cleanup result, report metadata, warning state, command, version, and typed `success`/`exit_code`/warning/dry-run fields, shared run identity and latest 4,000 characters of actual stderr (never stdout or fabricated log text). Failed datasets carry original child exit codes only as an optional project extension. Dry-run payloads additionally receive the aggregate `dry_run_report` object supplied by the cleanup lifecycle. |
| `_run_publisher` | Starts the publisher in a new Linux session with stdin and captured output pipes. `communicate` enforces the configured timeout. On timeout or interruption, `os.killpg(..., SIGKILL)` terminates that isolated process group, including PyInstaller bootloader descendants, before draining pipes and reaping the launcher. It returns a `CompletedProcess` to preserve the caller's nonfatal-delivery policy. |
| `notify_mqtt` | Defensive MQTT notification wrapper. It applies the independent `send_on_dry_run` gate and re-applies `should_send_notification` so a successful report with `mqtt.on_success=false` cannot launch the publisher even if a caller bypasses the main lifecycle gate. In source mode it starts `modules/mqtt_notifications.py --publish`; in a PyInstaller build it relaunches the same frozen executable with a private environment marker. Both forms use `_run_publisher` to pass config/report on stdin, enforce the hard timeout for the entire isolated publisher process group, keep credentials off argv, and leave cleanup outcome unchanged if publishing fails. |
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
| `test_example_contains_every_supported_setting` | Ensures `configs/config-example.toml` has every supported section/key and no undocumented extras. |
| `test_example_loads_and_is_safe_by_default` | Confirms the packaged example parses, defaults to dry-run, leaves mail/MQTT disabled, and resolves paths correctly. |
| `test_defaults_and_negative_retain_compatibility` | Confirms optional defaults, both continuation defaults are `true` when omitted, and negative-retain normalization remains zero. |
| `test_invalid_cleanup_and_unknown_keys_are_rejected` | Confirms invalid commands/types, misspelled keys, and unknown sections fail before cleanup. |
| `test_continuation_options_require_real_booleans` | Confirms both continuation settings accept only real TOML booleans and reject integer lookalikes. |
| `test_mail_requires_recipient_only_when_enabled` | Confirms explicit mail enablement cannot proceed without a recipient. |
| `test_relative_paths_are_config_relative` | Confirms dataset/hostname paths follow the TOML file rather than current working directory. |
| `test_cli_rejects_old_operational_options` | Confirms an old operational CLI option is rejected and cleanup is not called. |
| `test_cli_help_is_available_without_cleanup` | Confirms standard `-h/--help` is available, documents `--version` plus both configuration spellings, shows examples, exits 0, checks the safety/mode guidance, tolerates equivalent metavar formatting across Python versions, and never loads configuration or enters cleanup. |
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
| `test_fallback_title_and_output_limit` | Confirms blank title fallback and 4,000-character diagnostic bound. |
| `test_shared_notification_gate` | Verifies the one shared truth table: failures always notify; successes notify only when `on_success=true`. |
| `test_disabled_and_default_success_reports_do_not_launch_worker` | Confirms disabled MQTT and default-suppressed success reports for both delete and dry-run do not launch the publisher. |
| `test_worker_input_and_timeout` | Confirms secrets are not placed on the worker command line and timeout is applied. |
| `test_failures_publish_for_delete_and_dry_run_when_success_reports_are_disabled` | Confirms failures publish for both delete and dry-run whenever MQTT is enabled, even with `on_success=false`. |
| `test_success_requires_same_explicit_opt_in_for_delete_and_dry_run` | Confirms the same `mqtt.on_success=true` opt-in enables successful delete and successful dry-run reports. |
| `test_delivery_failure_is_logged_and_secret_not_echoed` | Confirms publisher failures are nonfatal and worker stderr is not copied into logs where credentials could leak. |
| `test_timeout_is_nonfatal` | Confirms a stuck publisher is bounded and only logged. |
| `test_timeout_kills_publisher_process_group` | Simulates an exited launcher whose child keeps output pipes open; proves timeout cleans up descendants promptly instead of waiting for the child's sleep. |
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
| `invoke` | Runs real `main()`/TOML/lifecycle flow with temporary files and safe mocks for ZFS, log cleanup, mail, and MQTT. Optional `report_title` supplies the run name; `real_mail=True` exercises real `MailTo` while mocking the external `send_mail` boundary. |
| `test_named_run_reaches_mail_subject_body_and_mqtt` | Exercises real TOML loading, cleanup lifecycle, `MailTo` and MQTT report creation for delete/dry-run success, command failure and root rejection; only external mail, ZFS and MQTT delivery are mocked. Checks the same run name reaches every subject, body and MQTT `title`, while app/job identifiers remain stable. |
| `test_blank_run_name_preserves_email_subject_and_mqtt_fallback` | Confirms blank names leave existing subjects unchanged and preserve MQTT's application-name fallback. |
| `test_multiline_run_name_is_single_line_in_subject_only` | Confirms CR/LF/tab whitespace cannot create multiline subjects; body/MQTT retain the configured title text after existing outer trimming. |
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
| `exchange` | Starts a loopback-only miniature MQTT broker fixture and invokes the real isolated Paho publisher. Its successful report sets `on_success=True` explicitly so it reaches the publisher under the same production opt-in policy; otherwise the test would wait for a connection that can never arrive. |
| `exchange.serve` | Accepts the client, sends success/rejection/stall responses, captures publish topic/payload/flags, and performs QoS acknowledgements. |
| `test_real_qos_0_1_2_delivery` | Verifies actual Paho QoS 0/1/2 loopback delivery and non-retained messages when Paho is installed. |
| `test_broker_rejection` | Confirms broker rejection is logged by the parent and does not leak into cleanup outcome. |
| `test_stalled_broker_is_killed_at_timeout` | Confirms stalled publisher work is terminated within the configured timeout. |

## Public and internal commands

| Command | What it does and why |
| --- | --- |
| `sudo python3 CleanUpInSyncoidSnapshots.py -c configs/config.toml` | Public cleanup invocation using the short configuration selector. `-c` chooses the TOML file; every cleanup/retention/reporting setting comes from it. |
| `sudo python3 CleanUpInSyncoidSnapshots.py --config configs/config.toml` | Equivalent public cleanup invocation using the long configuration selector. |
| `python3 CleanUpInSyncoidSnapshots.py -h` / `--help` | Displays the standard CLI help, every public flag, and examples, then exits before configuration loading, root checks, logging, or ZFS work. |
| `python3 CleanUpInSyncoidSnapshots.py --version` | Prints `CleanUpInSyncoidSnapshots.py 0.0.20` and exits before configuration loading, logging, root checks, or ZFS work. |
| `sudo .venv/bin/python CleanUpInSyncoidSnapshots.py -c configs/config.toml` | Same cleanup invocation when using the documented virtual environment. |
| `zfs list -H -t snapshot -o name DATASET` | Lists snapshot names for one explicit dataset in machine-readable form; no recursive traversal is requested. Checked failures are recorded and the matching cleanup continuation setting decides whether the outer loop advances to the next dataset. |
| `zfs destroy SNAPSHOT` | Deletes exactly one selected snapshot. No `-r`, force, wildcard, or shell expansion is used. A checked failure stops work inside that dataset. If stderr contains `dataset does not exist` (case-insensitive), the outer loop follows `continue_on_missing_dataset`; otherwise it follows `continue_on_other_failures`. Either category makes the final run fail. |
| `mail -s SUBJECT [--attach FILE ...] RECIPIENT` | Optional external mail delivery using the current log/error files. |
| `python -B modules/mqtt_notifications.py --publish` | Internal timeout-isolated MQTT worker launched only by `notify_mqtt`; credentials/report arrive on stdin. `--publish` is not a public application flag. |
| `python3 -m venv .venv` | Creates an isolated Python environment when desired. |
| `.venv/bin/python -m pip install -r requirements.txt` | Installs `tomli` only when Python <3.11 requires it. |
| `.venv/bin/python -m pip install -r requirements-mqtt.txt` | Installs base requirements plus optional Paho MQTT. |
| `./build-pyinstaller.sh` | Run in a separate disposable project copy to retain the supplied executable. Recreates a clean `.venv-build`, removes prior `build/` and `dist/`, recreates `dist/` empty, installs `requirements-build.txt`, runs the one-file PyInstaller spec with explicit build/dist paths, fails unless `dist/` contains exactly one executable named `CleanUpInSyncoidSnapshots`, then smoke-tests that executable. |
| `sudo ./dist/CleanUpInSyncoidSnapshots -c configs/config.toml` | Runs the frozen one-file build. It accepts the same public CLI/config as source mode; Python, Paho and Tomli are bundled, while host `zfs` and optional `mail` remain external. |
| `./dist/CleanUpInSyncoidSnapshots --help` / `--version` | Smoke-safe help/version actions on the frozen build. The preserved supplied binary reports 0.0.16; a rebuild from current source reports 0.0.20. |
| `cp configs/config-example.toml configs/config.toml` | Creates a local editable config from the complete reference. |
| `chmod 600 configs/config.toml` | Protects a config that may hold MQTT credentials and mail destinations. |
| `python3 -B -m unittest discover -s tests -v` | Runs safe regression tests; ZFS/mail are mocked, and real MQTT tests use loopback only. |

## Files

| File | Why it exists |
| --- | --- |
| `CleanUpInSyncoidSnapshots.py` | Public application entry point and retained cleanup/email/log logic. |
| `modules/config_loader.py` | Single-TOML parsing and validation boundary before destructive work. |
| `configs/config-example.toml` | Identical to distributed `configs/config.toml`; complete commented reference for every supported runtime setting. |
| `modules/mqtt_notifications.py` | Optional status-report validation and isolated publisher. |
| `requirements.txt` | Python 3.10 TOML parser compatibility dependency. |
| `requirements-mqtt.txt` | Optional Paho dependency plus base requirements. |
| `requirements-build.txt` | PyInstaller build environment requirements: runtime MQTT dependency set, forced Tomli fallback, and PyInstaller itself. |
| `CleanUpInSyncoidSnapshots.spec` | One-file PyInstaller definition. Explicit hidden-import collection includes all Paho and Tomli submodules; project/stdlib modules are discovered normally. |
| `build-pyinstaller.sh` | Build helper that recreates the isolated build venv and leaves the final executable at `dist/CleanUpInSyncoidSnapshots`, then smoke-tests it. |
| `dist/` | Generated final executable output directory. It is intentionally ignored by Git, recreated for builds, and included in this release ZIP with the preserved 0.0.16 executable. Source reports 0.0.20; rebuilding in a disposable copy replaces its binary. Runtime logs are created only when running cleanup. |
| `configs/datasets-example` | Original dataset-list example. |
| `configs/hostnames-example` | Original hostname-list example. |
| `examples/CleanUpInSyncoidSnapshots-mqtt-persistent-notification.yaml` | Receive-only example blueprint for final MQTT reports. |
| `tests/test_project.py` | Regression and loopback integration tests. |
| `README.md` | Current usage/configuration documentation only. |
| `VERSIONING.md`, `versioning.md` | Byte-identical complete release history and version policy; update both together to support either requested filename. |
| `VERIFICATION.md` | Evidence and test limitations for the packaged release. |
| `PACKAGE_MANIFEST.json` | Original-relative path comparison and SHA-256 hashes for the packaged files, plus unchanged/modified/added classifications. The manifest excludes its own hash to avoid a circular digest; ZIP integrity and the external archive checksum cover it. |
| `DISCLAIMER.md` | Existing liability/data-loss warning. |
| `.gitignore` | Keeps local runtime TOML/input files, logs, Python caches, virtual environments, and build outputs out of commits while explicitly preserving `configs/config-example.toml`. |
| `.github/CODEOWNERS` | Existing repository ownership metadata. |

## Safety boundaries retained

- Configuration validation occurs before `run_cleanup` and therefore before ZFS commands.
- The ZFS runner uses argument lists, never a shell command string.
- Dry-run never calls `zfs destroy` and never removes old log groups.
- Snapshot matching remains limited to exact configured hostnames and the existing Syncoid timestamp pattern.
- `zfs destroy` remains one snapshot at a time with checked failure handling.
- Dataset-level checked ZFS failures always make the final result fail. The two explicit continuation settings only control whether the next configured dataset is attempted; setting either to `false` restores stop-immediately behavior for that category.
- Mail and MQTT remain optional notification layers; neither can make snapshot-selection logic broader.
- Completion publishing stays in the existing timeout-bounded worker and remains non-retained. Live state/events are non-retained; only discovery and last real live result are retained.

## Build specification and shell commands

`CleanUpInSyncoidSnapshots.spec` uses `collect_submodules` to include optional MQTT and TOML fallback modules. `Analysis` resolves the entry point, imports, and dependencies; `PYZ` bundles Python modules; `EXE` creates the console one-file executable. No runtime config or secrets are embedded.

`build-pyinstaller.sh` uses `cd` to select its own project directory, reads optional `PYTHON_BIN` and `VENV_DIR` overrides (defaults: `python3` and `.venv-build`), and removes the selected virtualenv, `build/`, and `dist/` with `rm -rf` before recreating output with `mkdir -p`. Supply a dedicated disposable build-venv path if overriding `VENV_DIR`. `python -m venv` creates isolation; `python -m pip install -r requirements-build.txt` installs the declared build dependencies. `pyinstaller --clean --noconfirm --distpath ... --workpath ... SPEC` clears its working cache, replaces output, and separates final output from build intermediates. `find` and `mapfile` enumerate every direct output entry, including hidden entries; shell count/path/regular-file/executable checks reject extra or invalid output. The executable's `--version` and `--help` smoke checks run before success is printed. `set -euo pipefail` aborts on failed commands, undefined variables, and pipeline errors.

The Home Assistant blueprint's `trigger: mqtt` receives reports for one exact configured topic. Its template conditions validate the application/status and apply notification preferences. `persistent_notification.create` displays a report, optionally reusing `notification_id`; it performs no cleanup commands.


## `modules/mqtt_reporting.py` — completion contract and independent live preview

The module docstring contains integration usage. The single adapter observes existing work; it neither selects new cleanup candidates nor issues ZFS, mail, scheduling or HA commands.

| Symbol | What it does and why |
| --- | --- |
| `_text` | Require real strings and optional nonempty values so report fields keep a predictable JSON contract. |
| `_json_text` | Validate native JSON types/finite numbers/string keys and encode UTF-8 without introducing a JSON file. |
| `_json_text.check` | Recursively reject unsupported values and non-string object keys before encoding or publishing. |
| `_dataset_list` | Detach optional dataset diagnostics supplied by actual dataset adapters; omitted diagnostics remain absent. |
| `build_report` | Build typed completion JSON from the authoritative job exit code, cap actual stderr at 4,000 characters, include run/host/time identity, and allow optional extensions without replacing core fields. |
| `encode_report` | Reject inconsistent status/success/exit code, non-boolean flags, invalid identity fields or malformed optional dataset arrays before compact JSON serialization. |
| `_now` | Return a UTC ISO timestamp for live heartbeat and lifecycle events. |
| `make_device_id` | Hash host, stable job and config path for a unique reproducible identity independent of friendly names or manufacturer. |
| `LiveConfig` | Immutable live transport/discovery/event options; passwords are excluded from its repr. Defaults leave live delivery disabled. |
| `LiveConfig.from_mapping` | Adapt supplied live option names and shared broker credentials independently of completion enablement; derive safe heartbeat expiry and device identity. |
| `LiveConfig.from_mapping.certificate` | Expand a certificate path against the application TOML directory, preserving config-relative lookup. |
| `LiveConfig.__post_init__` | Reject invalid live types, topic/device identities, booleans, timeouts, heartbeat/expiry relationships and TLS/auth combinations before workers can start. |
| `LiveConfig.state_topic` | Return this device's non-retained live state topic, separate from completion notifications. |
| `LiveConfig.result_topic` | Return this device's retained last-real-result topic for HA restarts or expired live sensors. |
| `LiveConfig.events_topic` | Return a separate non-retained lifecycle-event topic; LiveNotify flags affect only these messages. |
| `discovery_messages` | Build retained HA sensor discovery with configurable manufacturer, unique IDs, expiring non-retained state and non-expiring last result. Aggregate sensors carry stable role attributes so entity renames work. |
| `LivePreview` | One run's thread-safe in-memory snapshot, outcome records and bounded asynchronous publisher; no job logic or local persistence lives here. |
| `LivePreview.__init__` | Initialize nullable measurements and separate progress/outcome units. outcome_item_unit defaults to item_unit for generic callers; cleanup uses datasets for progress and snapshots for outcomes. |
| `LivePreview._snapshot_locked` | Detach state under its lock and attach job_type, item_unit, outcome_item_unit, run/host identity, runtime and heartbeat without inferring unknown measurements. |
| `LivePreview.snapshot` | Return local observed state for callers/tests; this is not proof of broker delivery. |
| `LivePreview.last_delivery` | Return the last delivery attempt status separately from the actual job status. |
| `LivePreview.start` | Start at most one daemon only when enabled and allowed for this dry-run; optionally queue a start event without blocking the job thread on networking. |
| `LivePreview.update` | Validate and detach local updates, derive percent only from known positive totals, refresh outcome counts and wake the batching daemon. |
| `LivePreview.record_item` | Record an item's latest success/failure/skipped outcome by name, preserving reasons/optional details without incrementing generic completed/total progress. |
| `LivePreview.append_stderr` | Append actual supplied child stderr in memory, decoding bytes safely and keeping only the latest 4,000 characters. |
| `LivePreview.finish` | Freeze runtime/outcome exactly once; explicitly label failure, interruption or incomplete work without forcing 100%, queue allowed terminal events and bound the final send wait. |
| `LivePreview._cancel` | Stop the daemon and kill an active isolated publisher process group, including frozen bootloader descendants. |
| `LivePreview.close` | Reap/cancel live networking with bounded waits; closing without finish does not invent an outcome, so running state expires honestly. |
| `LivePreview._send` | Pass credentials and one message batch on worker stdin, isolate its process group, bound communication and kill/drain failed or timed-out workers without raising job errors. |
| `LivePreview._worker` | Coalesce local changes and heartbeats, periodically republish discovery, send non-retained state/events, retain last real results only, and track delivery independently. |
| `run_worker_if_requested` | Private source/frozen hook: read a batch from stdin, configure verified TLS/auth and call Paho multiple; unexpected publication errors return worker exit 1 without exposing secrets. |
| `configure_reporting` | Normalize supplied option names over legacy aliases, reuse the existing MQTT transport validator, independently construct completion/live options, and reject completion/live topic collisions. Live-only configs do not require or validate an unused completion topic; a local validation sentinel is never published or persisted. |
| `RunReporting` | Cleanup-specific observation adapter: one run ID, actual child stderr, snapshot decisions and optional dataset failures, all in memory. |
| `RunReporting.__init__` | Initialize dataset progress with an unknown total until datasets_file is read, plus separate snapshot detail counters and the shared friendly name/job/run identity. |
| `RunReporting.start` | Bind the current run context and begin optional live delivery; completion can remain disabled. |
| `RunReporting.update` | Merge project details and compute processed datasets as successful dataset completions plus checked dataset failures. Set total directly from datasets_configured after file parsing, keeping progress independent of snapshot outcomes. |
| `RunReporting.listed` | Accumulate matched snapshot names only; listing volume never changes dataset total or processed progress. |
| `RunReporting.item` | Count a separate snapshots_processed detail and record the snapshot outcome/destruction counter; never advance main dataset progress. |
| `RunReporting.selected` | Count the existing algorithm's selected deletion candidates before attempting them, including candidates in a dataset whose destroy later fails. |
| `RunReporting.dataset_completed` | Increment successful dataset completions and synchronize processed progress; the existing cleanup return value and snapshot logic remain unchanged. |
| `RunReporting.dataset_failure` | Keep actual dataset/command/code/stderr diagnostics, increment failed dataset attempts and processed progress without discarding the known file total; avoid duplicate stderr capture. |
| `RunReporting.scan_complete` | Synchronize actual processed counts after the loop; never force completed to total or manufacture success. |
| `RunReporting.capture` | Accumulate actual ZFS/mail stderr across child commands, unmodified except decoding/tail length; never use stdout or log messages as a substitute. |
| `RunReporting.finish` | Finalize independent live state with actual code/error/warning and always close the daemon/reset the observation context. |
| `observe` | Best-effort facade used at existing job boundaries; instrumentation errors cannot fail cleanup or replace its exit code. |

| Constant/alias | Why it exists |
| --- | --- |
| `ALIASES`, `REPORTING_KEYS`, `LIVE_KEYS` | Keep accepted supplied/legacy settings explicit so unknown config options still fail before work. Canonical names win without duplicating independent channels. |
| `_CURRENT` | Context-local in-memory observer avoids passing notification objects into every existing cleanup helper. |
| `_json`, `STDERR_LIMIT`, `WORKER_FLAG` | Reuse one strict JSON encoder, one 4,000-character diagnostic limit, and one private worker command. |

## `tests/test_mqtt_reporting.py`

Template-derived live/card checks and project-specific integration checks use fake HA registries, captured local processes and ephemeral localhost MQTT fixtures. They never perform ZFS work or send Pushover/production mail. Every new helper/test is listed below.

| Function/class | What it does and why |
| --- | --- |
| `wait_for` | Bound asynchronous test waits so stuck publisher threads/processes fail visibly. |
| `LiveTests` | Group live  checks and their isolated fixtures. |
| `LiveTests.live` | Supply the LiveTests live fixture/helper for isolated assertions without touching production services. |
| `LiveTests.test_identity_is_stable_and_separates_configs_and_hosts` | Verify identity is stable and separates configs and hosts so the reporting/UI contract stays accurate. |
| `LiveTests.test_config_validation_and_secret_repr` | Verify config validation and secret repr so the reporting/UI contract stays accurate. |
| `LiveTests.test_manufacturer_is_configurable_in_discovery_and_state` | Verify manufacturer is configurable in discovery and state so the reporting/UI contract stays accurate. |
| `LiveTests.test_invalid_manufacturer_names_are_rejected` | Verify invalid manufacturer names are rejected so the reporting/UI contract stays accurate. |
| `LiveTests.test_aggregate_sensors_have_stable_role_markers` | Verify aggregate sensors have stable role markers so the reporting/UI contract stays accurate. |
| `LiveTests.test_disabled_module_maintains_local_progress_without_processes` | Verify disabled module maintains local progress without processes so the reporting/UI contract stays accurate. |
| `LiveTests.test_progress_is_derived_and_unknown_is_null` | Verify progress is derived and unknown is null so the reporting/UI contract stays accurate. |
| `LiveTests.test_rejects_bad_counters_and_direct_status_updates` | Verify rejects bad counters and direct status updates so the reporting/UI contract stays accurate. |
| `LiveTests.test_stderr_tail_and_utf8_replacement` | Verify stderr tail and utf8 replacement so the reporting/UI contract stays accurate. |
| `LiveTests.test_completed_success_has_typed_code_and_shared_identity` | Verify completed success has typed code and shared identity so the reporting/UI contract stays accurate. |
| `LiveTests.test_failure_and_interrupt_do_not_force_progress_to_100` | Verify failure and interrupt do not force progress to 100 so the reporting/UI contract stays accurate. |
| `LiveTests.test_zero_code_with_remaining_work_is_incomplete` | Verify zero code with remaining work is incomplete so the reporting/UI contract stays accurate. |
| `LiveTests.test_finish_is_idempotent_freezes_runtime_and_rejects_late_updates` | Verify finish is idempotent freezes runtime and rejects late updates so the reporting/UI contract stays accurate. |
| `LiveTests.test_close_without_finish_does_not_invent_a_terminal_result` | Verify close without finish does not invent a terminal result so the reporting/UI contract stays accurate. |
| `LiveTests.test_discovery_separates_expiring_state_and_retained_result` | Verify discovery separates expiring state and retained result so the reporting/UI contract stays accurate. |
| `LiveTests.test_live_has_dataset_lists_and_counts` | Verify live has dataset lists and counts so the reporting/UI contract stays accurate. |
| `LiveTests.test_dataset_retries_replace_previous_outcome_and_keep_reasons` | Verify dataset retries replace previous outcome and keep reasons so the reporting/UI contract stays accurate. |
| `LiveTests.test_dataset_lists_and_snapshots_are_detached` | Verify dataset lists and snapshots are detached so the reporting/UI contract stays accurate. |
| `LiveTests.test_failed_items_prevent_zero_code_live_success` | Verify failed items prevent zero code live success so the reporting/UI contract stays accurate. |
| `LiveTests.test_dataset_input_validation_and_no_updates_after_finish` | Verify dataset input validation and no updates after finish so the reporting/UI contract stays accurate. |
| `LiveTests.test_background_heartbeat_and_terminal_batch` | Verify background heartbeat and terminal batch so the reporting/UI contract stays accurate. |
| `LiveTests.test_background_heartbeat_and_terminal_batch.send` | Supply the LiveTests test background heartbeat and terminal batch send fixture/helper for isolated assertions without touching production services. |
| `LiveTests.test_updates_are_local_and_coalesced_while_network_is_slow` | Verify updates are local and coalesced while network is slow so the reporting/UI contract stays accurate. |
| `LiveTests.test_updates_are_local_and_coalesced_while_network_is_slow.slow` | Supply the LiveTests test updates are local and coalesced while network is slow slow fixture/helper for isolated assertions without touching production services. |
| `LiveTests.test_disabled_dry_run_does_not_start_worker` | Verify disabled dry run does not start worker so the reporting/UI contract stays accurate. |
| `LiveTests.test_opted_in_dry_run_never_overwrites_retained_last_result` | Verify opted in dry run never overwrites retained last result so the reporting/UI contract stays accurate. |
| `LiveTests.test_actual_worker_isolation_and_final_payload_with_fake_paho` | Verify actual worker isolation and final payload with fake paho so the reporting/UI contract stays accurate. |
| `LiveTests.test_real_stalled_worker_is_killed_with_bounded_final_wait` | Verify real stalled worker is killed with bounded final wait so the reporting/UI contract stays accurate. |
| `LiveTests.test_failed_delivery_does_not_change_job_outcome` | Verify failed delivery does not change job outcome so the reporting/UI contract stays accurate. |
| `LiveTests.test_frozen_launch_and_tls_worker_hook` | Verify frozen launch and tls worker hook so the reporting/UI contract stays accurate. |
| `LiveTests.test_module_imports_without_paho_and_uses_python310_syntax` | Verify module imports without paho and uses python310 syntax so the reporting/UI contract stays accurate. |
| `Entity` | Represent a fake HA sensor with its device and attributes for offline card rendering. |
| `FakeHA` | Provide an in-memory HA registry/state surface; no installed HA service is contacted. |
| `FakeHA.__init__` | Supply the FakeHA   init   fixture/helper for isolated assertions without touching production services. |
| `FakeHA.sensor` | Supply the FakeHA sensor fixture/helper for isolated assertions without touching production services. |
| `FakeHA.__call__` | Supply the FakeHA   call   fixture/helper for isolated assertions without touching production services. |
| `FakeHA.state_attr` | Supply the FakeHA state attr fixture/helper for isolated assertions without touching production services. |
| `FakeHA.device_id` | Supply the FakeHA device id fixture/helper for isolated assertions without touching production services. |
| `FakeHA.device_attr` | Supply the FakeHA device attr fixture/helper for isolated assertions without touching production services. |
| `FakeHA.device_entities` | Supply the FakeHA device entities fixture/helper for isolated assertions without touching production services. |
| `CardTests` | Group card checks and their isolated fixtures. |
| `CardTests.setUp` | Supply the CardTests setUp fixture/helper for isolated assertions without touching production services. |
| `CardTests.state` | Build actual module payloads for running, success, failure, incomplete, interrupted and unknown-measurement card scenarios. |
| `CardTests.add` | Render actual discovery definitions into fake device sensors, including expired or renamed entities and retained prior results. |
| `CardTests.render` | Render the actual Markdown card with HA-like registry helpers and optional manufacturer filtering. |
| `CardTests.render.as_datetime` | Parse fixture timestamps with a safe default, matching the card's unavailable-time handling. |
| `CardTests.test_yaml_wrapper_preserves_markdown_content` | Verify yaml wrapper preserves markdown content so the reporting/UI contract stays accurate. |
| `CardTests.test_manufacturer_filter_and_custom_name` | Verify manufacturer filter and custom name so the reporting/UI contract stays accurate. |
| `CardTests.test_devices_added_automatically_and_deduplicated` | Verify devices added automatically and deduplicated so the reporting/UI contract stays accurate. |
| `CardTests.test_running_metrics_use_current_state_over_previous_result` | Verify running metrics use current state over previous result so the reporting/UI contract stays accurate. |
| `CardTests.test_expired_terminal_state_uses_retained_result` | Verify expired terminal state uses retained result so the reporting/UI contract stays accurate. |
| `CardTests.test_newer_run_with_lost_heartbeat_does_not_claim_old_success` | Verify newer run with lost heartbeat does not claim old success so the reporting/UI contract stays accurate. |
| `CardTests.test_first_run_without_retained_result_is_visible` | Verify first run without retained result is visible so the reporting/UI contract stays accurate. |
| `CardTests.test_incomplete_and_interrupted_are_explicit` | Verify incomplete and interrupted are explicit so the reporting/UI contract stays accurate. |
| `CardTests.test_unknown_progress_stays_unknown` | Verify unknown progress stays unknown so the reporting/UI contract stays accurate. |
| `CardTests.test_snapshot_results_and_stderr_are_formatted` | Verify snapshot results and stderr are formatted so the reporting/UI contract stays accurate. |
| `CardTests.test_renamed_entities_use_role_markers` | Verify renamed entities use role markers so the reporting/UI contract stays accurate. |
| `CardTests.test_empty_registry_shows_setup_instructions` | Verify empty registry shows setup instructions so the reporting/UI contract stays accurate. |
| `IntegrationTests` | Real cleanup lifecycle with external ZFS/mail/MQTT effects intercepted. |
| `IntegrationTests.run_job` | Run actual main/config/cleanup with real command/error/retention paths, intercept only ZFS subprocess results and MQTT delivery, and return captured live/completion outcomes. |
| `IntegrationTests.run_job.command` | Supply deterministic ZFS list/destroy success, stderr, failure or interrupt; reject every other child command so tests cannot run destructive jobs. |
| `IntegrationTests.run_job.publish` | Capture the real serialized completion report or simulate timeout without contacting any external broker. |
| `IntegrationTests.run_job.adapter` | Retain the real RunReporting instance for assertions after lifecycle finalization. |
| `IntegrationTests.test_success_has_typed_completion_and_honest_snapshot_counts` | Verify success has typed completion and honest snapshot counts so the reporting/UI contract stays accurate. |
| `IntegrationTests.test_destroy_failure_preserves_job_code_child_code_and_actual_stderr_tail` | Verify destroy failure preserves job code child code and actual stderr tail so the reporting/UI contract stays accurate. |
| `IntegrationTests.test_failed_listing_and_interrupt_never_invent_totals_or_success` | Verify failed listings retain the known dataset-file total and advance failed attempts, while interrupts keep the current entry unfinished and preserve the failure/interrupt result. |
| `IntegrationTests.test_completion_and_live_are_independent_in_all_enablement_combinations` | Verify completion and live are independent in all enablement combinations so the reporting/UI contract stays accurate. |
| `IntegrationTests.test_dry_run_skips_snapshot_destruction_and_preserves_last_real_result` | Verify dry run skips snapshot destruction and preserves last real result so the reporting/UI contract stays accurate. |
| `IntegrationTests.test_broker_failures_never_replace_actual_success_or_failure` | Verify broker failures never replace actual success or failure so the reporting/UI contract stays accurate. |
| `IntegrationTests.test_arbitrary_system_exit_is_preserved_even_when_reporting_raises` | Verify arbitrary system exit is preserved even when reporting raises so the reporting/UI contract stays accurate. |
| `IntegrationTests.test_real_run_cmd_stderr_on_success_and_mail_stderr_are_captured_verbatim` | Verify real run cmd stderr on success and mail stderr are captured verbatim so the reporting/UI contract stays accurate. |
| `IntegrationTests.test_canonical_options_legacy_aliases_and_non_mqtt_sections` | Verify canonical options legacy aliases and non mqtt sections so the reporting/UI contract stays accurate. |
| `IntegrationTests.test_generic_completion_has_no_dataset_fields_and_rejects_inconsistent_types` | Verify generic completion has no dataset fields and rejects inconsistent types so the reporting/UI contract stays accurate. |
| `IntegrationTests.test_no_new_application_commands_or_scheduling_and_worker_hook_is_private` | Verify no new application commands or scheduling and worker hook is private so the reporting/UI contract stays accurate. |
| `AutomationTests` | Group automation checks and their isolated fixtures. |
| `AutomationTests.setUp` | Supply the AutomationTests setUp fixture/helper for isolated assertions without touching production services. |
| `AutomationTests.test_topic_guards_pushover_limits_and_actual_completion_payload` | Verify topic guards pushover limits and actual completion payload so the reporting/UI contract stays accurate. |
| `AutomationTests.test_generic_card_hides_dataset_details_and_unmeasured_transfer` | Verify generic card hides dataset details and unmeasured transfer so the reporting/UI contract stays accurate. |
| `LiveBrokerTests` | Group live broker checks and their isolated fixtures. |
| `LiveBrokerTests.exchange` | Run real isolated Paho publishing against an ephemeral localhost listener and return wire messages; no production topic/broker receives anything. |
| `LiveBrokerTests.exchange.serve` | Acknowledge local QoS-1 MQTT packets, capture JSON/retain flags or reject connections, with bounded thread shutdown. |
| `LiveBrokerTests.test_real_paho_live_discovery_state_result_and_event_routing` | Verify real paho live discovery state result and event routing so the reporting/UI contract stays accurate. |
| `LiveBrokerTests.test_real_live_broker_rejection_preserves_job_code` | Verify real live broker rejection preserves job code so the reporting/UI contract stays accurate. |

## Added integration files and private command

- `configs/config.toml`: same complete safe example as `configs/config-example.toml`, with original non-MQTT sections and completion topic preserved. All credentials are placeholders; both channels default disabled.
- `examples/live-preview-card.yaml`: Markdown `content: |` template; manufacturer discovery and stable roles choose actual live or retained result data. Dataset-file progress/current position and separate snapshot outcomes appear for this job; generic item units and null measurements remain meaningful for other jobs. Lost heartbeats never assert a new success.
- `examples/success-failure-automation.yaml`: completion-topic-only Pushover example. An early preview guard and typed/consistent result condition run before actions; title/message are bounded. No sequencing/scheduling action is introduced.
- `python -B modules/mqtt_reporting.py --ha-live-preview-worker`: internal stdin-fed live publisher only; the public application CLI is unchanged. Rebuilt frozen apps dispatch the same private flag before public parsing. The preserved 0.0.16 binary does not implement it.

The existing receive-only persistent-notification blueprint now identifies the application by `job_type`, allowing friendly completion `name`/`title` values without losing its controls.

## Independent-channel edge checks

| Function/class | What it does and why |
| --- | --- |
| `IndependenceEdgeTests` | Protect independent channel, event and preview settings even with a minimal live-only config. |
| `IndependenceEdgeTests.test_live_only_does_not_require_or_validate_a_completion_topic` | Load live-only settings with no completion topic and success notifications disabled; live needs only its own broker/topics. |
| `IndependenceEdgeTests.test_live_event_and_discovery_switches_do_not_suppress_state_or_result` | Disable discovery and all events while verifying non-retained state and retained real results still publish for success/failure. |
| `IndependenceEdgeTests.test_completion_dry_run_switch_never_suppresses_live_or_starts_its_worker` | Verify the completion-only preview gate prevents its worker without changing independent live settings. |


## Dataset-file progress regressions

| Function/class | What it verifies and why |
| --- | --- |
| `DatasetFileProgressTests` | Protect dataset-file progress independently of snapshot counts and actual job outcome. |
| `DatasetFileProgressTests.run_job` | Reuse the existing intercepted real-lifecycle fixture so these tests execute no destructive commands. |
| `DatasetFileProgressTests.test_five_entries_show_two_of_five_before_third_dataset_in_both_modes` | Read five nonblank entries and verify 2/5, 40%, current position 3/5 before the third dataset, in delete and dry-run modes even with no snapshots. |
| `DatasetFileProgressTests.test_failed_entries_advance_position_without_becoming_successful` | All five failed dataset attempts reach 5/5 processed but remain failure, with zero successful dataset completions. |
| `DatasetFileProgressTests.test_stopped_failure_and_midfile_interrupt_leave_remaining_entries_unprocessed` | Stop after one checked failure at 1/5, or interrupt the third entry at 2/5; never force remaining progress. |
| `DatasetFileProgressTests.test_duplicate_entries_and_empty_file_use_exact_existing_input_rules` | Count repeated entries separately, ignore blank lines and keep zero-total percent unknown without changing the parser. |
| `DatasetFileProgressTests.test_card_renders_dataset_ratio_and_separate_snapshot_outcomes` | Render the real Markdown card with renamed sensors and show dataset ratio/current position while outcome rows remain snapshots. |


## Package layout and relocation checks

`modules/__init__.py` marks the shared runtime package; it performs no job action. The root app imports `modules.config_loader`, `modules.mqtt_notifications` and `modules.mqtt_reporting`. Intra-package imports are relative. Workers still launch their own absolute source paths, or use the existing frozen hooks. `CleanUpInSyncoidSnapshots.spec` discovers the imported package through the root entry point; the spec and build helper are unchanged, and a rebuilt binary was not tested here.

`configs/` holds both complete TOML examples and the unchanged dataset/hostname examples. Relative configured input paths still resolve against the selected TOML directory, so paired files work after relocation. `examples/` holds all three Home Assistant YAML examples, including the moved persistent-notification blueprint. The root JSON manifest is actual release metadata; no standalone JSON example was present to move.

| Function/class | What it verifies and why |
| --- | --- |
| `LayoutTests` | Protect the requested modules/configs/examples organization without changing job logic or creating duplicate files. |
| `LayoutTests.test_auxiliary_files_have_one_location_in_requested_folders` | Check the relocated files exist exactly where requested, the old runtime/config paths are gone, and real release metadata remains at root. |
| `LayoutTests.test_external_cwd_cli_and_config_relative_input_paths` | Run actual source help/version and config loading from outside the project, proving imports and paired input paths work without relying on the shell CWD. |
| `LayoutTests.test_both_source_workers_resolve_modules_from_external_cwd` | Run both real source worker subprocesses under fake Paho from another directory, capturing delivery calls without contacting a broker. |
| `LayoutTests.test_gitignore_keeps_config_examples_visible_and_private_config_ignored` | Use an isolated Git repository to prove configs examples remain visible while site-local config.toml remains ignored. |
