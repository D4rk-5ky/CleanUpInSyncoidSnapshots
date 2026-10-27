# CleanUpInSyncoidSnapshots

CleanUpInSyncoidSnapshots removes matching Syncoid-created ZFS snapshots, can preview the exact deletion set first, produces a final dry-run report, prunes its own log groups with the same retention settings, and can optionally send email and typed MQTT completion reports, and offers independent Home Assistant live preview of snapshot decisions and deletions.

Current source application version: **0.0.20**. Run `python3 CleanUpInSyncoidSnapshots.py --version` to confirm it.

The included `dist/CleanUpInSyncoidSnapshots` is the preserved **0.0.16** Linux x86-64 executable. Use the Python source for the current release and its reporting integration. To produce a current standalone executable, build from a separate disposable project copy with the helper below; the helper replaces that copy's existing `dist/`. Verify the resulting executable with `--version` before installing it.

## Requirements

- Linux with ZFS. Source-mode runs require Python **3.10 or newer**; the PyInstaller executable bundles its Python runtime.
- Run cleanup as root with `sudo`.
- `zfs` must be available in `PATH`.
- Python 3.10 needs the `tomli` compatibility package from `requirements.txt`; Python 3.11+ uses the standard-library `tomllib` module.
- Email is optional and requires a configured `mail`/`mailx` command that supports `-s` and `--attach`.
- MQTT is optional and requires Paho MQTT from `requirements-mqtt.txt`.

For Python 3.10, or when you prefer an isolated environment:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
```

If MQTT will be enabled, install its optional dependency as well:

```bash
.venv/bin/python -m pip install -r requirements-mqtt.txt
```

`requirements-mqtt.txt` includes the base requirements automatically.

## Standalone PyInstaller build

A one-file Linux executable can be built with the included PyInstaller release files:

```bash
./build-pyinstaller.sh
```

Optional environment overrides are `PYTHON_BIN` (default `python3`) and `VENV_DIR` (default `.venv-build`). `VENV_DIR` must point to a disposable build environment: the helper deletes it before building.

The build script recreates a clean `.venv-build/`, installs `requirements-build.txt`, removes old `build/` and `dist/` output, recreates `dist/` empty, and runs the included `CleanUpInSyncoidSnapshots.spec`. The final executable is left directly in:

```text
dist/CleanUpInSyncoidSnapshots
```

`requirements-build.txt` includes the normal MQTT dependency set, forces the `tomli` fallback module into the build environment, and installs PyInstaller. The spec explicitly collects all `paho` and `tomli` submodules; the application modules and Python standard-library/runtime pieces are collected by PyInstaller. This means the frozen executable does not require a separate Python, Paho MQTT, or Tomli installation at runtime. ZFS and the optional external `mail`/`mailx` program remain host tools and are not bundled.

PyInstaller builds are platform/architecture specific. Build the executable on the Linux architecture where you intend to run it (or on a compatible build system); this project does not treat PyInstaller as a cross-compiler. Runtime TOML, dataset/hostname files, and optional TLS certificate/key files remain external and are supplied by the user.

After PyInstaller finishes, the build script verifies that `dist/` contains **exactly one entry**: the executable `CleanUpInSyncoidSnapshots`. Any extra file, directory, or hidden entry in `dist/` makes the build fail. It then smoke-tests that executable with `--version` and `--help`.

## Configuration

Copy the complete example and protect it because it can contain mail and MQTT credentials:

```bash
cp configs/config-example.toml configs/config.toml
chmod 600 configs/config.toml
```

The distributed `configs/config.toml` and `configs/config-example.toml` are identical safe examples. Every runtime setting is in this TOML file. Relative filesystem paths are resolved relative to the TOML file itself, not the shell's current directory.

The example defaults to `command = "dry-run"`, with both mail and MQTT disabled.

### `[cleanup]`

| Setting | Required/default | Meaning |
| --- | --- | --- |
| `command` | Required | `"dry-run"` previews candidates; `"delete"` performs snapshot destruction. |
| `datasets_file` | Required | File containing one exact local ZFS dataset per non-empty line. Dataset-level ZFS failures always make the final run fail; the two continuation options below decide whether later configured datasets are still attempted. |
| `syncoid_hosts_file` | Required | File containing Syncoid hostnames, one per line. Blank lines and whole-line `#` comments are ignored. |
| `older_than` | `""` | Optional age cutoff such as `7d`, `2w`, or `3m`. `m` means 30 days. Empty disables the age cutoff. |
| `retain_count` | `0` | Protect the newest N matching snapshots per hostname/dataset and the newest N log timestamp groups. Negative values are normalized to 0. |
| `continue_on_missing_dataset` | `true` | When ZFS explicitly reports `dataset does not exist`, record the failure and continue with the next configured dataset. `false` stops immediately. The final result is failure either way. |
| `continue_on_other_failures` | `true` | When another checked ZFS `list` or `destroy` command fails for a dataset, record the failure and continue with the next configured dataset. `false` stops immediately. Global/config/root/input failures are not made recoverable. |

