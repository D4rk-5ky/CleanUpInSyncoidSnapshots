"""Optional, bounded MQTT status delivery; no snapshot operations live here."""

import datetime
import json
import math
import os
import signal
from pathlib import Path
import ssl
import subprocess
import sys


DEFAULTS = {
    "port": 1883,
    "username": None,
    "password": None,
    "client_id": "",
    "qos": 1,
    "timeout": 15,
    "tls": False,
    "ca_certs": None,
    "certfile": None,
    "keyfile": None,
    "on_success": False,
}


def should_send_notification(success: bool, on_success: bool) -> bool:
    """Return True for every failure, or for success only when explicitly enabled."""
    return (not success) or on_success


def validate_mqtt_config(supplied, base_dir):
    """Validate MQTT settings supplied by the main TOML file."""
    if not isinstance(supplied, dict):
        raise ValueError("[mqtt] settings must be a TOML table")
    unknown = set(supplied) - (set(DEFAULTS) | {"host", "topic"})
    if unknown:
        raise ValueError("[mqtt] contains unknown options")
    config = dict(DEFAULTS, **supplied)
    for key in ("host", "topic"):
        value = config.get(key)
        if not isinstance(value, str) or not value.strip() or "\x00" in value:
            raise ValueError(f"mqtt.{key} must be a nonempty string without NUL")
        config[key] = value.strip()
    if any(char in config["topic"] for char in "+#"):
        raise ValueError("mqtt.topic cannot contain + or # wildcards")
    if len(config["topic"].encode("utf-8")) > 65535:
        raise ValueError("mqtt.topic is too long")
    for key, minimum, maximum in (("port", 1, 65535), ("qos", 0, 2)):
        if type(config[key]) is not int or not minimum <= config[key] <= maximum:
            raise ValueError(f"mqtt.{key} must be an integer from {minimum} to {maximum}")
    timeout = config["timeout"]
    if type(timeout) not in (int, float) or not math.isfinite(timeout) or timeout <= 0:
        raise ValueError("mqtt.timeout must be a finite positive number of seconds")
    for key in ("tls", "on_success"):
        if type(config[key]) is not bool:
            raise ValueError(f"mqtt.{key} must be true or false")
    for key in ("username", "password", "ca_certs", "certfile", "keyfile"):
        value = config[key]
        if value is not None and not isinstance(value, str):
            raise ValueError(f"mqtt.{key} must be a string")
        if value == "":
            config[key] = None
    if not isinstance(config["client_id"], str):
        raise ValueError("mqtt.client_id must be a string")
    if config["password"] is not None and not config["username"]:
        raise ValueError("mqtt.password requires mqtt.username")
    if bool(config["certfile"]) != bool(config["keyfile"]):
        raise ValueError("mqtt.certfile and mqtt.keyfile must be supplied together")
    base_dir = Path(base_dir).resolve()
    for key in ("ca_certs", "certfile", "keyfile"):
        if config[key]:
            if not config["tls"]:
                raise ValueError(f"mqtt.{key} requires mqtt.tls=true")
            certificate = Path(config[key]).expanduser()
            if not certificate.is_absolute():
                certificate = base_dir / certificate
            certificate = certificate.resolve()
            if not certificate.is_file():
                raise ValueError(f"mqtt.{key} file does not exist")
            config[key] = str(certificate)
    return config


def build_mqtt_report(args, version, exit_code, error=None, warning=False, dry_run_report=None,
                      *, run_id=None, stderr_text=None, dataset_failures=None):
    """Adapt real cleanup results to typed completion JSON; dataset details are optional."""
    from mqtt_reporting import build_report
    friendly_name = getattr(args, "reporting_name", None) or args.backup_title.strip() or "CleanUpInSyncoidSnapshots"
    if stderr_text is None:
        # No stdout fallback: stderr must be actual child diagnostics.
        failures = getattr(error, "failures", None)
        stderr_text = "".join(item[2].stderr or "" for item in failures) if failures else (getattr(error, "stderr", "") or "")
    extra = {"job_type": "syncoid_snapshot_cleanup", "item_unit": "datasets", "outcome_item_unit": "snapshots"}
    if dry_run_report is not None:
        extra["dry_run_report"] = dry_run_report
    return build_report(name=friendly_name, title=friendly_name, job=args.log_prefix,
                        exit_code=exit_code, error_message=str(error) if error is not None else "",
                        stderr_text=stderr_text, warning=bool(warning), dry_run=args.command == "dry-run",
                        command=args.command, comment=args.backup_comment, version=version,
                        run_id=run_id, failed_datasets=dataset_failures or None, extra=extra)


