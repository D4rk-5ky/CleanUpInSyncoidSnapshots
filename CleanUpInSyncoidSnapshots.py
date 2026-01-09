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
import tempfile


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


def pick_log_folder(script_log_folder: str, tmp_name: str = "SnapBeforeWatchTower") -> str:
    """
    Policy:
      - If NOT root: always use /tmp/<tmp_name>
      - If root: try <script>/logs; if not writable, fall back to /tmp/<tmp_name>
    """
    tmp_folder = os.path.join(tempfile.gettempdir(), tmp_name)

    def _ensure_writable(path: str) -> bool:
        try:
            os.makedirs(path, exist_ok=True)
            test_path = os.path.join(path, ".write_test")
            with open(test_path, "w", encoding="utf-8") as f:
                f.write("ok")
            os.remove(test_path)
            return True
        except Exception:
            return False

    if os.geteuid() != 0:
        os.makedirs(tmp_folder, exist_ok=True)
        return tmp_folder

    if _ensure_writable(script_log_folder):
        return script_log_folder

    os.makedirs(tmp_folder, exist_ok=True)
    return tmp_folder


class CommandError(RuntimeError):
    def __init__(self, cmd, returncode, stdout, stderr):
        super().__init__(f"Command failed ({returncode}): {' '.join(cmd)}")
        self.cmd = cmd
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


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


def send_mail(subject, body, recipient, attachment_files=None):
    mail_command = ['mail', '-s', subject, recipient]
    if attachment_files:
        for file in attachment_files:
            mail_command.extend(['--attach', file])

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


def MailTo(logger, error_logger, recipient, log_folder: str, prefix: str):
    print_separator(logger)
    logger.info('There is an option to send a mail')

    subject = "Error snapshotting or cleaning up snapshots/logs - attaching logs"

    newest_log, newest_err = get_newest_files(log_folder, prefix)
    attachment_files = []
    body = ""

    if newest_log:
        attachment_files.append(newest_log)
    if newest_err:
        attachment_files.append(newest_err)

    if newest_err and os.path.isfile(newest_err):
        with open(newest_err, 'r', encoding="utf-8") as err_file:
            body += "----------\n\n.err file\n" + err_file.read()

    if newest_log and os.path.isfile(newest_log):
        with open(newest_log, 'r', encoding="utf-8") as log_file:
            body += "----------\n\n.log file\n" + log_file.read()

    mail_exit_code, stderr_output = send_mail(subject, body, recipient, attachment_files)

    if mail_exit_code == 0:
        WasMailSent(logger, error_logger, 0, "")
    else:
        WasMailSent(logger, error_logger, mail_exit_code, stderr_output)


def parse_older_than(value: str) -> datetime.timedelta:
    pattern = r'^(\d+)([dwm])$'
    match = re.match(pattern, value)
    if not match:
        raise argparse.ArgumentTypeError("Invalid value for --older-than. Use format 'Nd', 'Nw', or 'Nm' (N=integer).")

    num = int(match.group(1))
    unit = match.group(2)

    if unit == 'd':
        return datetime.timedelta(days=num)
    if unit == 'w':
        return datetime.timedelta(weeks=num)
    if unit == 'm':
        return datetime.timedelta(days=num * 30)
    raise argparse.ArgumentTypeError("Invalid value for --older-than. Use format 'Nd', 'Nw', or 'Nm' (N=integer).")


def create_snapshot(
    logger: logging.Logger,
    error_logger: logging.Logger,
    dataset: str,
    prefix: str,
):
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H_%M_%S")
    snapshot_name = f"{prefix}-Date-{timestamp}"
    full_snapshot_name = f"{dataset}@{snapshot_name}"

    logger.info(f"Creating snapshot of: {dataset}")
    logger.debug(f"Full snapshot name: {full_snapshot_name}")

    try:
        run_cmd(
            ["zfs", "snapshot", full_snapshot_name],
            logger=logger,
            error_logger=error_logger,
            check=True,
        )
    except CommandError:
        print_separator(logger, error_logger)
        error_logger.error(
            f"Error creating snapshot of {dataset} (snapshot: {full_snapshot_name})"
        )
        raise

