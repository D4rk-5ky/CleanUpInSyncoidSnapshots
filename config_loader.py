"""Load and validate the application's single TOML configuration file."""

import argparse
import datetime
from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:  # Python 3.10 compatibility.
    try:
        import tomli as tomllib
    except ModuleNotFoundError:  # pragma: no cover - depends on interpreter version.
        tomllib = None

from mqtt_notifications import validate_mqtt_config


TOP_LEVEL_SECTIONS = {"cleanup", "logging", "report", "mail", "mqtt"}
SECTION_KEYS = {
    "cleanup": {"command", "datasets_file", "syncoid_hosts_file", "older_than", "retain_count"},
    "logging": {"prefix"},
    "report": {"title", "comment"},
    "mail": {"enabled", "recipient", "on_success"},
    "mqtt": {
        "enabled",
        "host",
        "port",
        "topic",
        "username",
        "password",
        "client_id",
        "qos",
        "timeout",
        "tls",
        "ca_certs",
        "certfile",
        "keyfile",
        "publish_dry_run",
    },
}


def parse_older_than(value: str) -> datetime.timedelta:
    """Parse an age string such as 7d, 2w, or 3m using the original 30-day month rule."""
    import re

    if not isinstance(value, str):
        raise ValueError("cleanup.older_than must be a string such as '7d', '2w', or '3m'")
    match = re.fullmatch(r"(\d+)([dwm])", value.strip())
    if not match:
        raise ValueError("cleanup.older_than must use 'Nd', 'Nw', or 'Nm' (N=integer)")

    number = int(match.group(1))
    unit = match.group(2)
    if unit == "d":
        return datetime.timedelta(days=number)
    if unit == "w":
        return datetime.timedelta(weeks=number)
    return datetime.timedelta(days=number * 30)


def _table(document: dict, name: str, required: bool = False) -> dict:
    """Return one TOML table and reject wrong shapes before any cleanup can run."""
    if name not in document:
        if required:
            raise ValueError(f"Missing required [{name}] section")
        return {}
    value = document[name]
    if not isinstance(value, dict):
        raise ValueError(f"[{name}] must be a TOML table")
    unknown = set(value) - SECTION_KEYS[name]
    if unknown:
        raise ValueError(f"[{name}] contains unknown option(s): {', '.join(sorted(unknown))}")
    return value


def _required_string(table: dict, section: str, key: str) -> str:
    """Read a required nonempty string setting without silently coercing other TOML types."""
    value = table.get(key)
    if not isinstance(value, str) or not value.strip() or "\x00" in value:
        raise ValueError(f"{section}.{key} must be a nonempty string without NUL")
    return value.strip()


def _optional_string(table: dict, section: str, key: str, default: str = "") -> str:
    """Read an optional string setting while preserving intentional spaces inside its value."""
    value = table.get(key, default)
    if not isinstance(value, str) or "\x00" in value:
        raise ValueError(f"{section}.{key} must be a string without NUL")
    return value


def _boolean(table: dict, section: str, key: str, default: bool) -> bool:
    """Read a strict TOML boolean; integers are rejected even though bool subclasses int in Python."""
    value = table.get(key, default)
    if type(value) is not bool:
        raise ValueError(f"{section}.{key} must be true or false")
    return value


def _resolve_config_relative(config_dir: Path, value: str) -> str:
    """Resolve a configured filesystem path relative to the TOML file when it is not absolute."""
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = config_dir / path
    return str(path.resolve())


def load_config(path: str, default_log_prefix: str):
    """
    Load the single application TOML file and return a namespace compatible with
    the existing cleanup lifecycle. All validation happens before logging, mail,
    MQTT publishing, or ZFS commands are started.
    """
    if tomllib is None:
        raise RuntimeError(
            "Python 3.10 requires the 'tomli' package. Install requirements.txt first."
        )

    config_path = Path(path).expanduser().resolve()
    with config_path.open("rb") as stream:
        document = tomllib.load(stream)

    if not isinstance(document, dict):
        raise ValueError("Configuration root must be a TOML document")
    unknown_sections = set(document) - TOP_LEVEL_SECTIONS
    if unknown_sections:
        raise ValueError(
            "Configuration contains unknown top-level section(s): "
            + ", ".join(sorted(unknown_sections))
        )

    cleanup = _table(document, "cleanup", required=True)
    logging_cfg = _table(document, "logging")
    report = _table(document, "report")
    mail = _table(document, "mail")
    mqtt = _table(document, "mqtt")

    command = _required_string(cleanup, "cleanup", "command")
    if command not in {"delete", "dry-run"}:
        raise ValueError("cleanup.command must be either 'delete' or 'dry-run'")

    datasets_file = _resolve_config_relative(
        config_path.parent,
        _required_string(cleanup, "cleanup", "datasets_file"),
    )
    syncoid_hosts_file = _resolve_config_relative(
        config_path.parent,
        _required_string(cleanup, "cleanup", "syncoid_hosts_file"),
    )

    older_value = cleanup.get("older_than", "")
    if not isinstance(older_value, str):
        raise ValueError("cleanup.older_than must be a string")
    older_than = parse_older_than(older_value) if older_value.strip() else None

    retain_count = cleanup.get("retain_count", 0)
    if type(retain_count) is not int:
        raise ValueError("cleanup.retain_count must be an integer")
    # Preserve the old CLI behavior where negative values were normalized to zero.
    retain_count = max(retain_count, 0)

    log_prefix = _optional_string(logging_cfg, "logging", "prefix", default_log_prefix)
    if not log_prefix:
        log_prefix = default_log_prefix

    backup_title = _optional_string(report, "report", "title", "")
    backup_comment = _optional_string(report, "report", "comment", "")

    mail_enabled = _boolean(mail, "mail", "enabled", False)
    mail_recipient = _optional_string(mail, "mail", "recipient", "")
    mail_on_success = _boolean(mail, "mail", "on_success", False)
    if mail_enabled and not mail_recipient.strip():
        raise ValueError("mail.recipient must be a nonempty string when mail.enabled=true")
    send_mail = mail_recipient.strip() if mail_enabled else None

    mqtt_enabled = _boolean(mqtt, "mqtt", "enabled", False)
    mqtt_config = None
    if mqtt_enabled:
        supplied = dict(mqtt)
        supplied.pop("enabled", None)
        mqtt_config = validate_mqtt_config(supplied, config_path.parent)

    return argparse.Namespace(
        command=command,
        datasets_file=datasets_file,
        syncoid_hosts_file=syncoid_hosts_file,
        older_than=older_than,
        retain_count=retain_count,
        log_prefix=log_prefix,
        send_mail=send_mail,
        mail_on_success=mail_on_success,
        backup_title=backup_title,
        backup_comment=backup_comment,
        mqtt_config=mqtt_config,
        config_file=str(config_path),
        dry_run=(command == "dry-run"),
    )
