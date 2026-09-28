# CleanUpInSyncoidSnapshots

CleanUpInSyncoidSnapshots removes matching Syncoid-created ZFS snapshots, can preview the exact deletion set first, prunes its own log groups with the same retention settings, and can optionally send email and MQTT JSON status reports.

Current application version: **0.0.8**.

## Requirements

- Linux with ZFS and Python **3.10 or newer**.
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

## Configuration

Copy the complete example and protect it because it can contain mail and MQTT credentials:

```bash
cp config-example.toml config.toml
chmod 600 config.toml
```

Every runtime setting is in this TOML file. Relative filesystem paths are resolved relative to the TOML file itself, not the shell's current directory.

The example defaults to `command = "dry-run"`, with both mail and MQTT disabled.

### `[cleanup]`

| Setting | Required/default | Meaning |
| --- | --- | --- |
| `command` | Required | `"dry-run"` previews candidates; `"delete"` performs snapshot destruction. |
| `datasets_file` | Required | File containing one exact local ZFS dataset per non-empty line. Dataset-level ZFS failures always make the final run fail; the two continuation options below decide whether later configured datasets are still attempted. |
| `syncoid_hosts_file` | Required | File containing Syncoid hostnames, one per line. Blank lines and whole-line `#` comments are ignored. |
| `older_than` | `""` | Optional age cutoff such as `7d`, `2w`, or `3m`. `m` means 30 days. Empty disables the age cutoff. |
| `retain_count` | `0` | Protect the newest N matching snapshots per hostname/dataset and the newest N log timestamp groups. Negative values are normalized to 0 to preserve earlier behavior. |
| `continue_on_missing_dataset` | `true` | When ZFS explicitly reports `dataset does not exist`, record the failure and continue with the next configured dataset. `false` stops immediately. The final result is failure either way. |
| `continue_on_other_failures` | `true` | When another checked ZFS `list` or `destroy` command fails for a dataset, record the failure and continue with the next configured dataset. `false` stops immediately. Global/config/root/input failures are not made recoverable. |

### `[logging]`

| Setting | Required/default | Meaning |
| --- | --- | --- |
| `prefix` | Script basename | Prefix for generated `.log` and `.err` files. Empty uses the script basename. |

The application always creates and uses a `logs/` directory beside the actual `CleanUpInSyncoidSnapshots.py` file. It never falls back to `/tmp` or the current working directory. If that directory cannot be created or written, the run fails instead of silently placing logs somewhere else.

### `[report]`

| Setting | Required/default | Meaning |
| --- | --- | --- |
| `title` | `""` | Optional title written into email and used as MQTT report title. MQTT falls back to `CleanUpInSyncoidSnapshots` when blank. |
| `comment` | `""` | Optional free-form comment included in email and MQTT reports. |

### `[mail]`

Mail is optional and disabled unless `enabled = true`.

| Setting | Required/default | Meaning |
| --- | --- | --- |
| `enabled` | `false` | Enables email delivery. |
| `recipient` | `""` | Required to be non-empty when mail is enabled. |
| `on_success` | `false` | `false` sends mail only on failure; `true` also sends mail after success. |

Mail failure is logged but does not turn an otherwise successful cleanup into a fatal cleanup failure. When MQTT is enabled, such logged errors are reflected as `warning: true` in the final MQTT report.

### `[mqtt]`

MQTT is optional and disabled unless `enabled = true`.

| Setting | Required/default | Meaning |
| --- | --- | --- |
| `enabled` | `false` | Enables final MQTT JSON publishing. |
| `host` | Required when enabled | Broker hostname or IP, without a URL scheme. |
| `port` | `1883` | TCP port, 1-65535. TLS does not change the port automatically. |
| `topic` | Required when enabled | Exact publish topic. `+` and `#` wildcards are rejected. |
| `username` | `""` | Optional broker username. Empty means no username. |
| `password` | `""` | Optional plain TOML string password, for example `password = "<String>"`. A non-empty password requires a username. |
| `client_id` | `""` | Optional client ID. Empty lets the client/broker choose one. |
| `qos` | `1` | MQTT QoS 0, 1, or 2. |
| `timeout` | `15` | Positive maximum seconds for the isolated publisher process, including connection and acknowledgement waits. |
| `tls` | `false` | Enables TLS certificate and hostname verification. |
| `ca_certs` | `""` | Optional CA file. Empty uses system trust roots when TLS is enabled. |
| `certfile` | `""` | Optional mutual-TLS client certificate. Requires `keyfile` and `tls = true`. |
| `keyfile` | `""` | Optional matching private key. Requires `certfile` and `tls = true`. |
| `publish_dry_run` | `false` | Controls successful dry-run preview reports. Failure reports are still published whenever MQTT is enabled; set `true` to also publish successful previews. |