def delete_old_snapshots(
    logger: logging.Logger,
    error_logger: logging.Logger,
    dataset: str,
    prefix: str,
    older_than: Optional[datetime.timedelta],
    retain_count: int,
) -> None:
    """
    Deletion rules:
      - If retain_count > 0: always keep newest retain_count.
      - If older_than is provided: delete snapshots older than cutoff (but never delete kept ones).
      - If older_than is NOT provided: delete everything not in keep_set (retain-only pruning).
      - If older_than is None AND retain_count == 0: do nothing.
    """
    if older_than is None and retain_count <= 0:
        logger.info(f"[{dataset}] No pruning configured (no --older-than and retain_count=0). Skipping.")
        return

    # Match: <dataset>@<prefix>-Date-YYYY-MM-DD_HH_MM_SS
    snap_regex = re.compile(
        rf"^(?P<full>.+)@{re.escape(prefix)}-Date-?(?P<ts>\d{{4}}-\d{{2}}-\d{{2}}_\d{{2}}_\d{{2}}_\d{{2}})$"
    )

    proc = run_cmd(["zfs", "list", "-H", "-t", "snapshot", "-o", "name", dataset], logger, error_logger, check=True)
    lines = [ln.strip() for ln in proc.stdout.splitlines() if ln.strip()]
    if not lines:
        return

    snaps: List[Tuple[datetime.datetime, str]] = []
    for s in lines:
        m = snap_regex.match(s)
        if not m:
            continue
        ts_str = m.group("ts")
        try:
            ts = datetime.datetime.strptime(ts_str, "%Y-%m-%d_%H_%M_%S")
        except ValueError as e:
            error_logger.error(f"Skipping snapshot with unparseable timestamp: {s} ({e})")
            continue
        snaps.append((ts, s))

    if not snaps:
        return

    snaps.sort(key=lambda x: x[0], reverse=True)

    keep_set = set()
    if retain_count > 0:
        keep_set = set(s for _, s in snaps[:retain_count])

    # Decide deletions
    if older_than is not None:
        cutoff = datetime.datetime.now() - older_than
        to_delete = [s for ts, s in snaps if (s not in keep_set and ts < cutoff)]
        logger.info(f"[{dataset}] Found {len(snaps)} matching snapshots (retain_count={retain_count}).")
        logger.info(f"[{dataset}] Cutoff time: {cutoff.strftime('%Y-%m-%d %H:%M:%S')}  (older_than={older_than})")
    else:
        # retain-only: delete everything not in keep_set
        to_delete = [s for _, s in snaps if (s not in keep_set)]
        logger.info(f"[{dataset}] Found {len(snaps)} matching snapshots (retain_count={retain_count}).")
        logger.info(f"[{dataset}] No cutoff (--older-than not set). Retain-only pruning enabled.")

    logger.info(f"[{dataset}] Will delete {len(to_delete)} snapshot(s).")

    for snap_name in to_delete:
        run_cmd(["zfs", "destroy", snap_name], logger=logger, error_logger=error_logger, check=True)
        logger.info(f"[{dataset}] Deleted snapshot: {snap_name}")


def delete_old_files(
    logger: logging.Logger,
    error_logger: logging.Logger,
    log_folder: str,
    prefix: str,
    older_than: Optional[datetime.timedelta],
    retain_count: int,
) -> None:
    """
    Log deletion rules mirror snapshot pruning:
      - If retain_count > 0: always keep newest retain_count timestamp groups.
      - If older_than is provided: delete groups older than cutoff (excluding kept).
      - If older_than is NOT provided: delete everything not in keep_set (retain-only).
      - If older_than is None AND retain_count == 0: do nothing.
    """
    if older_than is None and retain_count <= 0:
        return

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
        return

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

    for d in eligible:
        for filename in files_by_ts.get(d, []):
            path_to_file = os.path.join(log_folder, filename)
            try:
                os.remove(path_to_file)
                logger.info(f"Deleted file: {filename}")
            except Exception as e:
                error_logger.error(f"Failed to delete file: {filename}. Error: {e}")