def _run_publisher(command, *, input, timeout, env=None):
    """Bound a Linux publisher session, including PyInstaller's bootloader child.

    Killing only the direct launcher on timeout can leave the frozen Python child
    connected to the broker. A new session isolates the publisher's process group
    so timeout/interruption cleanup cannot signal the calling cleanup process.
    """
    with subprocess.Popen(
        command,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        env=env,
        start_new_session=True,
    ) as worker:
        try:
            stdout, stderr = worker.communicate(input=input, timeout=timeout)
        except BaseException:
            # Include the bootloader child even if its direct parent just exited.
            try:
                os.killpg(worker.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            worker.communicate()
            raise
        return subprocess.CompletedProcess(command, worker.returncode, stdout, stderr)


def notify_mqtt(config, report, error_logger=None):
    """Send one final report without altering cleanup's exit status on delivery failure."""
    if config is None:
        return
    success = report.get("status") == "success"
    if not should_send_notification(success, config["on_success"]):
        return
    if report.get("dry_run") and not config.get("send_on_dry_run", True):
        return
    try:
        # stdin keeps credentials and report content out of the process command line.
        # A worker gives even DNS/connect/acknowledgement stalls a firm timeout.
        if getattr(sys, "frozen", False):
            command = [sys.executable]
            worker_env = os.environ.copy()
            worker_env["CLEANUP_SYNCOID_INTERNAL_MQTT_WORKER"] = "1"
        else:
            command = [sys.executable, "-B", os.path.abspath(__file__), "--publish"]
            worker_env = None

        result = _run_publisher(
            command,
            input=json.dumps({"config": config, "report": report}),
            timeout=config["timeout"],
            env=worker_env,
        )
        if result.returncode:
            # Do not echo subprocess output: a library error might include credentials.
            raise RuntimeError("publisher failed; check paho-mqtt installation, broker, credentials and TLS settings")
    except Exception as exc:
        reason = "publisher timed out" if isinstance(exc, subprocess.TimeoutExpired) else (
            str(exc) if isinstance(exc, RuntimeError) else "could not start MQTT publisher"
        )
        message = f"MQTT notification failed: {reason}. Cleanup result is unchanged."
        if error_logger:
            error_logger.error(message)
        else:
            print(message, file=sys.stderr)


def publish_worker():
    """Publish non-retained MQTT 3.1.1 JSON using Paho in the timeout-isolated worker."""
    from paho.mqtt.publish import single

    request = json.load(sys.stdin)
    config = request["config"]
    auth = None
    if config["username"]:
        auth = {"username": config["username"], "password": config["password"]}
    context = None
    if config["tls"]:
        context = ssl.create_default_context(cafile=config["ca_certs"] or None)
        if config["certfile"]:
            context.load_cert_chain(config["certfile"], config["keyfile"])
    single(
        config["topic"],
        payload=json.dumps(request["report"], ensure_ascii=True),
        hostname=config["host"],
        port=config["port"],
        client_id=config["client_id"],
        qos=config["qos"],
        retain=False,
        auth=auth,
        tls=context,
    )


if __name__ == "__main__":
    if sys.argv[1:] != ["--publish"]:
        sys.exit("Internal MQTT worker. Use CleanUpInSyncoidSnapshots.py -c CONFIG instead.")
    try:
        publish_worker()
    except Exception:
        sys.exit(1)
