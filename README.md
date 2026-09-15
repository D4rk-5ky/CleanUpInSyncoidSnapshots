# CleanUpInSyncoidSnapshots

Delete matching syncoid ZFS snapshots, preview deletions, manage log retention,
and optionally send email and MQTT result notifications.

## Requirements and installation

- Linux with ZFS and Python **3.10 or newer**.
- Run both `delete` and `dry-run` as root. Help and version commands need no root access.
- `zfs` must be on the executable search path.
- Email requires a configured `mail` command supporting `-s` and `--attach`.
- MQTT requires the optional Paho dependency in the Python interpreter used to run the script.

Keep the Python files together. The script can run without Paho when MQTT is disabled.
For MQTT, create a virtual environment in the extracted project directory:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-mqtt.txt
cp mqtt-config-example.json mqtt-config.json
chmod 600 mqtt-config.json
```

`venv` creates an isolated Python environment; `pip install` installs the optional
MQTT library; `cp` makes your local settings file; `chmod 600` limits its access
because it may contain a password. Edit the broker address, topic, and credentials
in `mqtt-config.json` before use. Use `sudo .venv/bin/python` for MQTT-enabled runs.
Without MQTT, use `sudo python3` instead.

## Dataset and hostname files

Create `datasets.txt` with one exact local ZFS dataset name per line:

```text
tank/data
tank/backups
```

Blank dataset lines are ignored; comments are **not** supported in this file.
List each dataset to process explicitly; the script does not request recursive listing.
The original `datasets-example` is preserved for reference; replace its machine-specific
names with valid datasets on your own system, including replacing its space-containing sample.

Create `hostnames.txt` with the hostnames recorded in your syncoid snapshot names:

```text
# Hostnames are matched exactly, including case.
backup-server
laptop01
```

Blank lines and whole-line `#` comments are ignored in the hostname file. Inline
comments are not supported. The original `hostnames-example` is also included.
An empty hostname list skips snapshot pruning; successful runs can still prune logs.

## Commands

Show all arguments or the current version:

```bash
python3 CleanUpInSyncoidSnapshots.py --help
python3 CleanUpInSyncoidSnapshots.py --version
```

Preview using a seven-day cutoff while keeping at least ten snapshots per host:

```bash
sudo python3 CleanUpInSyncoidSnapshots.py \
  --command dry-run \
  --datasets-file datasets.txt \
  --syncoid-hosts-file hostnames.txt \
  --older-than 7d --retain-count 10
```

`dry-run` lists candidates without destroying snapshots or pruning existing log
groups. It still creates logs, removes its empty error log, and can send email.
MQTT reports from dry-runs are disabled by default.

After reviewing the preview, run deletion with MQTT notifications:

```bash
sudo .venv/bin/python CleanUpInSyncoidSnapshots.py \
  --command delete \
  --datasets-file datasets.txt \
  --syncoid-hosts-file hostnames.txt \
  --older-than 7d --retain-count 10 \
  --mqtt-config mqtt-config.json \
  --backup-title "Zotac RI531 - Syncoid cleanup" \
  --backup-comment "Cleanup after daily replication"
```

To use count-only retention, omit `--older-than` and keep a positive
`--retain-count`. To use age-only retention, omit `--retain-count` and specify
`--older-than`. MQTT is independent of email; omit `--mqtt-config` to disable it.

This complete option example previews cleanup and enables email on success and failure:

```bash
sudo .venv/bin/python CleanUpInSyncoidSnapshots.py \
  -c dry-run -d datasets.txt -s hostnames.txt \
  -o 7d -r 10 -l Zotac-Cleanup \
  -m you@example.com -mos \
  -bt "Zotac RI531 - Syncoid cleanup" \
  -bc "Cleanup after daily replication" \
  --mqtt-config mqtt-config.json
```

`--help` and `--version` exit immediately instead of running cleanup.

### All CLI options

| Option | Short form | Behavior/default |
| --- | --- | --- |
| `--help` | `-h` | Print argument help and exit. |
| `--version` | None | Print application version and exit. |
| `--command {delete,dry-run}` | `-c` | Required. Delete matching candidates or preview them. |
| `--datasets-file FILE` | `-d` | Required. Dataset list described above. |
| `--syncoid-hosts-file FILE` | `-s` | Required. Exact syncoid hostname list. |
| `--older-than Nd/Nw/Nm` | `-o` | Optional age limit: days, weeks, or 30-day months. |
| `--retain-count N` | `-r` | Keep newest N per hostname/dataset and N log timestamp groups; default 0. Negative values are treated as 0. |
| `--log-prefix TEXT` | `-l` | Log filename prefix; default script basename. Use a plain filename prefix without path separators or wildcard characters. |
| `--send-mail EMAIL` | `-m` | Enable email on failure; disabled by default. |
| `--mail-on-success` | `-mos` | Also email on successful runs; needs `--send-mail`. |
| `--backup-title TEXT` | `-bt` | Email heading and MQTT `title`; defaults to empty, with app-name fallback for MQTT. |
| `--backup-comment TEXT` | `-bc` | Email comment and MQTT `comment`; default empty. |
| `--mqtt-config FILE` | None | Enable final MQTT reports using a JSON settings file; disabled by default. |

