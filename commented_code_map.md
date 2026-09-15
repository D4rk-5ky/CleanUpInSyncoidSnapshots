# Commented code map

This map describes the current implementation: what each function/command does and why.
## Execution flow

`main` parses and validates → `run_cleanup` runs the original cleanup → mail and log finalization → `build_mqtt_report` → `notify_mqtt` → timeout-isolated `publish_worker`. No MQTT settings means no Paho import or broker connection.

## CleanUpInSyncoidSnapshots.py

| Function or method | What it does and why |
| --- | --- |
| `ReportWarningHandler.__init__` | Create an ERROR-level observer tied to this run's state so errors remain known after log retention. |
| `ReportWarningHandler.emit` | Mark the run as having warnings whenever the error logger emits a record; it performs no extra output. |
| `setup_logger` | Create DEBUG/INFO main logging and ERROR logging to files and console, returning the error-file path for finalization. |
| `setup_logger._build_logger` | Configure a named non-propagating logger and attach formatted handlers, avoiding duplicate installed handlers. |
| `pick_log_folder` | Prefer writable logs beside the script, otherwise use a script-named folder under the system temp directory. |
| `pick_log_folder._ensure_writable` | Create and remove a small probe file to check whether the preferred folder accepts writes. |
| `script_base_name` | Sanitize the script filename into a default log prefix and fallback directory name. |
| `CommandError.__init__` | Retain command arguments, exit code, stdout, and stderr so failed ZFS commands can be logged and reported over MQTT. |
| `run_cmd` | Execute argument lists without a shell, log command results, and raise CommandError for checked nonzero exits. |
| `get_newest_files` | Find newest .log and .err files for a prefix by modification time for email attachments. |
| `read_hostnames` | Read exact hostname lines, ignoring blanks and whole-line comments, to limit snapshot matching. |
| `send_mail` | Invoke mail with subject and attachments before the recipient, sending the body through stdin and returning delivery diagnostics. |
| `print_separator` | Insert a visual boundary into main or error logs so datasets and outcomes are easier to read. |
| `log_blank_line` | Insert spacing into the main log without duplicating formatting code. |
| `WasMailSent` | Log whether mail completed and include mail stderr when it failed. |
| `build_backup_mail_header` | Build optional title/comment text for email without changing the result subject. |
| `MailTo` | Compose the email from optional metadata, introductory text, and newest logs; reuse send_mail and WasMailSent. |
| `parse_syncoid_ts` | Parse name-encoded syncoid timestamps with signed or implicit-positive GMT offsets for UTC comparisons. |
| `delete_syncoid_snapshots` | List snapshots for one dataset, match escaped hostnames, group and sort by UTC time, protect newest N, apply optional age cutoff, and preview or destroy individual candidates. The original no-retention and zero-duration behavior remains unchanged. |
| `parse_older_than` | Convert Nd/Nw/Nm to timedeltas (months are 30 days) and reject malformed age strings during argument parsing. |
| `delete_old_files` | Group matching log/error filenames by timestamp, protect newest N groups, and preview/remove eligible older files after successful processing. |
| `main` | Parse CLI and optional MQTT config before cleanup, call run_cleanup, preserve exit/error behavior, build the final JSON report, and remove the per-run warning observer. |
| `run_cleanup` | Run the existing root check, input reading, per-dataset pruning, email finalization, log retention, and empty error-log removal. Expose diagnostics to main without putting MQTT into deletion helpers. |

## mqtt_notifications.py

| Function or method | What it does and why |
| --- | --- |
| `load_mqtt_config` | Merge defaults, reject invalid/unknown options, enforce topic/type/TLS relationships, and resolve certificate paths relative to the JSON file before cleanup begins. |
| `build_mqtt_report` | Construct the automation's exact success/failure schema with native booleans and integer exit status, reusing backup metadata and bounded command diagnostics. |
| `notify_mqtt` | Skip disabled/default dry-run delivery; otherwise send config/report on worker stdin with a timeout. Log sanitized delivery failure without replacing cleanup's result. |
| `publish_worker` | Import optional Paho only in the worker, configure authentication and verified TLS, and publish one non-retained JSON report before disconnecting. |

## tests/test_project.py

