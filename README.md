# CleanUpInSyncoidSnapshots

Version **0.0.16** removes matching Syncoid ZFS snapshots using age/count retention, previews deletions with `dry-run`, rotates its own log groups, and optionally reports to email, MQTT completion notifications, and Home Assistant live sensors.

The MQTT implementation uses the supplied **syncerate-mqtt-template 1.1.0** modules unchanged. Completion notifications and HA live preview have separate configuration and delivery paths.

## Source layout

Keep the `modules/` directory beside `CleanUpInSyncoidSnapshots.py` when running from source:

```text
CleanUpInSyncoidSnapshots.py
modules/
  __init__.py
  config_loader.py
  mqtt_notifications.py
  mqtt_status.py
  ha_live_preview.py
```

All supporting application Python modules live in this package. The main entry script stays at the project root; configuration, input files, HA examples and build files keep their existing locations. Paho and other third-party dependencies are installed through the requirements files. The one-file executable bundles the modules internally and needs no external `modules/` directory.

## Quick start

Linux, ZFS and root privileges are required for cleanup. Source runs require Python 3.10+. The frozen executable bundles Python and the Python dependencies; `zfs` and optional `mail`/`mailx` remain host tools.

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-mqtt.txt
cp config-example.json config.json
chmod 600 config.json
# Edit config.json, datasets-example and hostnames-example for this machine.
sudo .venv/bin/python CleanUpInSyncoidSnapshots.py -c config.json
```

The example uses `cleanup.command="dry-run"` and disables email and both MQTT channels. A dry-run lists snapshots and reports what would be deleted; it does not destroy snapshots or prune old log files. After reviewing the result, set `cleanup.command="delete"` to apply the same selection policy.

Use the supplied Linux x86_64 executable with:

```bash
chmod +x dist/CleanUpInSyncoidSnapshots
sudo dist/CleanUpInSyncoidSnapshots -c /absolute/path/to/config.json
```

`--help` and `--version` do not load config or run cleanup. The only operational CLI setting is `-c/--config`.

## Configuration

`config-example.json` is the recommended complete JSON example. `config-example.toml` has equivalent settings. The `.json` extension selects JSON parsing; other extensions select TOML. Python 3.10 TOML parsing needs the `tomli` dependency in `requirements.txt`; JSON parsing needs only the standard library.

Both formats use the template's **`completion`** and **`live`** objects with the same names, types and defaults as `combined-config.example.json`. Add the application's `cleanup` settings and optional `logging`, `report`, and `mail` objects alongside them. The template's combined broker config alone does not specify a cleanup job.

All filesystem paths, including datasets, hostnames and TLS files, resolve relative to the application config file. JSON supports `null` for optional password/certificate values; TOML uses empty strings. Unknown sections/options and invalid values are rejected before cleanup starts.

### Cleanup and existing features

| Object | Setting | Meaning/default |
| --- | --- | --- |
| `cleanup` | `command` | Required: `dry-run` or `delete`. |
| `cleanup` | `datasets_file` | Required: one exact local ZFS dataset per nonempty line. |
| `cleanup` | `syncoid_hosts_file` | Required: Syncoid hostnames, one per line; blank lines and whole-line `#` comments ignored. |
| `cleanup` | `older_than` | Optional `7d`, `2w`, `3m`; months mean 30 days. Empty disables age cutoff. |
| `cleanup` | `retain_count` | Newest snapshots protected per dataset/hostname; also newest log groups protected. Default 0; negative values become 0. |
| `cleanup` | `continue_on_missing_dataset` | Default true. Record missing dataset failures and try later datasets. |
| `cleanup` | `continue_on_other_failures` | Default true. Record other checked ZFS list/destroy failures and try later datasets. |
| `logging` | `prefix` | Log filename prefix and report job ID; default application basename. |
| `report` | `title`, `comment` | Human-readable notification title and comment. |
| `mail` | `enabled`, `recipient`, `on_success` | Email enabled=false, success notifications=false; recipient required when enabled. |

A dataset failure always makes the overall run fail, including when continuation is enabled. Disabled continuation stops at the first failure of that kind. Global input, permission and configuration failures are fatal.

Snapshot names must match the configured Syncoid hostname and supported timestamp format. Hostnames are regex-escaped. Selection protects the newest `retain_count` snapshots for each hostname in each dataset, then applies the age cutoff if configured. Without an age cutoff, it selects everything outside that protected set. With both age and count disabled, every matching snapshot is eligible. Destruction remains one exact snapshot at a time without recursive ZFS destruction.