### `[logging]`

| Setting | Required/default | Meaning |
| --- | --- | --- |
| `prefix` | Script basename | Prefix for generated `.log` and `.err` files. Empty uses the script basename. |

The application always creates and uses a `logs/` directory beside the running application. Source runs place it beside `CleanUpInSyncoidSnapshots.py`; a PyInstaller build places it beside the frozen executable (normally `dist/logs/`). It never falls back to `/tmp` or the current working directory. If that directory cannot be created or written, the run fails instead of silently placing logs somewhere else.

### `[report]`

| Setting | Required/default | Meaning |
| --- | --- | --- |
| `title` | `""` | Optional run name. Sent in both MQTT JSON `name` and `title`, shown at the top of the email body, and prefixed as `[run name]` to every email subject. Blank leaves email subjects unchanged; MQTT falls back to `LiveBackupName`, then `CleanUpInSyncoidSnapshots`. Multiline whitespace is collapsed in the subject only. |
| `comment` | `""` | Optional free-form comment included in email and MQTT reports. |

Name a run in its TOML configuration:

```toml
[report]
title = "NAS nightly cleanup"
comment = "After Syncoid replication"
```

For this example, MQTT includes `"title": "NAS nightly cleanup"`, and email subjects include `[NAS nightly cleanup] Syncoid cleanup SUCCESS - logs attached` or the corresponding `FAILED` / `DRY-RUN` status. The run name is also included on root-check failure emails. Use a different title in each job's configuration. It does not change log filenames, MQTT topics or cleanup selection. MQTT `name` and `title` both use the friendly run name. `job` stays the stable log prefix, and `job_type` identifies Syncoid snapshot cleanup. Existing mail/MQTT enablement and `on_success` rules still decide which reports are sent.

### `[mail]`

Mail is optional and disabled unless `enabled = true`.

| Setting | Required/default | Meaning |
| --- | --- | --- |
| `enabled` | `false` | Enables email delivery. |
| `recipient` | `""` | Required to be non-empty when mail is enabled. |
| `on_success` | `false` | `false` sends mail only on failure; `true` also sends mail after success. A successful dry-run follows the same rule as a successful delete run. |

Mail failure is logged but does not turn an otherwise successful cleanup into a fatal cleanup failure. When MQTT is enabled, such logged errors are reflected as `warning: true` in the final MQTT report.

### `[mqtt]`

The complete option reference and integration usage are in the `modules/mqtt_reporting.py` module docstring and comments in `configs/config.toml` / `configs/config-example.toml`. Both examples preserve the completion topic `homeassistant/CleanUpInSyncoidSnapshots/Zotac-RI531/status` and use placeholder credentials.