| Function or method | What it does and why |
| --- | --- |
| `arguments` | Construct representative parsed CLI fields for report tests. |
| `ConfigTests.load` | Write a temporary JSON config and exercise the real config loader for validation tests. |
| `ConfigTests.test_example_covers_every_option` | Verify example covers every option to catch regressions in that contract. |
| `ConfigTests.test_defaults` | Verify defaults to catch regressions in that contract. |
| `ConfigTests.test_invalid_options` | Verify invalid options to catch regressions in that contract. |
| `ConfigTests.test_invalid_topic_and_shape` | Verify invalid topic and shape to catch regressions in that contract. |
| `ConfigTests.test_relative_certificate_paths` | Verify relative certificate paths to catch regressions in that contract. |
| `ReportTests.test_success_schema_and_types` | Verify success schema and types to catch regressions in that contract. |
| `ReportTests.test_failure_command_diagnostics` | Verify failure command diagnostics to catch regressions in that contract. |
| `ReportTests.test_fallback_title_and_output_limit` | Verify fallback title and output limit to catch regressions in that contract. |
| `ReportTests.test_disabled_and_default_dry_run_do_not_launch_worker` | Verify disabled and default dry run do not launch worker to catch regressions in that contract. |
| `ReportTests.test_worker_input_and_timeout` | Verify worker input and timeout to catch regressions in that contract. |
| `ReportTests.test_dry_run_requires_explicit_publish_opt_in` | Verify dry run requires explicit publish opt in to catch regressions in that contract. |
| `ReportTests.test_delivery_failure_is_logged_and_secret_not_echoed` | Verify delivery failure is logged and secret not echoed to catch regressions in that contract. |
| `ReportTests.test_timeout_is_nonfatal` | Verify timeout is nonfatal to catch regressions in that contract. |
| `ReportTests.test_worker_tls_and_auth` | Verify worker tls and auth to catch regressions in that contract. |
| `LifecycleTests.invoke` | Drive real argument parsing and cleanup lifecycle with temporary lists and mocked ZFS/mail/log output to test status behavior without touching real datasets. |
| `LifecycleTests.test_success_final_report` | Verify success final report to catch regressions in that contract. |
| `LifecycleTests.test_original_mode_needs_no_mqtt` | Verify original mode needs no mqtt to catch regressions in that contract. |
| `LifecycleTests.test_root_rejection_reports_failure` | Verify root rejection reports failure to catch regressions in that contract. |
| `LifecycleTests.test_command_failure_reports_stderr` | Verify command failure reports stderr to catch regressions in that contract. |
| `LifecycleTests.test_missing_input_reports_failure_before_zfs` | Verify missing input reports failure before zfs to catch regressions in that contract. |
| `LifecycleTests.test_finalization_failure_cannot_report_success` | Verify finalization failure cannot report success to catch regressions in that contract. |
| `LifecycleTests.test_mail_warning_is_nonfatal` | Verify mail warning is nonfatal to catch regressions in that contract. |
| `LifecycleTests.test_interrupt_is_never_success` | Verify interrupt is never success to catch regressions in that contract. |
| `LifecycleTests.test_invalid_config_stops_before_cleanup` | Verify invalid config stops before cleanup to catch regressions in that contract. |
| `RetentionTests.prune` | Feed controlled ZFS listing output to the real pruning helper and capture the proposed destruction arguments. |
| `RetentionTests.test_matching_count_and_dry_run` | Verify matching count and dry run to catch regressions in that contract. |
| `RetentionTests.test_original_no_retention_behavior_is_preserved` | Verify original no retention behavior is preserved to catch regressions in that contract. |
| `RetentionTests.test_age_and_count_work_together` | Verify age and count work together to catch regressions in that contract. |
| `RetentionTests.test_log_dry_run_and_group_retention` | Verify log dry run and group retention to catch regressions in that contract. |
| `receive_packet` | Decode fixed header, variable remaining length, and payload from a test client's MQTT packet. |
| `receive_packet.read_exact` | Read the requested byte count or fail on disconnect so packet tests handle partial socket reads correctly. |
| `BrokerIntegrationTests.exchange` | Start a loopback-only broker fixture and invoke the real Paho worker for successful delivery, CONNACK refusal, or timeout scenarios. |
| `BrokerIntegrationTests.exchange.serve` | Accept the local MQTT connection, send the selected broker response, capture topic/JSON/flags, and acknowledge QoS 1 or 2 packets. |
| `BrokerIntegrationTests.test_real_qos_0_1_2_delivery` | Verify real qos 0 1 2 delivery to catch regressions in that contract. |
| `BrokerIntegrationTests.test_broker_rejection` | Verify broker rejection to catch regressions in that contract. |
| `BrokerIntegrationTests.test_stalled_broker_is_killed_at_timeout` | Verify stalled broker is killed at timeout to catch regressions in that contract. |

