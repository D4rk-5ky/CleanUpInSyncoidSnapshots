#!/usr/bin/python3
import os
import re
import datetime
import logging
import subprocess
import argparse
import glob
import sys
from typing import List, Tuple, Optional
from config_loader import load_config, parse_older_than
from mqtt_notifications import build_mqtt_report, notify_mqtt, should_send_notification


__version__ = "0.0.12"


class ReportWarningHandler(logging.Handler):
    """Remember logged errors even if retention later removes their log file."""

    def __init__(self, state):
        super().__init__(logging.ERROR)
        self.state = state

    def emit(self, record):
        self.state["warning"] = True


def setup_logger(log_folder: str, log_date: str, prefix: str) -> Tuple[logging.Logger, logging.Logger, str]:
    """
    Creates two loggers:
      - main logger: INFO to console, DEBUG to .log
      - error logger: ERROR to console and ERROR to .err

    Returns: (logger, error_logger, err_filepath)
    """
    os.makedirs(log_folder, exist_ok=True)

    log_filepath = os.path.join(log_folder, f"{prefix}-Date-{log_date}.log")
    err_filepath = os.path.join(log_folder, f"{prefix}-Date-{log_date}.err")

    fmt = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')

    def _build_logger(name: str, level: int, handlers: List[logging.Handler]) -> logging.Logger:
        lg = logging.getLogger(name)
        lg.setLevel(level)
        lg.propagate = False
        if lg.handlers:
            lg.handlers.clear()
        for h in handlers:
            h.setFormatter(fmt)
            lg.addHandler(h)
        return lg

    file_h = logging.FileHandler(log_filepath)
    file_h.setLevel(logging.DEBUG)

    console_h = logging.StreamHandler()
    console_h.setLevel(logging.INFO)

    logger = _build_logger(
        name=f"{prefix}",
        level=logging.DEBUG,
        handlers=[file_h, console_h],
    )

    err_file_h = logging.FileHandler(err_filepath)
    err_file_h.setLevel(logging.ERROR)

    err_console_h = logging.StreamHandler()
    err_console_h.setLevel(logging.ERROR)

    error_logger = _build_logger(
        name=f"{prefix}Error",
        level=logging.ERROR,
        handlers=[err_file_h, err_console_h],
    )

    return logger, error_logger, err_filepath


def get_script_log_folder() -> str:
    """Create and return the fixed ``logs`` directory beside this script.

    Log placement is intentionally deterministic: the application never falls back
    to /tmp or the current working directory. If the script directory is not
    writable, directory creation raises an error instead of silently moving logs.
    """
    script_dir = os.path.dirname(os.path.realpath(__file__))
    log_folder = os.path.join(script_dir, "logs")
    os.makedirs(log_folder, exist_ok=True)
    return log_folder



def script_base_name() -> str:
    """Return script name without extension, safe for filenames."""
    base = os.path.splitext(os.path.basename(__file__))[0]
    # Replace spaces or weird chars just in case
    return re.sub(r"[^A-Za-z0-9._-]+", "_", base)


class CommandError(RuntimeError):
    def __init__(self, cmd, returncode, stdout, stderr):
        super().__init__(f"Command failed ({returncode}): {' '.join(cmd)}")
        self.cmd = cmd
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


class DatasetFailuresError(RuntimeError):
    """Summarize one or more dataset-level ZFS command failures for final reporting.

    The cleanup loop records checked ``CommandError`` failures per configured dataset.
    When the matching continuation option is enabled, later datasets are still tried;
    regardless of continuation, this exception keeps the overall run failed and carries
    combined stderr so the existing MQTT report can expose the original ZFS diagnostics.
    """

    def __init__(self, failures):
        self.failures = list(failures)
        stderr_messages = []
        missing = []
        other = []

        for dataset, kind, error in self.failures:
            if error.stderr:
                stderr_messages.append(f"[{dataset}] {error.stderr}")
            if kind == "missing":
                missing.append(dataset)
            else:
                other.append(f"{dataset} (rc={error.returncode})")

        self.stderr = "\n".join(stderr_messages).strip()
        parts = []
        if missing:
            parts.append(f"Missing ZFS dataset(s): {', '.join(missing)}")
        if other:
            parts.append(f"Other ZFS failure(s): {', '.join(other)}")
        detail = "; ".join(parts) if parts else "Dataset-level ZFS failure"
        super().__init__(
            f"{detail}. The overall cleanup result is failure; later configured datasets "
            "were processed only where the matching continuation option was enabled."
        )