- `MQTT_JSON_Status` enables final completion JSON independently of live preview. `SendMQTTOnSuccess` defaults to false: failures report whenever completion reporting is enabled, while successes require opt-in. `MQTTJSONOnDryRun` independently controls completion previews and defaults to true, preserving the existing dry-run failure policy.
- `LiveMQTTEnabled` independently enables snapshot live state. `LiveMQTTDiscovery` publishes retained discovery; `LiveManufacturer` identifies jobs for the Markdown card. Live events are controlled by `LiveNotifyStart`, `LiveNotifySuccess`, and `LiveNotifyFailure`; they never send Pushover or control completion reports. `LiveMQTTOnDryRun` defaults false, and opted-in previews never overwrite the retained last real result.
- Shared transport uses `broker_address`, `broker_port`, `mqtt_username`, `mqtt_password` and optional `MQTTTLS` / certificate settings. Completion and live have separate timeout, client-ID and QoS settings. Certificate paths remain relative to the TOML file.
- Existing MQTT keys (`enabled`, `host`, `port`, `topic`, `username`, `password`, `on_success`, `client_id`, `qos`, `timeout`, `tls`, `ca_certs`, `certfile`, `keyfile`) remain supported aliases. When both spellings are supplied, the new supplied option names take precedence. No installed topic is automatically changed.

Completion messages remain non-retained. Live state/events use separate `job-live/<unique device>/...` topics; discovery and the last real live result are retained. Credentials remain on publisher stdin; network failures do not replace the job's exit code. No integration JSON configuration, state, cache or log files are created. Existing application logs are still produced as before.

### Success/failure notification rule

Email and completion MQTT use the same success opt-in rule (MQTT `SendMQTTOnSuccess` is the supplied spelling of legacy `on_success`). Live preview has independent controls. `enabled` decides whether that channel is active; `on_success` decides whether successful runs are also reported. A dry-run uses the same success/failure decision as a normal delete run. The application applies this decision at the lifecycle boundary before invoking either success-notification path; MQTT also keeps a second defensive check inside the publisher wrapper.

| Channel enabled | `on_success` | Run result | Notification |
| --- | --- | --- | --- |
| `false` | either | success or failure | No notification through that channel. |
| `true` | `false` | failure | Send/publish the failure report. |
| `true` | `false` | success | Do not send/publish. |
| `true` | `true` | failure | Send/publish the failure report. |
| `true` | `true` | success | Send/publish the success report. |

With the default `MQTTJSONOnDryRun = true`, a failed dry-run still sends mail and/or MQTT through each enabled channel even when `on_success = false`, while a successful dry-run is silent unless `on_success = true` for that channel. On a successful delete or dry-run with an enabled channel and `on_success = false`, the local log records the exact suppression reason: `Success mail report suppressed by mail.on_success=false.` for mail and `Success MQTT report suppressed by mqtt.on_success=false.` for MQTT.

## Dataset and hostname files

Example dataset file:

```text
tank/data
tank/backups
```

Blank dataset lines are ignored. Dataset comments are not supported. The script processes only the explicitly listed datasets and does not ask ZFS for recursive dataset traversal. Dataset-level checked ZFS failures are always recorded as failures. With the default continuation settings, the script moves on to later configured datasets after either an explicit missing-dataset error or another checked ZFS list/destroy failure; both behaviors can be disabled independently in `[cleanup]`.

Example hostname file:

```text
# Exact Syncoid hostnames
backup-server
laptop01
```

Hostname matching is exact and case-sensitive. Blank lines and whole-line `#` comments are ignored. Inline comments are not supported.

## Running the application

The application has one operational CLI setting: which TOML configuration file to load. Standard help and version output are also available. Help explains both TOML modes, the root requirement, notification policy, config-relative paths, and the no-age/zero-retention deletion case.

| Flag | Required | What it does |
| --- | --- | --- |
| `-c CONFIG` | Yes for a cleanup run | Selects the TOML configuration file. |
| `--config CONFIG` | Yes for a cleanup run | Long-form alias for `-c CONFIG`; it loads the same TOML file. |
| `-h`, `--help` | No | Shows the built-in CLI help, all public flags, and examples, then exits without starting cleanup. |
| `--version` | No | Prints the application name/version and exits without loading configuration, creating logs, checking root, or running ZFS commands. |

