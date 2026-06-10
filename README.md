# SnapBeforeWatchTower

## ⚠️ Disclaimer / Liability Notice

This script is provided **“as is”**, without warranty of any kind.
By using this script, you agree that **I am not liable** for any data loss, system damage, service interruption, or other issues that may occur as a result of running it.

This script performs **destructive operations**, including but not limited to:

- Destroying ZFS snapshots (`zfs destroy`)
- Deleting log files (`*.log` / `*.err`)
- Executing system-level commands (`zfs`, `mail`)

⚠️ **Always test on a non-production system first.**  
⚠️ **Always ensure you have verified backups.**  
⚠️ **You are fully responsible for reviewing and understanding the code before running it.**

---

## Overview

**SnapBeforeWatchTower** is a Python 3 utility designed to:

- Delete **syncoid-created ZFS snapshots** for one or more datasets
- Support both:
  - **Dry-run mode** (prints what would be deleted)
  - **Delete mode** (actually deletes)
- Enforce retention using:
  - Time-based retention (`--older-than`) *(optional)*
  - Count-based retention (`--retain-count`) *(optional)*
- Clean up old `.log` / `.err` files using the same retention logic
- Generate structured logs and error reports
- Optionally send email notifications with logs attached
- Optionally add a custom **Title** and **Comment** at the top of notification emails

❗ **The script must be run as root.**

---

## Key Requirements (Not Optional)

❗ A **datasets file** is required (`--datasets-file`)  
❗ A **syncoid hostnames file** is required (`--syncoid-hosts-file`)

The script will always attempt to:

- Read ZFS dataset names from a file passed via `--datasets-file`
- Read syncoid hostnames from a file passed via `--syncoid-hosts-file`

If either requirement is missing or misconfigured, **the script will fail**.

---

## Features

- ✅ Syncoid snapshot pruning (matches `syncoid_<hostname>_<timestamp>`)
- ✅ Supports both retain-only and retain + cutoff logic
- ✅ Dry-run output to verify deletions safely
- ✅ Log rotation / cleanup using the same retention rules
- ✅ Separate `.log` (debug/info) and `.err` (errors) files
- ✅ Optional email notifications (`--send-mail`) with newest logs attached
- ✅ Optional success emails (`--mail-on-success`)
- ✅ Optional email body title/comment (`--backup-title` / `--backup-comment`)
- ✅ Root-only execution enforcement with safe fallback logging location

---

## System Requirements

### Operating System

- Linux with **ZFS**

### Python

- Python **3.9+** recommended

### Required Commands (Mandatory)

The following commands must be available in `$PATH`:

- `zfs`
- `mail` *(only required if `--send-mail` is used)*

---

## Files

### Datasets File (Mandatory)

The dataset file must exist and contain **one ZFS dataset per line**.

Example `datasets.txt`:

```text
tank/data
tank/docker
tank/vms
```

Rules:

- Blank lines are ignored

---

### Syncoid Hosts File (Mandatory)

This file contains hostnames that should match syncoid snapshots.

Example `syncoid_hosts.txt`:

```text
darkyere-VirtualBox
backup-server
laptop01
```

Rules:

- Blank lines are ignored
- Lines starting with `#` are ignored (comments)

---

## Usage

### Dry-run (recommended first)

```bash
sudo ./SnapBeforeWatchTower.py \
  --command dry-run \
  --datasets-file datasets.txt \
  --syncoid-hosts-file syncoid_hosts.txt \
  --older-than 7d \
  --retain-count 10
```

---

### Delete snapshots

```bash
sudo ./SnapBeforeWatchTower.py \
  --command delete \
  --datasets-file datasets.txt \
  --syncoid-hosts-file syncoid_hosts.txt \
  --older-than 7d \
  --retain-count 10
```

---

### Retain-only mode (no time cutoff)

```bash
sudo ./SnapBeforeWatchTower.py \
  --command delete \
  --datasets-file datasets.txt \
  --syncoid-hosts-file syncoid_hosts.txt \
  --retain-count 10
```

---

### Send email on error

```bash
sudo ./SnapBeforeWatchTower.py \
  --command delete \
  --datasets-file datasets.txt \
  --syncoid-hosts-file syncoid_hosts.txt \
  --older-than 7d \
  --retain-count 10 \
  --send-mail you@example.com
```

By default, `--send-mail` sends mail when the script fails.

---

### Send email on success and error

