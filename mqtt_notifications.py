"""Optional, bounded MQTT status delivery; no snapshot operations live here."""

import datetime
import json
import math
import os
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
    "publish_dry_run": False,
}


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
    for key in ("tls", "publish_dry_run"):
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


def build_mqtt_report(args, version, exit_code, error=None, warning=False):
    """Use the Home Assistant automation's exact status names and JSON types."""
    return {
        "status": "success" if exit_code == 0 else "failure",
        "title": args.backup_title.strip() or "CleanUpInSyncoidSnapshots",
        "name": "CleanUpInSyncoidSnapshots",
        "job": args.log_prefix,
        "exit_code": exit_code,
        "warning": bool(warning),
        "error": str(error) if error is not None else "",
        "stderr": (getattr(error, "stderr", "") or getattr(error, "stdout", "") or "")[-4096:],
        "command": args.command,
        "dry_run": args.command == "dry-run",
        "comment": args.backup_comment,
        "version": version,
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    }


def notify_mqtt(config, report, error_logger=None, logger=None):
    """Send one final report without altering cleanup's exit status on delivery failure.

    Return ``True`` only when the isolated publisher exits successfully. This lets
    callers/tests distinguish an attempted-and-confirmed publish from a logged
    delivery failure without changing the cleanup exit code.
    """
    if config is None:
        return False
    # publish_dry_run controls routine successful previews only. A failed dry-run
    # must still report failure when MQTT is enabled, otherwise exactly the runs
    # that need attention can disappear silently.
    if (
        report["dry_run"]
        and not config["publish_dry_run"]
        and report.get("status") != "failure"
    ):
        return False
    try:
        # stdin keeps credentials and report content out of the process command line.
        # A worker gives even DNS/connect/acknowledgement stalls a firm timeout.
        result = subprocess.run(
            [sys.executable, "-B", os.path.abspath(__file__), "--publish"],
            input=json.dumps({"config": config, "report": report}),
            text=True,
            encoding="utf-8",
            capture_output=True,
            timeout=config["timeout"],
            check=False,
        )
        if result.returncode:
            # Do not echo subprocess output: a library error might include credentials.
            raise RuntimeError("publisher failed; check paho-mqtt installation, broker, credentials and TLS settings")
        if logger:
            logger.info("MQTT report sent successfully")
        return True
    except Exception as exc:
        reason = "publisher timed out" if isinstance(exc, subprocess.TimeoutExpired) else (
            str(exc) if isinstance(exc, RuntimeError) else "could not start MQTT publisher"
        )
        message = f"MQTT notification failed: {reason}. Cleanup result is unchanged."
        if error_logger:
            error_logger.error(message)
        else:
            print(message, file=sys.stderr)
        return False


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