The configuration selector only chooses the TOML file. Cleanup mode, input files, retention, continuation behavior, logging, email, report metadata, and MQTT settings all come from that file.

Run it with the short option:

```bash
sudo python3 CleanUpInSyncoidSnapshots.py -c configs/config.toml
```

Or use the equivalent long option:

```bash
sudo python3 CleanUpInSyncoidSnapshots.py --config /etc/cleanup-syncoid/config.toml
```

When using the documented virtual environment:

```bash
sudo .venv/bin/python CleanUpInSyncoidSnapshots.py -c configs/config.toml
```

When using the PyInstaller executable:

```bash
sudo ./dist/CleanUpInSyncoidSnapshots -c configs/config.toml
```

To display help without running cleanup:

```bash
python3 CleanUpInSyncoidSnapshots.py --help
```

To display the installed application version without running cleanup:

```bash
python3 CleanUpInSyncoidSnapshots.py --version
```

The preserved frozen executable exposes the same CLI; its `--version` reports 0.0.16:

```bash
./dist/CleanUpInSyncoidSnapshots --help
./dist/CleanUpInSyncoidSnapshots --version
```

No other public operational flags are accepted. For example, `--command dry-run` is rejected because `command = "dry-run"` belongs in the TOML file. If no configuration option is supplied, argument parsing exits before cleanup starts.

## Recommended workflow

First configure:

```toml
[cleanup]
command = "dry-run"
```

Run the application and review every listed candidate. When the preview is correct, change only:

```toml
command = "delete"
```

Then run the same `-c config.toml` command again.

## Retention behavior

Snapshot names must match:

```text
<dataset>@syncoid_<hostname>_YYYY-MM-DD:HH:MM:SS-GMT[+/-]HH:MM
```

A positive timezone offset without an explicit `+` is also accepted. Nonmatching snapshots are ignored. A name that matches the pattern but contains an invalid date or timezone is logged and skipped. This logged error does not itself make the cleanup exit unsuccessfully; any final MQTT report records it as a warning.

Snapshots are grouped by configured hostname within each dataset and sorted newest-first by the timestamp embedded in the snapshot name, normalized to UTC.

- `retain_count > 0` always protects the newest N matching snapshots for each hostname/dataset.
- With `older_than` configured, only unprotected snapshots strictly older than the cutoff are candidates.
- With no `older_than`, every unprotected matching snapshot is a candidate.
- Therefore, `older_than = ""` together with `retain_count = 0` means every matching snapshot is selected for deletion in `delete` mode. Use `dry-run` first.
- For `0d`, `0w`, and `0m`: for snapshot pruning, a zero-duration value acts like no cutoff because a zero `timedelta` is falsey in the existing cleanup code.

Each snapshot is destroyed individually with:

```text
zfs destroy SNAPSHOT
```

No recursive or force flags are added. Any checked `zfs list` or `zfs destroy` failure makes the final run fail, and deletions already completed are not rolled back. By default, a dataset-level command failure is recorded and processing moves on to the next configured dataset. Set `continue_on_missing_dataset = false` to stop immediately on the explicit missing-dataset diagnostic, or set `continue_on_other_failures = false` to stop immediately on other checked ZFS list/destroy failures. A failed `zfs destroy` stops further snapshot processing inside that dataset before the outer loop decides whether to continue with the next dataset.

## Log retention behavior

`.log` and `.err` files sharing the same timestamp are treated as one log group. Successful `delete` runs prune eligible groups after snapshot processing. `dry-run` never removes old log groups, but it previews them before the final dry-run report is written so the report and optional success notifications include the old-log candidate counts.

Log retention uses the same `older_than` and `retain_count` settings as snapshot retention. With both disabled, log pruning does nothing. Unlike snapshot selection, `0d`, `0w`, and `0m` apply a cutoff of now to logs; newest-N protection still applies. Log groups are chosen from their filename timestamps. Log timestamps use local time. The current run's empty `.err` file is removed at the end, including during dry-run. Dry-run creates the log directory/files and can send enabled notifications; it previews snapshot and old-log deletions.