```bash
sudo ./SnapBeforeWatchTower.py \
  --command delete \
  --datasets-file datasets.txt \
  --syncoid-hosts-file syncoid_hosts.txt \
  --older-than 7d \
  --retain-count 10 \
  --send-mail you@example.com \
  --mail-on-success
```

`--mail-on-success` makes the script send a success email when the run completes successfully.

---

### Send email with optional title and comment

```bash
sudo ./SnapBeforeWatchTower.py \
  --command delete \
  --datasets-file datasets.txt \
  --syncoid-hosts-file syncoid_hosts.txt \
  --older-than 7d \
  --retain-count 10 \
  --send-mail you@example.com \
  --mail-on-success \
  --backup-title "NAS weekly cleanup" \
  --backup-comment "Prune old syncoid snapshots after backup"
```

Short options can also be used:

```bash
sudo ./SnapBeforeWatchTower.py \
  -c delete \
  -d datasets.txt \
  -s syncoid_hosts.txt \
  -o 7d \
  -r 10 \
  -m you@example.com \
  -mos \
  -bt "NAS weekly cleanup" \
  -bc "Prune old syncoid snapshots after backup"
```

---

## Email Notifications

Email notification is optional and enabled with:

```bash
--send-mail you@example.com
```

or:

```bash
-m you@example.com
```

### Email subject

The email subject is still controlled by the script result.

Success email subject:

```text
Syncoid cleanup SUCCESS - logs attached
```

Failed email subject:

```text
Syncoid cleanup FAILED - logs attached
```

The optional backup title/comment **does not replace or change the email subject**.

---

### Optional backup title and comment

You can add a custom title and comment to the top of the email body:

```bash
--backup-title "NAS weekly cleanup"
--backup-comment "Prune old syncoid snapshots after backup"
```

or with short options:

```bash
-bt "NAS weekly cleanup"
-bc "Prune old syncoid snapshots after backup"
```

These options are optional.

You can use:

- Neither option
- Only `--backup-title`
- Only `--backup-comment`
- Both `--backup-title` and `--backup-comment`

Example email body start:

```text
Title: NAS weekly cleanup
Comment:
Prune old syncoid snapshots after backup

Cleanup completed successfully. Logs attached.
```

If neither `--backup-title` nor `--backup-comment` is used, this extra block is not added to the email body.

---

## Command Line Options

| Option | Short | Required | Description |
|---|---:|---:|---|
| `--command` | `-c` | ✅ | `delete` or `dry-run` |
| `--datasets-file` | `-d` | ✅ | File containing ZFS datasets, one per line |
| `--syncoid-hosts-file` | `-s` | ✅ | File containing syncoid hostnames, one per line |
| `--older-than` | `-o` | ❌ | Delete snapshots/logs older than `Nd`, `Nw`, or `Nm` |
| `--retain-count` | `-r` | ❌ | Always keep newest `N` snapshots/log groups |
| `--log-prefix` | `-l` | ❌ | Custom prefix for log filenames |
| `--send-mail` | `-m` | ❌ | Send email notification to an address |
| `--mail-on-success` | `-mos` | ❌ | Also send mail when the run succeeds |
| `--backup-title` | `-bt` | ❌ | Optional title written at the top of notification emails |
| `--backup-comment` | `-bc` | ❌ | Optional comment written at the top of notification emails |

---

## Retention Logic (Important)

Retention is applied **per hostname**, inside **each dataset**.

### `--retain-count N`

- Always keeps the **newest N** matching snapshots per host

### `--older-than Nd | Nw | Nm`

- Deletes snapshots older than the cutoff **unless retained**

### Special Cases

- If `--older-than` is **not provided** → *Retain-only mode*
- If `--older-than` is **not provided** and `--retain-count` is `0` → **No deletions occur**

---

## Logging

Log files are created as:

```text
<prefix>-Date-YYYY-MM-DD_HH_MM_SS.log
<prefix>-Date-YYYY-MM-DD_HH_MM_SS.err
```

### Log folder selection

- `<script_dir>/logs`
- `/tmp/<script_name>/` *(fallback)*

Old logs are cleaned up using the **same retention rules as snapshots**.

---

## Safety Notes

❗ This script **destroys ZFS snapshots**  
❗ **Must be run as root**  
❗ Designed for automation (**cron / systemd**)  
❗ **Always run dry-run first**

---

## License

No license is implied unless explicitly added.

Use, modify, and run this script **entirely at your own risk**.