Logs always live in `logs/` beside the source script or real executable. Log retention uses the same age/count policy on timestamp groups; it runs after successful real cleanup. Empty error logs are removed. A dry-run includes dataset/snapshot and prospective log-retention counts in its final report. Email errors are nonfatal and set the report's warning flag.

### Independent channel switches

| `completion.enabled` | `live.enabled` | Behavior |
| --- | --- | --- |
| false | false | Local cleanup/logging and independently configured email. |
| true | false | Final success/failure JSON notifications. |
| false | true | HA live progress/discovery without completion notifications. |
| true | true | Both channels, sharing one run ID. |

HA live preview observes actual execution. It is separate from the cleanup `dry-run` command.

### Completion notifications

`completion` accepts every `MQTTConfig` setting in the supplied template:

| Setting | Default | Purpose |
| --- | --- | --- |
| `enabled` | false | Enable completion publishing only. |
| `host` | empty | Broker hostname/IP; required when enabled, without a URL scheme. |
| `port` | 1883 | Broker port; explicitly choose 8883 if required for TLS. |
| `topic` | `homeassistant/jobs/status` | Exact completion topic, without MQTT wildcards. |
| `username`, `password` | null | Optional broker authentication. Password requires username. |
| `client_id` | empty | Optional client identity. |
| `qos` | 0 | 0, 1 or 2. |
| `timeout` | 15 | Parent-enforced delivery deadline, seconds. |
| `on_success` | true | False suppresses successful completion notifications; failures remain eligible. |
| `send_on_dry_run` | true | False suppresses both successful and failed dry-run completion reports. |
| `tls` | false | Enable certificate and hostname verification. |
| `ca_certs`, `certfile`, `keyfile` | null | Optional TLS files. Client cert/key must be paired and require TLS. |

The example uses a project-specific topic. Set the HA blueprint's input to exactly the same topic. Completion events always use **retain=false**. They are published once per eligible invocation without automatic retry. Delivery failure is logged and does not change cleanup's exit result.

### Home Assistant live preview

`live` accepts every `LiveConfig` setting in the supplied template. Its broker, authentication, TLS, client ID, QoS and timeout are configured independently of completion. Defaults differ: QoS 1 and timeout 5 seconds.

| Live setting | Default | Meaning |
| --- | --- | --- |
| `enabled` | false | Enable live progress only. |
| `device_id` | Automatically derived when omitted | Stable host/job/config identity. The example explicitly uses `cleanup_syncoid_snapshots`. Use a unique ID for each host/job. |
| `topic_prefix` | `job-live` | Prefix for state and last-result topics. |
| `discovery` | true | Publish retained HA sensor discovery. |
| `discovery_prefix` | `homeassistant` | HA discovery prefix. |
| `send_on_dry_run` | false | Explicitly allow live publishing for an actual cleanup dry-run. |
| `heartbeat_seconds` | 10 | Heartbeat interval. |
| `min_publish_interval` | 1 | Minimum interval between ordinary progress batches. Must not exceed heartbeat. |
| `expire_after` | 45 | Sensor expiry; must exceed two heartbeats plus timeout. |
| `discovery_interval` | 300 | Discovery refresh interval. |
| `final_wait` | 1 | Bounded final publication drain, seconds. |

With the example ID, topics are:

```text
job-live/cleanup_syncoid_snapshots/state
job-live/cleanup_syncoid_snapshots/last_result
homeassistant/sensor/job_live_cleanup_syncoid_snapshots_<field>/config
```

State/heartbeat messages are non-retained. Discovery and the final real-run result are retained. Dry-run results never overwrite the retained real-run result, even when live dry-run publishing is enabled. Finished live state eventually expires to unavailable; the separate last-result sensor retains the last real result.

The module discovers 14 sensors for status, progress, completed/total, current item, phase, runtime, heartbeat, last result, dataset outcome counts and optional transfer measurements. Snapshot cleanup does not measure transfers, so bytes/speed stay JSON null.

Progress counts **datasets whose processing returned or raised a checked ZFS failure**. A failed attempt counts as processed, while an interrupted attempt and unattempted datasets do not. Consequently 100% can accompany failure. Successful, failed and skipped dataset lists/counts are separate. Current item shows the dataset or exact snapshot being processed. ZFS stderr is captured after each subprocess finishes; heartbeats continue while it is running.