def is_missing_dataset_error(error: CommandError) -> bool:
    """Return True only for ZFS's explicit 'dataset does not exist' diagnostic."""
    return "dataset does not exist" in (error.stderr or "").lower()


def run_cmd(
    cmd,
    logger: logging.Logger | None = None,
    error_logger: logging.Logger | None = None,
    check: bool = True,
    log_stdout: bool = True,
    log_stderr: bool = True,
):
    """
    Run a system command with robust logging.

    - Command is logged at DEBUG
    - stdout logged at DEBUG (optional)
    - stderr logged at ERROR on failure
    - Raises CommandError if check=True and returncode != 0
    """
    if logger:
        logger.debug(f"Running command: {' '.join(cmd)}")

    proc = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
    )

    stdout = (proc.stdout or "").strip()
    stderr = (proc.stderr or "").strip()

    if proc.returncode == 0:
        if logger and log_stdout and stdout:
            logger.debug(f"Command stdout:\n{stdout}")
    else:
        if error_logger:
            error_logger.error(
                f"Command failed (rc={proc.returncode}): {' '.join(cmd)}"
            )
            if log_stderr and stderr:
                error_logger.error(f"stderr:\n{stderr}")
            if log_stdout and stdout:
                error_logger.error(f"stdout:\n{stdout}")

        if check:
            raise CommandError(cmd, proc.returncode, stdout, stderr)

    return proc

def get_newest_files(log_dir: str, prefix: str):
    files = glob.glob(os.path.join(log_dir, f"{prefix}*"))
    files.sort(key=os.path.getmtime, reverse=True)

    newest_log = None
    newest_err = None

    for file in files:
        ext = os.path.splitext(file)[-1][1:]
        if ext == "log" and not newest_log:
            newest_log = file
        elif ext == "err" and not newest_err:
            newest_err = file
        if newest_log and newest_err:
            break

    return newest_log, newest_err


def read_hostnames(path: str) -> List[str]:
    """Read hostnames (one per line), ignoring blanks and # comments."""
    with open(path, "r", encoding="utf-8") as f:
        out: List[str] = []
        for ln in f.read().splitlines():
            ln = ln.strip()
            if not ln or ln.startswith("#"):
                continue
            out.append(ln)
    return out


def send_mail(subject, body, recipient, attachment_files=None):
    # Put all options before the recipient. This is more compatible with mail/mailx variants.
    mail_command = ['mail', '-s', subject]

    if attachment_files:
        for file in attachment_files:
            mail_command.extend(['--attach', file])

    mail_command.append(recipient)

    if not body:
        body = "No mail body was generated. Check attached logs.\n"

    process = subprocess.Popen(mail_command, stdin=subprocess.PIPE, stderr=subprocess.PIPE)
    _, stderr_output = process.communicate(input=body.encode())
    return process.returncode, stderr_output.decode().strip()


def print_separator(logger, error_logger=None):
    separator_length = 20
    separator = "\n\n" + "-" * separator_length + "\n"
    if error_logger:
        error_logger.error(separator)
    else:
        logger.info(separator)


def log_blank_line(logger: logging.Logger):
    logger.info("")

def WasMailSent(logger, error_logger, MailExitCode, popenstderr):
    if MailExitCode == 0:
        print_separator(logger)
        logger.info('Mail was sent successfully')
    else:
        print_separator(logger, error_logger)
        error_logger.error('There was an error sending the mail')
        error_logger.error('This is what popen said')
        error_logger.error('')
        error_logger.error(popenstderr)
        error_logger.error('')
        error_logger.error('----------')


def build_backup_mail_header(backup_title: str = "", backup_comment: str = "") -> str:
    """
    Build the optional text block that is written at the very top of notification emails.

    The email subject still stays as SUCCESS/FAILED. These values are only written
    into the body of the mail.
    """
    backup_title = (backup_title or "").strip()
    backup_comment = (backup_comment or "").strip()

    if not backup_title and not backup_comment:
        return ""

    lines = [
        f"Title: {backup_title}",
        "Comment:",
    ]

    if backup_comment:
        lines.append(backup_comment)

    return "\n".join(lines).rstrip() + "\n\n"