## Root requirement

Actual cleanup and dry-run execution both require root. The guard runs before reading dataset/hostname files or issuing ZFS commands. If root is missing, the application logs the error, optionally mails it, optionally reports it through MQTT, and exits with code 1.

## Exit status and troubleshooting

- `0`: cleanup or preview completed. Notification delivery errors can still appear in logs without changing this result.
- `1`: cleanup failed, including any recorded dataset failure even when continuation was enabled.
- `2`: invalid CLI arguments or configuration rejected before cleanup starts.
- An interrupted run is reported to MQTT with `exit_code = 130`. The process retains Python's normal interrupt termination behavior.

Inspect `logs/` beside the source script or installed executable for diagnostics. A dry-run is a point-in-time preview; snapshot changes between runs can change the selected set. Coordinate scheduled cleanup jobs so they do not overlap: the application has no run lock. Uncaught runtime exceptions can include a traceback.

## Dataset failure continuation

Two independent `[cleanup]` options control what happens after a checked ZFS command fails for one configured dataset:

```toml
continue_on_missing_dataset = true
continue_on_other_failures = true
```

- `continue_on_missing_dataset` applies whenever a checked ZFS `list` or `destroy` failure contains `dataset does not exist` in stderr (case-insensitive). Classification uses that diagnostic, regardless of which command returned it.
- `continue_on_other_failures` applies to other checked ZFS `list` or `destroy` failures, such as permission, pool/I/O, busy-snapshot, or similar nonzero ZFS results.
- `true` records the failure, keeps the overall run failed, and continues with the next configured dataset.
- `false` records the failure and stops cleanup immediately.
- A failed destroy does not continue with later snapshots inside the same dataset; continuation, when enabled, resumes at the next configured dataset.
- Configuration errors, missing input files, root-check failures, Python/process-start failures, and interrupts are not converted into recoverable dataset failures.

When one or more dataset failures were continued, the application combines them into the final failure summary. The process exits with code `1`, old log pruning is skipped because the run was not successful, enabled failure mail uses a **FAILED** subject, and enabled MQTT publishes `status = "failure"` / `exit_code = 1`. The MQTT `error` field summarizes missing and other failed datasets, while `stderr` preserves bounded original ZFS diagnostics. Failure notifications ignore `on_success`; completion MQTT previews additionally require `MQTTJSONOnDryRun = true` (the default).

## Dry-run report

After entering snapshot processing, a dry-run writes a final `DRY-RUN REPORT` to the normal log. Configuration, log-setup, or root-check failures occur before that report is initialized. On a successful dry-run, old-log retention is previewed first so those counts are included too. The report contains:

- configured dataset count;
- successfully completed dataset count;
- dataset failure count;
- total matching Syncoid snapshot count;
- total snapshots that **WOULD** be deleted;
- per-dataset matched / would-delete counts;
- old log groups and log files that **WOULD** be deleted when the dry-run completed successfully;
- an explicit statement that zero snapshots were actually destroyed and no old logs were deleted.

The initialized dry-run report is written locally at finalization. A successful dry-run email includes it only when `mail.enabled = true` and `mail.on_success = true`. A successful MQTT dry-run report is published only when `mqtt.enabled = true` and `mqtt.on_success = true`; otherwise no success MQTT notifier is invoked. Failed dry-runs still produce the available partial snapshot report and notify through enabled mail regardless of `on_success`; completion MQTT follows the same rule when `MQTTJSONOnDryRun = true` (default). For either successful or failed previews, setting it to false suppresses completion MQTT. In failed runs, old-log retention is marked as not evaluated because failed runs do not proceed to log retention. If the old-log preview itself fails, the dry-run becomes a failed run and follows the normal failure-notification rule.

## MQTT report format

A final MQTT message is JSON with these fields:

```json
{
  "status": "success",
  "success": true,
  "title": "Syncoid snapshot cleanup",
  "name": "Syncoid snapshot cleanup",
  "job": "CleanUpInSyncoidSnapshots",
  "exit_code": 0,
  "warning": false,
  "error": "",
  "stderr": "",
  "command": "delete",
  "dry_run": false,
  "comment": "",
  "version": "0.0.20",
  "timestamp": "2026-10-27T12:00:00+00:00",
  "host": "nas-host",
  "run_id": "unique-run-identifier",
  "schema_version": 1,
  "job_type": "syncoid_snapshot_cleanup",
  "item_unit": "datasets",
  "outcome_item_unit": "snapshots"
}
```

`status` and boolean `success` agree with the integer `exit_code`: 0 means success, every nonzero code means failure. The original overall cleanup exit code is preserved; checked child-command codes are included in optional failed-dataset diagnostics. `warning` becomes true when error-level messages were logged during an otherwise successful MQTT-enabled run. Dataset failures can combine diagnostics from multiple datasets; the completion report includes the latest 4,000 characters of actual child-command stderr, including successful-command diagnostics. It never substitutes stdout or log text. `failed_datasets` is an optional extension carrying dataset/command failures; generic reports omit dataset sections.

Dry-run MQTT reports additionally contain a `dry_run_report` object such as:

```json
{
  "datasets_configured": 2,
  "datasets_completed": 2,
  "dataset_failures": 0,
  "snapshots_matched": 18,
  "snapshots_would_delete": 6,
  "log_retention_evaluated": true,
  "log_groups_would_delete": 1,
  "log_files_would_delete": 2,
  "datasets": [
    {"dataset": "tank/data", "matched": 10, "selected": 4},
    {"dataset": "tank/backups", "matched": 8, "selected": 2}
  ]
}
```

`selected` in each dataset entry means “would delete” when `dry_run = true`.

## Home Assistant examples

`examples/live-preview-card.yaml` remains a Markdown card with `content: |`. Match its manufacturer variable to `LiveManufacturer`. It discovers devices automatically, follows stable role markers after entity renames, displays snapshot outcomes/reasons, dataset scan details, actual stderr, runtime and heartbeat, and labels retained prior results. Main progress counts entries in `datasets_file`: with five nonblank entries, two processed entries show **Datasets: 2 / 5 processed (40%)**. The current dataset also has a one-based position (for example, position 3 / 5 while the third is running). Failed attempts count as processed while keeping the job failed; interruptions leave the current entry unfinished. Blank lines are ignored and repeated entries count separately. The total is known as soon as the file is read, independent of snapshot counts or listing failures. Snapshot outcomes have their own labels/counters; they do not advance dataset progress. Before reading the file, totals stay unknown. Cleanup has no measured byte or transfer rate, so transfer panels are hidden. A lost heartbeat for a newer run never reuses an older success as that run's outcome.

`examples/success-failure-automation.yaml` is a completion-only Pushover example on the existing completion topic. Its comments explain the action placeholder and duplicate-notification handling. It rejects previews and inconsistent reports before actions; live state/events never trigger it. It adds no scheduling or job sequence. Install examples manually after reviewing the module/config comments; tests do not modify HA or send live notifications.


`examples/CleanUpInSyncoidSnapshots-mqtt-persistent-notification.yaml` is a receive-only Home Assistant automation blueprint. Configure its MQTT topic to exactly match `[mqtt].topic` in your TOML file.

The blueprint can independently show clean success, success-with-warning, failure, and dry-run notifications, displays the aggregate dry-run counts when present, and can either replace the previous notification or create separate notifications. It does not publish commands, start cleanup, or invoke ZFS.

## Project files

Runtime helpers are in `modules/`, the distributed configuration/input examples are in `configs/`, and Home Assistant YAML examples are in `examples/`. Run the root application with `-c configs/config.toml`. Keep config-relative input/certificate paths relative to the selected TOML file. Release metadata such as `PACKAGE_MANIFEST.json` stays at the root; it is not a JSON example. No standalone JSON example file was supplied in this project.