Live states are `running`, `success`, `failure`, `interrupted` or `incomplete`. Running outcome/code stay null; finish never forces counters to 100%. The application preserves its existing failure semantics. A stop caused by a dataset failure lists remaining datasets as unattempted/skipped.

Live network work runs in a background daemon with bounded subprocess workers. Its delivery failures never disable completion reporting or change the cleanup result. A per-device advisory lock in this installation's log directory is acquired before publishing live state; a conflicting launch exits without changing that device's state or running cleanup. Different installations/directories do not share this lock. Assign separate identities if jobs can overlap across installations, and separate identities for overlapping dry-runs.

## JSON completion contract

Reports now contain all template fields:

```json
{
  "status": "success",
  "success": true,
  "title": "Syncoid snapshot cleanup",
  "name": "CleanUpInSyncoidSnapshots",
  "job": "CleanUpInSyncoidSnapshots",
  "dry_run": false,
  "exit_code": 0,
  "error": "",
  "stderr": "",
  "warning": false,
  "schema_version": 1,
  "command": "delete",
  "comment": "",
  "version": "0.0.16",
  "timestamp": "2026-10-27T08:00:00+00:00",
  "host": "nas",
  "run_id": "example-run-id",
  "planned_datasets": [{"source": "tank/data"}],
  "failed_datasets": [],
  "skipped_datasets": []
}
```

Code 0 means completion success; all other integer codes mean failure. `status`, boolean `success`, and integer `exit_code` agree. Warnings do not replace the job outcome. Stderr keeps the last 4,000 characters. The old `dry_run_report` object remains as an additional field on dry-run reports. Failure entries include dataset source, reason, failure kind, original ZFS code and bounded stderr.

See `payload-examples.json` for success, failure and dry-run samples. Live payloads deliberately use the template's separate live schema; do not use them as completion notification triggers.

## Home Assistant setup

1. Connect HA's MQTT integration to your broker.
2. For final notifications, import `home-assistant/CleanUpInSyncoidSnapshots-mqtt-persistent-notification.yaml` as an automation blueprint. Set its exact completion topic and choose success/warning/failure/dry-run notification preferences. It checks schema and agreement between status/success/code before creating a persistent notification.
3. For live sensors, independently enable `live.enabled` and discovery. Paste `home-assistant/CleanUpInSyncoidSnapshots-live-dashboard.yaml` as a manual dashboard card. Its IDs match the example config; replace them when choosing another device ID or when HA assigns different entity IDs.

Changing or disabling a live device does not delete retained discovery entries for the old identity. Remove those deliberately when retiring it. MQTT publication success confirms transport completion, not HA processing.

## Existing TOML migration

Existing `[mqtt]` configs still work and now produce the new completion JSON. They preserve their omitted defaults, `qos=1` and `on_success=false`; `send_on_dry_run` defaults to true. `config-legacy-example.toml` documents that form.

For the template's config structure, rename `[mqtt]` to `[completion]` and explicitly preserve your preferred values. New `completion` configs use template defaults `qos=0`, `on_success=true`. Do not configure both names in one file. `[live]` can be added independently to either form, with a separate `enabled` switch. Email remains independently configured with `mail.on_success=false` by default.

The updated HA blueprint expects the new schema; upgrade the script and blueprint together.

## Build and verification

```bash
./build-pyinstaller.sh
python3 -B -m unittest discover -s tests -v
```

The existing build helper creates a clean venv, installs `requirements-build.txt`, clears old build/dist outputs and builds through the existing PyInstaller spec. The spec bundles both reporting modules and Paho/Tomli. A successful `dist/` contains exactly one executable and passes `--version`/`--help` checks. Both private worker flags are dispatched before normal argument parsing or cleanup, keeping credentials on stdin.

The included executable is Linux x86_64 and was built with Python 3.14.4 on glibc 2.43. Frozen binaries depend on the build platform and its glibc baseline; rebuild on your target or a compatible older Linux build system if necessary.

`VERIFICATION.md` records the performed checks and limitations. Tests mock ZFS and mail, test policies and progress, and exercise MQTT against a local fake broker. No production ZFS dataset, broker or HA instance is needed for tests. `VERSIONING.md` contains release history and `commented_code_map.md` maps the current source.