def MailTo(
    logger,
    error_logger,
    recipient,
    log_folder: str,
    prefix: str,
    subject: str = "Syncoid cleanup report - logs attached",
    intro: str = "",
    backup_title: str = "",
    backup_comment: str = "",
):
    log_blank_line(logger)
    logger.info("Preparing email report...")

    newest_log, newest_err = get_newest_files(log_folder, prefix)
    attachment_files = []
    body = build_backup_mail_header(backup_title, backup_comment)

    if intro:
        body += intro.strip() + "\n\n"

    if newest_err and os.path.isfile(newest_err) and os.path.getsize(newest_err) > 0:
        attachment_files.append(newest_err)
        with open(newest_err, 'r', encoding="utf-8") as err_file:
            body += "----------\n\n.err file\n" + err_file.read()

    if newest_log:
        attachment_files.append(newest_log)
        if os.path.isfile(newest_log):
            with open(newest_log, 'r', encoding="utf-8", errors="replace") as log_file:
                body += "----------\n\n.log file\n" + log_file.read()

    if not body.strip():
        body = "No log content was found. Check the script output on the host.\n"

    mail_exit_code, stderr_output = send_mail(subject, body, recipient, attachment_files)
    WasMailSent(logger, error_logger, mail_exit_code, stderr_output)



def parse_syncoid_ts(ts: str) -> datetime.datetime:
    """
    Parse: YYYY-MM-DD:HH:MM:SS-GMT(+|-)HH:MM
    Examples:
      2023-09-09:15:34:26-GMT02:00   (treated as +02:00)
      2023-09-09:15:34:26-GMT-01:00
    """
    m = re.match(
        r"^(?P<date>\d{4}-\d{2}-\d{2}):(?P<time>\d{2}:\d{2}:\d{2})-GMT(?P<off>[+-]?\d{2}:\d{2})$",
        ts,
    )
    if not m:
        raise ValueError(f"Invalid syncoid timestamp: {ts}")

    dt_part = f"{m.group('date')} {m.group('time')}"
    dt = datetime.datetime.strptime(dt_part, "%Y-%m-%d %H:%M:%S")

    off = m.group("off")
    # If syncoid writes "GMT02:00" (no sign), treat as +02:00
    if off[0] not in "+-":
        off = "+" + off

    sign = 1 if off[0] == "+" else -1
    hh = int(off[1:3])
    mm = int(off[4:6])
    tz = datetime.timezone(sign * datetime.timedelta(hours=hh, minutes=mm))

    return dt.replace(tzinfo=tz)