def main():
    parser = argparse.ArgumentParser(description='Create or delete snapshots for ZFS datasets.')
    parser.add_argument('-c', '--command', choices=['create', 'delete'], required=True, help='Command: create or delete')
    parser.add_argument('-f', '--file', required=True, help='Path to the file containing the dataset names')

    # NEW: optional older-than
    parser.add_argument('--older-than', type=parse_older_than, required=False,
                        help="Delete snapshots/logs older than 'Nd', 'Nw', or 'Nm' (N=integer)")

    # NEW: optional retain-count (default 0)
    parser.add_argument('--retain-count', type=int, default=0,
                        help='Number of newest snapshots/log groups to retain (default: 0)')

    # NEW: custom snapshot/log prefix
    parser.add_argument('--snap-name', default="SnapBeforeWatchTower",
                        help="Snapshot/log prefix. Timestamp will be appended as '<snap-name>-Date-YYYY-MM-DD_HH_MM_SS'")

    parser.add_argument('--send-mail', metavar='EMAIL', help='Send an email notification to the specified email address')

    args = parser.parse_args()

    prefix = args.snap_name
    retain_count = max(int(args.retain_count or 0), 0)
    older_than = args.older_than  # Optional[datetime.timedelta]

    log_date = datetime.datetime.now().strftime('%Y-%m-%d_%H_%M_%S')

    SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
    preferred_log_folder = os.path.join(SCRIPT_DIR, "logs")
    log_folder = pick_log_folder(preferred_log_folder)

    logger, error_logger, err_filepath = setup_logger(log_folder, log_date, prefix)

    if os.geteuid() != 0:
        msg = (
            "This script must be run as root (sudo). "
            f"Logs were written to: {log_folder} (fallback, because not root)."
        )
        error_logger.error(msg)

        try:
            if args.send_mail:
                MailTo(logger, error_logger, recipient=args.send_mail, log_folder=log_folder, prefix=prefix)
        except Exception as mail_e:
            error_logger.error(f"Additionally failed to send mail: {mail_e}")

        sys.exit(1)

    with open(args.file, "r", encoding="utf-8") as file:
        datasets = [ln.strip() for ln in file.read().splitlines() if ln.strip()]

    try:
        if args.command == 'create':

            print_separator(logger)
            logger.info("Starting snapshot creation...")

            for dataset in datasets:
                print_separator(logger)
                create_snapshot(logger, error_logger, dataset, prefix)
                delete_old_snapshots(logger, error_logger, dataset, prefix, older_than, retain_count)

            print_separator(logger)
            logger.info("Snapshot creation completed.")
            delete_old_files(logger, error_logger, log_folder, prefix, older_than, retain_count)

        elif args.command == 'delete':
            print_separator(logger)
            logger.info("Starting snapshot deletion...")

            for dataset in datasets:
                delete_old_snapshots(logger, error_logger, dataset, prefix, older_than, retain_count)

            print_separator(logger)
            logger.info("Snapshot deletion completed.")
            delete_old_files(logger, error_logger, log_folder, prefix, older_than, retain_count)

    except Exception as e:
        error_logger.error(f"Fatal error: {e}")
        try:
            if args.send_mail:
                MailTo(logger, error_logger, recipient=args.send_mail, log_folder=log_folder, prefix=prefix)
        except Exception as mail_e:
            error_logger.error(f"Additionally failed to send mail: {mail_e}")
        raise

    finally:
        if os.path.exists(err_filepath) and os.path.getsize(err_filepath) == 0:
            os.remove(err_filepath)


if __name__ == "__main__":
    main()