## Retention behavior

Snapshot names must match `syncoid_<hostname>_YYYY-MM-DD:HH:MM:SS-GMT[+/-]HH:MM`.
An omitted positive offset sign is accepted. Other names are ignored; malformed
timestamps are logged and skipped. Sorting and age comparisons use the timestamp
in the name, converted to UTC, rather than ZFS's creation property.

The newest `--retain-count` snapshots are protected separately for each hostname
within each dataset. If an age limit is supplied, only unprotected snapshots
strictly older than the cutoff are candidates. Without an age limit, all
unprotected matching snapshots are candidates.

**With no age limit and a retain count of zero, `delete` deletes every matching
snapshot.** Always choose retention values deliberately and review `dry-run` output.
For snapshots, `0d`, `0w`, and `0m` currently behave like an omitted cutoff;
for logs, zero age uses the current time as the cutoff. Prefer a positive age.
These are existing application behaviors.

Logs are grouped by filename timestamp (`.log` and `.err` together). Retention
uses local time, keeps the newest N timestamp groups, and applies the same optional
age constraint. With no age and zero count, log pruning does nothing. A zero-age
log cutoff can include the current run's logs when no group is retained.
ZFS command failures stop subsequent dataset processing; earlier deletions are not undone.

## MQTT configuration

Use `mqtt-config-example.json` as the full configuration reference. This file
configures MQTT only; dataset selection, retention, and email remain CLI options.
JSON booleans must be `true`/`false`, and absent optional values can be `null`.
Unknown configuration keys are rejected before cleanup starts.

| JSON key | Default | Meaning |
| --- | --- | --- |
| `host` | Required | MQTT broker hostname or IP, without a URL scheme. |
| `topic` | Required | Exact publish topic; cannot contain subscription wildcards `+` or `#`. |
| `port` | `1883` | Broker TCP port, 1–65535. Set explicitly to `8883` if your TLS listener uses that port. |
| `username` | `null` | Optional broker username. |
| `password` | `null` | Optional password; requires a nonempty username. |
| `client_id` | `""` | Empty lets the client/broker assign an ID. Otherwise choose a unique ID for concurrent jobs. |
| `qos` | `1` | MQTT delivery level: 0, 1, or 2. QoS 1 waits for broker acknowledgement; duplicate delivery is possible. |
| `timeout` | `15` | Positive seconds allowed for the publishing worker, including connection and acknowledgements. |
| `tls` | `false` | Use TLS with certificate and hostname verification. |
| `ca_certs` | `null` | CA file for TLS; null uses system trust roots. |
| `certfile` | `null` | Optional client certificate file for mutual TLS; requires `keyfile`. |
| `keyfile` | `null` | Client private key file; requires `certfile`. Encrypted-key passwords are not supported. |
| `publish_dry_run` | `false` | Explicitly allow reports from previews. Use a separate test topic when enabling this. |

Certificate paths are relative to the JSON file, or absolute. Certificate options
require `tls: true`. TLS does not change the port automatically. Publish transport
is MQTT 3.1.1 over TCP (with optional TLS). Messages always use `retain: false`,
so an old completion message is not deliberately stored for future subscribers.
Existing retained messages from other publishers are not cleared.