def delete_syncoid_snapshots(
    logger: logging.Logger,
    error_logger: logging.Logger,
    dataset: str,
    hostnames: List[str],
    older_than: Optional[datetime.timedelta],
    retain_count: int,
    dry_run: bool,
) -> dict:
    """Prune or preview one dataset and return counts for the final run report."""
    if not hostnames:
        logger.info(f"[{dataset}] No hostnames provided. Skipping syncoid pruning.")
        return {"dataset": dataset, "matched": 0, "selected": 0}

    # Build one regex that matches any hostname in the list
    # <dataset>@syncoid_<hostname>_<timestamp>
    host_alt = "|".join(re.escape(h) for h in hostnames)
    snap_regex = re.compile(
        rf"^(?P<full>.+)@syncoid_(?P<host>{host_alt})_(?P<ts>\d{{4}}-\d{{2}}-\d{{2}}:\d{{2}}:\d{{2}}:\d{{2}}-GMT[+-]?\d{{2}}:\d{{2}})$"
    )

    proc = run_cmd(
        ["zfs", "list", "-H", "-t", "snapshot", "-o", "name", dataset],
        logger=logger,
        error_logger=error_logger,
        check=True,
    )
    lines = [ln.strip() for ln in (proc.stdout or "").splitlines() if ln.strip()]
    if not lines:
        return {"dataset": dataset, "matched": 0, "selected": 0}

    # Group snapshots by hostname
    by_host: dict[str, list[tuple[datetime.datetime, str]]] = {h: [] for h in hostnames}

    for s in lines:
        m = snap_regex.match(s)
        if not m:
            continue
        host = m.group("host")
        ts_str = m.group("ts")
        try:
            ts = parse_syncoid_ts(ts_str)
        except Exception as e:
            error_logger.error(f"Skipping snapshot with bad syncoid timestamp: {s} ({e})")
            continue
        by_host.setdefault(host, []).append((ts, s))

    # Decide deletions per host
    now_utc = datetime.datetime.now(datetime.timezone.utc)
    cutoff_utc = (now_utc - older_than) if older_than else None

    total_delete = 0
    total_matched = 0

    first_host_printed = True

    for host, snaps in by_host.items():
        if not snaps:
            continue
        
        # Print a blank line between hosts
        if not first_host_printed:
            logger.info("")
        first_host_printed = False

        total_matched += len(snaps)

        # Newest first
        snaps.sort(key=lambda x: x[0].astimezone(datetime.timezone.utc), reverse=True)

        keep_set = set()
        if retain_count > 0:
            keep_set = set(s for _, s in snaps[:retain_count])

        if cutoff_utc is not None:
            to_delete = [
                s for ts, s in snaps
                if (s not in keep_set and ts.astimezone(datetime.timezone.utc) < cutoff_utc)
            ]
            logger.info(
                f"[{dataset}] host={host} matched={len(snaps)} retain={retain_count} cutoff_utc={cutoff_utc.isoformat()} delete={len(to_delete)}"
            )
        else:
            # retain-only: delete all except keep_set
            to_delete = [s for _, s in snaps if s not in keep_set]
            logger.info(
                f"[{dataset}] host={host} matched={len(snaps)} retain={retain_count} (no cutoff) delete={len(to_delete)}"
            )

        if to_delete:
            log_blank_line(logger)
        
        for snap_name in to_delete:
            if dry_run:
                logger.info(f"[DRY-RUN] Would delete syncoid snapshot: {snap_name}")
            else:
                run_cmd(
                    ["zfs", "destroy", snap_name],
                    logger=logger,
                    error_logger=error_logger,
                    check=True,
                )
                logger.info(f"[{dataset}] Deleted syncoid snapshot: {snap_name}")

        total_delete += len(to_delete)

    if dry_run:
        log_blank_line(logger)
        logger.info(f"[{dataset}] DRY-RUN complete. Snapshots that WOULD be deleted: {total_delete}")
    else:
        log_blank_line(logger)
        logger.info(f"[{dataset}] Syncoid pruning done. Deleted total: {total_delete}")

    return {"dataset": dataset, "matched": total_matched, "selected": total_delete}


def log_dry_run_report(logger: logging.Logger, report: dict) -> None:
    """Write one final dry-run summary that is also captured by success/failure email logs."""
    print_separator(logger)
    logger.info("DRY-RUN REPORT")
    logger.info(f"Datasets configured: {report['datasets_configured']}")
    logger.info(f"Datasets completed: {report['datasets_completed']}")
    logger.info(f"Dataset failures: {report['dataset_failures']}")
    logger.info(f"Matching Syncoid snapshots found: {report['snapshots_matched']}")
    logger.info(f"Snapshots that WOULD be deleted: {report['snapshots_would_delete']}")
    logger.info("Snapshots actually destroyed: 0")
    if report["log_retention_evaluated"]:
        logger.info(f"Old log groups that WOULD be deleted: {report['log_groups_would_delete']}")
        logger.info(f"Old log files that WOULD be deleted: {report['log_files_would_delete']}")
    else:
        logger.info("Old-log retention preview: not evaluated because the dry-run did not complete successfully.")
    for item in report["datasets"]:
        logger.info(
            f"[{item['dataset']}] report: matched={item['matched']} "
            f"would_delete={item['selected']}"
        )
    logger.info("Dry-run made no snapshot deletions and no old-log deletions.")
    print_separator(logger)