- `CleanUpInSyncoidSnapshots.py` - application entry point and original cleanup/email/log lifecycle.
- `modules/__init__.py` - package marker for shared-module imports and frozen builds.
- `modules/config_loader.py` - TOML loading, validation, path resolution, and conversion into the existing runtime values.
- `configs/config-example.toml` - complete commented configuration example containing every supported setting.
- `modules/mqtt_notifications.py` - reused legacy transport validation, typed completion adapter, bounded publishing, and internal completion worker.
- `modules/mqtt_reporting.py` - template-derived completion contract, independent live preview, generic item API, and small cleanup adapter; includes usage instructions.
- `configs/config.toml` - complete safe application/reporting configuration; identical to the example.
- `examples/success-failure-automation.yaml`, `examples/live-preview-card.yaml` - commented completion/Pushover and manufacturer-discovered Markdown card examples.
- `tests/test_mqtt_reporting.py` - reporting, lifecycle, rendering and localhost integration regressions.
- `requirements.txt` - Python 3.10 TOML compatibility dependency.
- `requirements-mqtt.txt` - optional MQTT dependency plus base requirements.
- `requirements-build.txt` - complete PyInstaller build dependency set, including MQTT and the TOML fallback.
- `CleanUpInSyncoidSnapshots.spec` - one-file PyInstaller specification that explicitly collects Paho and Tomli runtime modules.
- `build-pyinstaller.sh` - reproducible build helper; creates the build venv, recreates `dist/` empty, and fails unless the only final entry is `dist/CleanUpInSyncoidSnapshots`.
- `dist/` - contains the preserved executable identified above; generated final-output directory when building. It is ignored by Git, deleted/recreated empty on every build, and must contain only `CleanUpInSyncoidSnapshots` when the build succeeds.
- `configs/datasets-example`, `configs/hostnames-example` - input-file examples.
- `examples/` - receive-only Home Assistant MQTT notification blueprint.
- `tests/test_project.py` - regression tests with ZFS/mail mocked and optional loopback MQTT integration tests.
- `commented_code_map.md` - current function and command map.
- `VERSIONING.md`, `versioning.md` - synchronized copies of the complete release-by-release change record and patch-99 rollover policy.
- `VERIFICATION.md` - verification evidence and limits for this release.
- `PACKAGE_MANIFEST.json` - comparison with the supplied archive, including original/release SHA-256 hashes, sizes, and permission information. Its own hash is omitted to avoid circular metadata; the external zip checksum covers it.
- `DISCLAIMER.md` - safety/liability notice.
- `.gitignore` - excludes local runtime configs, generated logs, Python caches, virtual environments, and build outputs while keeping the shipped example tracked.

## Safety notes

This application can destroy ZFS snapshots. Review the included [DISCLAIMER.md](DISCLAIMER.md), keep independent backups, use `dry-run` before `delete`, and verify the configured dataset, hostname, retention, and path values before running against important data.

## ⚠️ Disclaimer / Liability

**Use this script at your own risk.**

The author takes **no responsibility or liability** for any data loss, service disruption, misconfiguration, service outage, missed backups, credential exposure, or other damage that may occur from using this script.

Before running it in production, you **must**:

- Read the entire source code
- Understand exactly what it does (and what it does *not* do)
- Review and adapt it to your own environment
- Test it carefully in a non‑production setup

By using this script, **you accept full responsibility** for its effects.

⚠️ AI-assisted / vibe-coded experimental software. Use at your own risk.

## Disclaimer

This project is AI-assisted / vibe-coded software created as a hobby project. It has not been professionally audited and may contain bugs, unsafe behavior, data-loss issues, security problems, or incorrect assumptions.

You are responsible for reviewing the code, testing it in a safe environment, making backups, and understanding what it does before using it on real data. The author is not responsible for damage, data loss, broken systems, security issues, or other problems caused by using this software.

---