Certificate paths may be absolute or relative to the TOML file. MQTT messages are always published with `retain = false`. Credentials and report data are sent to the isolated publisher through standard input rather than command-line arguments. MQTT delivery failures are nonfatal and do not change the cleanup result.

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

The application has one operational CLI setting: which TOML configuration file to load. Standard help and version output are also available.

| Flag | Required | What it does |
| --- | --- | --- |
| `-c CONFIG` | Yes for a cleanup run | Selects the TOML configuration file. |
| `--config CONFIG` | Yes for a cleanup run | Long-form alias for `-c CONFIG`; it loads the same TOML file. |
| `-h`, `--help` | No | Shows the built-in CLI help, all public flags, and examples, then exits without starting cleanup. |
| `--version` | No | Prints the application name/version and exits without loading configuration, creating logs, checking root, or running ZFS commands. |

The configuration selector only chooses the TOML file. Cleanup mode, input files, retention, continuation behavior, logging, email, report metadata, and MQTT settings all come from that file.

Run it with the short option:

```bash
sudo python3 CleanUpInSyncoidSnapshots.py -c config.toml
```

Or use the equivalent long option:

```bash
sudo python3 CleanUpInSyncoidSnapshots.py --config /etc/cleanup-syncoid/config.toml
```

When using the documented virtual environment:

```bash
sudo .venv/bin/python CleanUpInSyncoidSnapshots.py -c config.toml
```

To display help without running cleanup:

```bash
python3 CleanUpInSyncoidSnapshots.py --help
```

To display the installed application version without running cleanup:

```bash
python3 CleanUpInSyncoidSnapshots.py --version
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

A positive timezone offset without an explicit `+` is also accepted, matching the earlier implementation. Nonmatching snapshots are ignored. A matching snapshot with a malformed timestamp is logged and skipped.

Snapshots are grouped by configured hostname within each dataset and sorted newest-first by the timestamp embedded in the snapshot name, normalized to UTC.

- `retain_count > 0` always protects the newest N matching snapshots for each hostname/dataset.
- With `older_than` configured, only unprotected snapshots strictly older than the cutoff are candidates.
- With no `older_than`, every unprotected matching snapshot is a candidate.
- Therefore, `older_than = ""` together with `retain_count = 0` means every matching snapshot is selected for deletion in `delete` mode. Use `dry-run` first.
- Existing behavior for `0d`, `0w`, and `0m` is preserved: for snapshot pruning, a zero-duration value acts like no cutoff because a zero `timedelta` is falsey in the existing cleanup code.

Each snapshot is destroyed individually with:

```text
zfs destroy SNAPSHOT
```

No recursive or force flags are added. Any checked `zfs list` or `zfs destroy` failure makes the final run fail, and deletions already completed are not rolled back. By default, a dataset-level command failure is recorded and processing moves on to the next configured dataset. Set `continue_on_missing_dataset = false` to stop immediately on the explicit missing-dataset diagnostic, or set `continue_on_other_failures = false` to stop immediately on other checked ZFS list/destroy failures. A failed `zfs destroy` stops further snapshot processing inside that dataset before the outer loop decides whether to continue with the next dataset.

## Log retention behavior

`.log` and `.err` files sharing the same timestamp are treated as one log group. Successful `delete` runs prune eligible groups after snapshot processing. `dry-run` never removes old log groups, but it reports which ones would be removed.

Log retention uses the same `older_than` and `retain_count` settings as snapshot retention. With both disabled, log pruning does nothing. Log timestamps use local time. The current run's empty `.err` file is removed at the end.

## Root requirement

Actual cleanup and dry-run execution both require root. The guard runs before reading dataset/hostname files or issuing ZFS commands. If root is missing, the application logs the error, optionally mails it, optionally reports it through MQTT, and exits with code 1.

## Dataset failure continuation

Two independent `[cleanup]` options control what happens after a checked ZFS command fails for one configured dataset:

```toml
continue_on_missing_dataset = true
continue_on_other_failures = true
```

- `continue_on_missing_dataset` applies only when ZFS explicitly reports `dataset does not exist` while listing the configured dataset.
- `continue_on_other_failures` applies to other checked ZFS `list` or `destroy` failures, such as permission, pool/I/O, busy-snapshot, or similar nonzero ZFS results.
- `true` records the failure, keeps the overall run failed, and continues with the next configured dataset.
- `false` records the failure and stops cleanup immediately.
- A failed destroy does not continue with later snapshots inside the same dataset; continuation, when enabled, resumes at the next configured dataset.
- Configuration errors, missing input files, root-check failures, Python/process-start failures, and interrupts are not converted into recoverable dataset failures.

When one or more dataset failures were continued, the application combines them into the final failure summary. The process exits with code `1`, old log pruning is skipped because the run was not successful, enabled failure mail uses the normal **FAILED** subject, and enabled MQTT publishes `status = "failure"` / `exit_code = 1`. The existing MQTT `error` field summarizes missing and other failed datasets, while `stderr` preserves bounded original ZFS diagnostics. MQTT failure reports are sent even during `dry-run`; `publish_dry_run` only controls successful preview reports.

## MQTT report format

A final MQTT message is JSON with these fields:

```json
{
  "status": "success",
  "title": "Syncoid snapshot cleanup",
  "name": "CleanUpInSyncoidSnapshots",
  "job": "CleanUpInSyncoidSnapshots",
  "exit_code": 0,
  "warning": false,
  "error": "",
  "stderr": "",
  "command": "delete",
  "dry_run": false,
  "comment": "",
  "version": "0.0.8",
  "timestamp": "2026-09-15T12:00:00+00:00"
}
```

`status` is `success` only for exit code 0. `warning` becomes true when error-level messages were logged during an otherwise successful MQTT-enabled run. Dataset failures can combine diagnostics from multiple datasets; the report includes up to the last 4096 characters of stderr, or stdout if stderr is empty.

## Home Assistant example

`home-assistant/CleanUpInSyncoidSnapshots-mqtt-persistent-notification.yaml` is a receive-only Home Assistant automation blueprint. Configure its MQTT topic to exactly match `[mqtt].topic` in your TOML file.

The blueprint can independently show clean success, success-with-warning, failure, and dry-run notifications, and can either replace the previous notification or create separate notifications. It does not publish commands, start cleanup, or invoke ZFS.

## Project files

- `CleanUpInSyncoidSnapshots.py` - application entry point and original cleanup/email/log lifecycle.
- `config_loader.py` - TOML loading, validation, path resolution, and conversion into the existing runtime values.
- `config-example.toml` - complete commented configuration example containing every supported setting.
- `mqtt_notifications.py` - optional MQTT validation, report construction, bounded publishing, and internal worker.
- `requirements.txt` - Python 3.10 TOML compatibility dependency.
- `requirements-mqtt.txt` - optional MQTT dependency plus base requirements.
- `datasets-example`, `hostnames-example` - input-file examples.
- `home-assistant/` - receive-only Home Assistant MQTT notification blueprint.
- `tests/test_project.py` - regression tests with ZFS/mail mocked and optional loopback MQTT integration tests.
- `commented_code_map.md` - current function and command map.
- `VERSIONING.md` - release-by-release change record.
- `VERIFICATION.md` - verification evidence and limits for this release.
- `DISCLAIMER.md` - safety/liability notice.
- `.gitignore` - excludes local runtime configs, generated logs, Python caches, virtual environments, and build outputs while keeping the shipped example tracked.

## Safety notes

This application can destroy ZFS snapshots. Review the included [DISCLAIMER.md](DISCLAIMER.md), keep independent backups, use `dry-run` before `delete`, and verify the configured dataset, hostname, retention, and path values before running against important data.