def delete_old_files(
    logger: logging.Logger,
    error_logger: logging.Logger,
    log_folder: str,
    prefix: str,
    older_than: Optional[datetime.timedelta],
    retain_count: int,
    dry_run: bool,
) -> dict:
    """
    Apply log retention and return counts for the dry-run/finalization report.

    Log deletion rules mirror snapshot pruning:
      - If retain_count > 0: always keep newest retain_count timestamp groups.
      - If older_than is provided: delete groups older than cutoff (excluding kept).
      - If older_than is NOT provided: delete everything not in keep_set (retain-only).
      - If older_than is None AND retain_count == 0: do nothing.
    """
    if older_than is None and retain_count <= 0:
        return {"groups_matched": 0, "groups_selected": 0, "files_selected": 0}

    os.makedirs(log_folder, exist_ok=True)

    date_pattern = re.compile(
        rf"{re.escape(prefix)}[-_][Dd]ate[-_]?(?P<ts>\d{{4}}-\d{{2}}-\d{{2}}_\d{{2}}_\d{{2}}_\d{{2}})\.(?P<ext>log|err)$"
    )

    files_by_ts: dict[datetime.datetime, List[str]] = {}

    for filename in os.listdir(log_folder):
        m = date_pattern.search(filename)
        if not m:
            continue
        ts_str = m.group("ts")
        try:
            ts = datetime.datetime.strptime(ts_str, "%Y-%m-%d_%H_%M_%S")
        except ValueError:
            continue
        files_by_ts.setdefault(ts, []).append(filename)

    if not files_by_ts:
        return {"groups_matched": 0, "groups_selected": 0, "files_selected": 0}

    # Newest first
    all_dates = sorted(files_by_ts.keys(), reverse=True)

    keep_set = set()
    if retain_count > 0:
        keep_set = set(all_dates[:retain_count])

    if older_than is not None:
        cutoff = datetime.datetime.now() - older_than
        eligible = [d for d in all_dates if (d not in keep_set and d < cutoff)]
    else:
        eligible = [d for d in all_dates if (d not in keep_set)]

    selected_files = sum(len(files_by_ts.get(d, [])) for d in eligible)

    for d in eligible:
        for filename in files_by_ts.get(d, []):
            path_to_file = os.path.join(log_folder, filename)
            if dry_run:
                logger.info(f"[DRY-RUN] Would delete log file: {filename}")
            else:
                try:
                    os.remove(path_to_file)
                    logger.info(f"Deleted file: {filename}")
                except Exception as e:
                    error_logger.error(f"Failed to delete file: {filename}. Error: {e}")

    return {
        "groups_matched": len(all_dates),
        "groups_selected": len(eligible),
        "files_selected": selected_files,
    }

