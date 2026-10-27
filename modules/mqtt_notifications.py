"""Cleanup adapters for the independent Syncerate completion and HA live modules."""
from dataclasses import asdict
import json
from pathlib import Path
import ssl
import subprocess
import sys

from .mqtt_status import MQTTConfig, build_report, publish_report, _publish_once

# Preserve omitted values in legacy [mqtt] configurations. New [completion]
# configurations use MQTTConfig's template defaults (qos=0, on_success=true).
DEFAULTS = {
    "port": 1883, "username": None, "password": None, "client_id": "",
    "qos": 1, "timeout": 15, "tls": False, "ca_certs": None,
    "certfile": None, "keyfile": None, "on_success": False,
    "send_on_dry_run": True,
}


def should_send_notification(success: bool, on_success: bool) -> bool:
    return (not success) or on_success


def resolve_certificates(supplied, base_dir, section):
    """Resolve template TLS paths relative to the application config file."""
    config = dict(supplied)
    for key in ("username", "password", "ca_certs", "certfile", "keyfile"):
        if config.get(key) == "":
            config[key] = None
    for key in ("ca_certs", "certfile", "keyfile"):
        value = config.get(key)
        if value:
            if not isinstance(value, str):
                raise ValueError(f"{section}.{key} must be a string or null")
            certificate = Path(value).expanduser()
            if not certificate.is_absolute():
                certificate = Path(base_dir) / certificate
            certificate = certificate.resolve()
            if not certificate.is_file():
                raise ValueError(f"{section}.{key} file does not exist")
            config[key] = str(certificate)
    return config


def validate_mqtt_config(supplied, base_dir):
    """Compatibility adapter for the original [mqtt] table."""
    if not isinstance(supplied, dict):
        raise ValueError("[mqtt] settings must be an object/table")
    if set(supplied) - (set(DEFAULTS) | {"host", "topic"}):
        raise ValueError("[mqtt] contains unknown options")
    if not supplied.get("host") or not supplied.get("topic"):
        raise ValueError("mqtt.host and mqtt.topic are required when enabled")
    values = resolve_certificates(dict(DEFAULTS, **supplied), base_dir, "mqtt")
    return {key: value for key, value in asdict(MQTTConfig(enabled=True, **values)).items()
            if key != "enabled"}


def build_mqtt_report(args, version, exit_code, error=None, warning=False,
                      dry_run_report=None, *, run_id=None, stderr_text=None,
                      planned_datasets=None, failed_datasets=None, skipped_datasets=None):
    """Keep cleanup diagnostics while using the template's complete JSON contract."""
    if stderr_text is None:
        stderr_text = getattr(error, "stderr", "") or getattr(error, "stdout", "") or ""
    return build_report(
        name="CleanUpInSyncoidSnapshots", job=args.log_prefix,
        title=args.backup_title.strip() or "CleanUpInSyncoidSnapshots",
        exit_code=exit_code, error_message=str(error) if error is not None else "",
        stderr_text=stderr_text, warning=bool(warning), dry_run=args.command == "dry-run",
        command=args.command, comment=args.backup_comment, version=version,
        run_id=run_id, planned_datasets=planned_datasets,
        failed_datasets=failed_datasets, skipped_datasets=skipped_datasets,
        extra={"dry_run_report": dry_run_report} if dry_run_report is not None else None,
    )


def notify_mqtt(config, report, error_logger=None):
    """Best-effort completion only. Live preview has its own config and lifecycle."""
    if config is None:
        return
    try:
        result = publish_report(MQTTConfig(**dict({"enabled": True}, **config)), report)
    except Exception:
        message = "MQTT notification failed: invalid completion configuration. Cleanup result is unchanged."
    else:
        if result.status != "failed":
            return result
        message = f"MQTT notification failed: {result.reason}. Cleanup result is unchanged."
    if error_logger:
        error_logger.error(message)
    else:
        print(message, file=sys.stderr)


def publish_worker():
    """Accept the historical frozen-worker marker for compatibility."""
    request = json.load(sys.stdin)
    _publish_once(MQTTConfig(**dict({"enabled": True}, **request["config"])), request["report"])