MQTT uses [Eclipse Paho's single-message publisher](https://eclipse.dev/paho/files/paho.mqtt.python/html/helpers.html).
Credentials are passed to its worker through standard input, not command-line arguments.
Use TLS when credentials or error details need protection in transit.

### Report format

Example successful report:

```json
{
  "status": "success",
  "title": "Zotac RI531 - Syncoid cleanup",
  "name": "CleanUpInSyncoidSnapshots",
  "job": "CleanUpInSyncoidSnapshots",
  "exit_code": 0,
  "warning": false,
  "error": "",
  "stderr": "",
  "command": "delete",
  "dry_run": false,
  "comment": "Cleanup after daily replication",
  "version": "0.0.1",
  "timestamp": "2026-09-15T12:00:00+00:00"
}
```

| Field | Meaning |
| --- | --- |
| `status` | Exactly `success` or `failure`, matching the supplied automation. |
| `title` | `--backup-title`, or `CleanUpInSyncoidSnapshots` if blank. |
| `name` | Application name, for the automation's title fallback. |
| `job` | Log prefix, also usable as an automation title fallback. |
| `exit_code` | Application exit code: 0 on completion, 1 on ordinary fatal errors or root rejection, 130 on a caught keyboard interrupt. |
| `warning` | JSON boolean: true when the run logged errors, including nonfatal mail/log-pruning errors or skipped bad timestamps. |
| `error` | Fatal error description, or empty string on success. A failed ZFS command's own return code appears here. |
| `stderr` | Last 4096 characters of a failed command's stderr, falling back to stdout; empty when unavailable. |
| `command`, `dry_run` | Requested command and a JSON boolean identifying previews. |
| `comment` | `--backup-comment`. |
| `version` | Current application version. |
| `timestamp` | Report creation time in UTC, including the timezone offset. |

With MQTT enabled, one final report is attempted after cleanup, email, and log
finalization, including caught failures and root rejection. Success means the
run completed; it can also mean no snapshots matched. Nonfatal errors can produce
`success` with `warning: true`, as understood by your automation.

MQTT delivery failure is reported to the error logger/console and does not change
the cleanup exit code. If current log files were removed during finalization,
that diagnostic may only remain on the console; capture stderr in your scheduler.
The script does not send a second status after delivery failure, queue reports
for later runs, or retry after its timeout. Broker acknowledgement is not proof
that a Home Assistant action completed.

CLI parsing/configuration failures happen before cleanup and do not send MQTT.
Startup/import errors, power loss, forced termination, and an unavailable broker
can also prevent notification. Missing Paho is reported as a delivery failure.
For testing MQTT, set `publish_dry_run: true` with a dedicated test topic, then
run the existing dry-run command with `--mqtt-config`.

## Home Assistant blueprint example

The release includes:

```text
home-assistant/CleanUpInSyncoidSnapshots-mqtt-persistent-notification.yaml
```

It is an **automation blueprint** that subscribes to this application's final MQTT
JSON report and creates a Home Assistant persistent notification. It does not run
cleanup, publish MQTT commands, or control any ZFS/backup operation.

Copy the file below Home Assistant's blueprint directory, for example:

```text
/config/blueprints/automation/CleanUpInSyncoidSnapshots/CleanUpInSyncoidSnapshots-mqtt-persistent-notification.yaml
```

Then reload automations or restart Home Assistant, open
**Settings → Automations & scenes → Blueprints**, and create an automation from
**CleanUpInSyncoidSnapshots - MQTT persistent notification**.

Set **MQTT status topic** to the exact `topic` in this application's
`mqtt-config.json`. The packaged default matches the example config:

```text
homeassistant/CleanUpInSyncoidSnapshots/Zotac-RI531/status
```

The blueprint validates that the received JSON identifies
`CleanUpInSyncoidSnapshots` and has `status` equal to `success` or `failure`. It
then distinguishes these outcomes:

- clean success → green-check success title;
- success with `warning: true` → warning title and a reminder to inspect logs;
- failure → failure title plus `error` and `stderr` when supplied;
- dry-run → identified as a preview, when dry-run MQTT publishing is enabled.

Blueprint inputs let you independently suppress clean-success, warning, failure,
or dry-run notifications. By default it reuses one Home Assistant
`notification_id`, so the newest report replaces the previous persistent
notification. Disable **Replace previous notification** if every report should
remain separately dismissible. If several hosts/jobs use the blueprint with
replacement enabled, assign each automation a different notification ID.

Persistent notifications are Home Assistant frontend notifications; they are not
mobile push notifications. The blueprint uses only the MQTT integration and the
`persistent_notification.create` action.

### Reusing an existing combined backup automation

If you prefer to keep cleanup reporting inside an existing Syncerate/backup
automation instead of using the blueprint, subscribe that automation to the
cleanup topic separately from the backup status topics. For example:

```yaml
- trigger: mqtt
  id: cleanup_status
  topic: homeassistant/CleanUpInSyncoidSnapshots/Zotac-RI531/status
```

The report fields in the previous section are deliberately compatible with a
success/failure parser. Do not substitute a backup-control topic for this cleanup
status topic. A status trigger only reports completion; it does not make fixed
delays in another automation wait for cleanup. Change that sequencing separately
if shutdown or another job must wait for cleanup completion.

## Email and logs

`--send-mail` emails failures; add `--mail-on-success` for both outcomes.
`--backup-title` and `--backup-comment` appear in the body, without replacing
the subject. Subjects are `Syncoid cleanup SUCCESS - logs attached`,
`Syncoid cleanup FAILED - logs attached`, or the special root-rejection subject.
The newest `.log` and nonempty `.err` for the prefix are attached and included
in the body. Concurrent runs sharing a prefix may therefore select another run's logs.
Email is sent before log pruning, so its result does not include later pruning
or MQTT delivery errors.

Logs use `<prefix>-Date-YYYY-MM-DD_HH_MM_SS.log` and `.err`.
The script prefers its own `logs` directory and falls back to the system temporary
directory under the script basename when needed. Console output shows INFO/errors;
the main log also records DEBUG command output. Empty error logs are removed.
Root rejection still creates logs and attempts requested notifications.

## Verification command

```bash
.venv/bin/python -B -m unittest discover -s tests -v
```

This runs safe tests with ZFS and email mocked. With Paho installed, loopback
broker tests exercise actual MQTT packets, rejection, and timeout. Those tests
are skipped if Paho is unavailable. `-B` prevents Python bytecode cache creation.
No test targets a real dataset or sends email.

See [DISCLAIMER.md](DISCLAIMER.md) for the original project notices.