## Commands and entry points

| Command | What it does and why |
| --- | --- |
| `python3 CleanUpInSyncoidSnapshots.py --help` / `-h` | Print every accepted CLI argument; no root check or cleanup. |
| `python3 CleanUpInSyncoidSnapshots.py --version` | Print `__version__` and exit, allowing deployments to identify their release. |
| `--command dry-run` | List deletion candidates but skip ZFS destruction and old-log pruning; still creates logs and can email. |
| `--command delete` | Destroy each selected snapshot and then prune eligible logs after successful processing. |
| `zfs list -H -t snapshot -o name DATASET` | Obtain script-readable snapshot names for one explicit dataset without requesting recursion. |
| `zfs destroy SNAPSHOT` | Delete one chosen snapshot without recursive/force flags; checked failure stops cleanup. |
| `mail -s SUBJECT [--attach FILE ...] RECIPIENT` | Deliver optional logs/body with mail options placed before the recipient. |
| `python -B mqtt_notifications.py --publish` | Internal worker only; parent sends validated config/report JSON on stdin. `-B` avoids worker bytecode caches. |
| `python3 -m venv .venv` | Create an isolated interpreter environment for the optional MQTT dependency. |
| `.venv/bin/python -m pip install -r requirements-mqtt.txt` | Install the supported Paho 2.x dependency into that environment. |
| `cp mqtt-config-example.json mqtt-config.json` | Make a local editable broker configuration without modifying the reference example. |
| `chmod 600 mqtt-config.json` | Restrict access to a file that can contain broker credentials. |
| `sudo python3 ...` / `sudo .venv/bin/python ...` | Run the chosen interpreter as root, satisfying the existing cleanup guard. |
| `python -B -m unittest discover -s tests -v` | Run safe tests; actual MQTT uses loopback, while ZFS/mail remain mocked. |
| Home Assistant blueprint / `trigger: mqtt` | Subscribe to the cleanup result topic and report completion in Home Assistant; receiving status does not itself wait for or control cleanup sequencing. |

All remaining CLI options, their aliases, defaults, and uses are listed in the
README's **All CLI options** table. MQTT configuration options and JSON fields
are documented in its **MQTT configuration** section. The module's `DEFAULTS`
constant and mqtt-config-example.json contain the same optional setting keys.

## Files and retained assets

| File | Purpose |
| --- | --- |
| `CleanUpInSyncoidSnapshots.py` | CLI, original cleanup/email/log helpers, app version, and result lifecycle. |
| `mqtt_notifications.py` | Optional MQTT configuration, schema, and worker implementation. |
| `requirements-mqtt.txt` | Optional third-party dependency range. |
| `mqtt-config-example.json` | All supported broker settings with placeholder address and no real password. |
| `home-assistant/CleanUpInSyncoidSnapshots-mqtt-persistent-notification.yaml` | Example Home Assistant automation blueprint that receives this application’s MQTT final report and creates configurable persistent notifications without controlling cleanup. |
| `datasets-example`, `hostnames-example` | Original input examples, preserved byte-for-byte. |
| `.github/CODEOWNERS` | Original repository ownership metadata, preserved byte-for-byte. |
| `tests/test_project.py` | Safe unit/lifecycle/retention tests and loopback MQTT integration fixtures. |
| `README.md` | Current setup, commands, configuration, JSON contract, and operational behavior. |
| `DISCLAIMER.md` | Original author disclaimers and license notice moved out of the usage guide. |
| `VERSIONING.md` | Release increment policy and complete recorded changes. |
| `commented_code_map.md` | This function/command explanation map. |
| `VERIFICATION.md` | Release verification evidence, archive manifest, and test limitations. |

## Safety boundaries and existing limitations

- ZFS receives argument lists through the original run_cmd; no shell is introduced.
- MQTT code cannot invoke snapshot destruction, and dry-run MQTT delivery is opt-in.
- Root restriction, matching, retention, and destructive command construction remain unchanged.
- No-retention snapshot deletion and zero-duration cutoff behavior follow the original
  implementation, as explicitly documented in README.md.
- Existing prefix-based log selection/pruning and second-resolution filenames remain;
  concurrent runs are not coordinated, and current logs can be removed by retention.
- MQTT config validation precedes cleanup, but broker reachability and dependency
  availability are checked only when publishing. Notification transport failure is nonfatal.
- Secrets travel to the publisher through stdin; subprocess diagnostic text is not echoed.
- The worker entry point is internal, not a general-purpose subscriber or command listener.