def main():
    default_script_name = script_base_name()

    # The application intentionally exposes one operational setting on the CLI:
    # which TOML file to load. Standard -h/--help is available for discoverability;
    # all cleanup, retention, mail, report, logging, and MQTT behavior lives in TOML.
    parser = argparse.ArgumentParser(
        description="Delete matching syncoid ZFS snapshots using one TOML configuration file.",
        usage="%(prog)s -c CONFIG\n       %(prog)s --help\n       %(prog)s --version",
        epilog=(
            "Examples:\n"
            "  %(prog)s -c config.toml\n"
            "  %(prog)s --config /etc/cleanup-syncoid/config.toml"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
        help="Show the application version and exit without loading configuration or running cleanup.",
    )
    parser.add_argument(
        "-c",
        "--config",
        dest="config",
        metavar="CONFIG",
        required=False,
        help=(
            "Path to the TOML configuration file. All cleanup, retention, continuation, "
            "logging, mail, report, and MQTT settings are read from this file."
        ),
    )
    cli_args, unknown_args = parser.parse_known_args()
    if unknown_args:
        parser.error(f"unrecognized arguments: {' '.join(unknown_args)}")
    if not cli_args.config:
        parser.error("the following arguments are required: -c/--config")

    try:
        args = load_config(cli_args.config, default_script_name)
    except (OSError, ValueError, RuntimeError) as exc:
        # Configuration can contain credentials, so report only the error message and
        # never dump the parsed document or raw TOML contents.
        parser.error(f"Cannot load configuration: {exc}")

    mqtt_config = args.mqtt_config
    state = {}
    exit_code = 0
    failure = None
    try:
        run_cleanup(args, state)
    except SystemExit as exc:
        exit_code = exc.code if isinstance(exc.code, int) else (0 if exc.code is None else 1)
        failure = state.get("error") or (str(exc) if exit_code else None)
        raise
    except KeyboardInterrupt:
        exit_code = 130
        failure = "Cleanup interrupted by user"
        raise
    except Exception as exc:
        exit_code = 1
        failure = exc
        raise
    finally:
        # Report only after existing mail and log cleanup have finished.
        if mqtt_config is not None:
            report = build_mqtt_report(
                args,
                __version__,
                exit_code,
                failure,
                state.get("warning", False),
                state.get("dry_run_report"),
            )
            report_success = report.get("status") == "success"
            if should_send_notification(report_success, mqtt_config["on_success"]):
                notify_mqtt(mqtt_config, report, state.get("error_logger"))
        warning_handler = state.get("warning_handler")
        if warning_handler:
            state["error_logger"].removeHandler(warning_handler)
            warning_handler.close()


def run_cleanup(args, state):
    """Run cleanup and apply configured per-dataset continuation rules for ZFS failures."""
    prefix = args.log_prefix
    retain_count = max(int(args.retain_count or 0), 0)
    older_than = args.older_than  # Optional[datetime.timedelta]
    backup_title = args.backup_title
    backup_comment = args.backup_comment

    log_date = datetime.datetime.now().strftime('%Y-%m-%d_%H_%M_%S')

    # Logs always live in <actual script directory>/logs. The directory is created
    # automatically; failure to create it is fatal rather than silently relocating logs.
    log_folder = get_script_log_folder()

    logger, error_logger, err_filepath = setup_logger(log_folder, log_date, prefix)
    state.update(error_logger=error_logger, err_filepath=err_filepath)
    if args.mqtt_config:
        warning_handler = ReportWarningHandler(state)
        error_logger.addHandler(warning_handler)
        state["warning_handler"] = warning_handler

    if os.geteuid() != 0:
        msg = (
            "This script must be run as root (sudo). "
            f"Logs were written to: {log_folder}."
        )
        state["error"] = msg
        error_logger.error(msg)

        try:
            if args.send_mail and should_send_notification(False, args.mail_on_success):
                MailTo(
                    logger,
                    error_logger,
                    recipient=args.send_mail,
                    log_folder=log_folder,
                    prefix=prefix,
                    subject="Syncoid cleanup FAILED - not run as root",
                    intro=msg,
                    backup_title=backup_title,
                    backup_comment=backup_comment,
                )
        except Exception as mail_e:
            error_logger.error(f"Additionally failed to send mail: {mail_e}")

        sys.exit(1)

    dry_run = args.dry_run = (args.command == 'dry-run')
    success = False
    dataset_failure = None
    dataset_failures = []
    dry_run_report = None
    if dry_run:
        dry_run_report = {
            "datasets_configured": 0,
            "datasets_completed": 0,
            "dataset_failures": 0,
            "snapshots_matched": 0,
            "snapshots_would_delete": 0,
            "log_retention_evaluated": False,
            "log_groups_would_delete": 0,
            "log_files_would_delete": 0,
            "datasets": [],
        }
        state["dry_run_report"] = dry_run_report

    try:
        # Read input files inside the try block, so bad paths also trigger error mail.
        with open(args.datasets_file, "r", encoding="utf-8") as file:
            datasets = [ln.strip() for ln in file.read().splitlines() if ln.strip()]

        syncoid_hosts = read_hostnames(args.syncoid_hosts_file)
        if dry_run_report is not None:
            dry_run_report["datasets_configured"] = len(datasets)

        if args.command == 'delete':
            print_separator(logger)
            logger.info("Starting snapshot deletion...")
            print_separator(logger)

        for dataset in datasets:
            try:
                dataset_report = delete_syncoid_snapshots(
                    logger,
                    error_logger,
                    dataset,
                    syncoid_hosts,
                    older_than,
                    retain_count,
                    dry_run,
                )
                if dry_run_report is not None:
                    dry_run_report["datasets_completed"] += 1
                    dry_run_report["snapshots_matched"] += dataset_report["matched"]
                    dry_run_report["snapshots_would_delete"] += dataset_report["selected"]
                    dry_run_report["datasets"].append(dataset_report)
            except CommandError as exc:
                missing = is_missing_dataset_error(exc)
                kind = "missing" if missing else "other"
                dataset_failures.append((dataset, kind, exc))
                if dry_run_report is not None:
                    dry_run_report["dataset_failures"] = len(dataset_failures)
                dataset_failure = DatasetFailuresError(dataset_failures)
                state["error"] = dataset_failure

                continue_enabled = (
                    args.continue_on_missing_dataset
                    if missing
                    else args.continue_on_other_failures
                )
                if continue_enabled:
                    label = "Configured ZFS dataset does not exist" if missing else "ZFS command failed"
                    error_logger.error(
                        f"[{dataset}] {label}; continuation is enabled, continuing with the next dataset."
                    )
                else:
                    option = (
                        "cleanup.continue_on_missing_dataset"
                        if missing
                        else "cleanup.continue_on_other_failures"
                    )
                    error_logger.error(
                        f"[{dataset}] Continuation is disabled by {option}=false; stopping cleanup."
                    )
                    raise dataset_failure from exc
            print_separator(logger)

        print_separator(logger)
        if dataset_failures:
            mode = "dry-run" if args.command == "dry-run" else "deletion"
            logger.info(f"Snapshot {mode} processing completed with dataset failures.")
        elif args.command == 'dry-run':
            logger.info("Snapshot dry-run completed.")
        else:
            logger.info("Snapshot deletion completed.")

        if dataset_failures:
            dataset_failure = DatasetFailuresError(dataset_failures)
            state["error"] = dataset_failure
            error_logger.error(str(dataset_failure))
        else:
            if dry_run_report is not None:
                log_report = delete_old_files(
                    logger, error_logger, log_folder, prefix, older_than, retain_count, True
                )
                dry_run_report["log_retention_evaluated"] = True
                dry_run_report["log_groups_would_delete"] = log_report["groups_selected"]
                dry_run_report["log_files_would_delete"] = log_report["files_selected"]
            success = True

    except Exception as e:
        error_logger.error(f"Fatal error: {e}")
        raise

    finally:
        if dry_run_report is not None:
            dry_run_report["dataset_failures"] = len(dataset_failures)
            log_dry_run_report(logger, dry_run_report)

        if success:
            if args.send_mail and not args.mail_on_success:
                logger.info("Success mail report suppressed by mail.on_success=false.")
            if args.mqtt_config and not args.mqtt_config["on_success"]:
                logger.info("Success MQTT report suppressed by mqtt.on_success=false.")

        try:
            if args.send_mail and should_send_notification(success, args.mail_on_success) and not success:
                intro = "Cleanup failed. See attached logs."
                if dataset_failure is not None:
                    intro = (
                        f"Cleanup completed or stopped with a failure because {dataset_failure} "
                        "See attached logs for the original ZFS diagnostics."
                    )
                if dry_run:
                    if dataset_failure is not None:
                        intro = (
                            f"Dry-run completed or stopped with a failure because {dataset_failure} "
                            "No snapshots or old log files were deleted. "
                            "See the dry-run report and attached logs for the original ZFS diagnostics."
                        )
                    else:
                        intro = (
                            "Dry-run failed. No snapshots or old log files were intentionally deleted. "
                            "See the dry-run report and attached logs."
                        )
                MailTo(
                    logger,
                    error_logger,
                    recipient=args.send_mail,
                    log_folder=log_folder,
                    prefix=prefix,
                    subject=(
                        "Syncoid cleanup DRY-RUN FAILED - report/logs attached"
                        if dry_run
                        else "Syncoid cleanup FAILED - logs attached"
                    ),
                    intro=intro,
                    backup_title=backup_title,
                    backup_comment=backup_comment,
                )

            # Success notifications are opt-in for both delete and dry-run.
            elif args.send_mail and should_send_notification(success, args.mail_on_success) and success:
                MailTo(
                    logger,
                    error_logger,
                    recipient=args.send_mail,
                    log_folder=log_folder,
                    prefix=prefix,
                    subject=(
                        "Syncoid cleanup DRY-RUN SUCCESS - report/logs attached"
                        if dry_run
                        else "Syncoid cleanup SUCCESS - logs attached"
                    ),
                    intro=(
                        "Dry-run completed successfully. No snapshots or old log files were deleted. "
                        "The dry-run report is included below and in the attached log."
                        if dry_run
                        else "Cleanup completed successfully. Logs attached."
                    ),
                    backup_title=backup_title,
                    backup_comment=backup_comment,
                )
        except Exception as mail_e:
            error_logger.error(f"Failed to send notification mail: {mail_e}")

        if success and not dry_run:
            delete_old_files(logger, error_logger, log_folder, prefix, older_than, retain_count, False)

        # Clean up empty .err file
        if os.path.exists(err_filepath) and os.path.getsize(err_filepath) == 0:
            os.remove(err_filepath)

    if dataset_failure is not None:
        sys.exit(1)


if __name__ == "__main__":
    main()
