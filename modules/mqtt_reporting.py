"""CleanUpInSyncoidSnapshots completion and independent HA live reporting.

Run from project root: sudo python3 CleanUpInSyncoidSnapshots.py -c configs/config.toml.
Shared imports use the modules package; config inputs stay beside the TOML in configs/.

Usage (no extra JSON/state/cache/log files): configure the existing TOML [mqtt]
section; run the same app -c/--config command. MQTT_JSON_Status enables final
non-retained JSON; SendMQTTOnSuccess opts into successful completions. Failures
still report. LiveMQTTEnabled independently enables live state/discovery.
LiveNotify* controls live events only, never completion/Pushover or retained
last_result. LiveMQTTOnDryRun defaults false; previews never replace last_result.

configs/config.toml and configs/config-example.toml describe every option and legacy aliases. Keep
mqtt_json_topic at your existing completion topic. Import examples/success-failure-automation.yaml manually and replace notify.pushover with your HA action; avoid
duplicate notification automations. Dry-runs and inconsistent completion reports
are stopped before any action. This project defines no job-sequencing actions.
Paste examples/live-preview-card.yaml as a Markdown card and match its manufacturer value
to LiveManufacturer. Device IDs derive from host + stable job + config path;
optional LiveDeviceID can pin an identity (must remain unique per host/job).
Renaming sensors is supported by live_preview_role attributes.

Live job_type is syncoid_snapshot_cleanup. Main progress uses item_unit=datasets:
total is the number of nonempty entries read from datasets_file, completed counts
finished dataset attempts (success OR checked failure), and current_dataset_index
is the one-based position currently being processed. A five-entry file therefore
has max 5 from the start: after two attempts, progress is 2 / 5 (40%). Interrupts
leave the current entry unfinished. Failed listings do not erase the known total.
Blank lines are ignored as before; repeated entries count in their file order.
Outcome arrays remain snapshots, identified by outcome_item_unit=snapshots;
retained/too-new/invalid/dry-run snapshots are skipped outcomes. Snapshot outcomes
never advance dataset progress. Before the input file is read, total stays null.
No bytes or transfer rate are measured by this cleanup job: both remain null.
Dataset-level failures are optional completion extensions, never generic fields.

The app binds RunReporting around run_cleanup and captures real ZFS/mail stderr.
Network workers are bounded, killable process groups; broker errors never replace
job exit codes. Loss of heartbeat means unknown outcome, not inferred success.
All live state is memory-only; only broker discovery/last_result are retained.
"""
from __future__ import annotations
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from contextvars import ContextVar
import hashlib
import json
import math
import os
from pathlib import Path
import re
import signal
import socket
import ssl
import subprocess
import sys
from threading import Event, Lock, Thread
import time
from typing import Any, Mapping, Sequence
import uuid

__version__ = "0.0.20"
WORKER_FLAG = "--ha-live-preview-worker"
STDERR_LIMIT = 4000

def _text(value: Any, label: str, *, nonempty: bool = False) -> str:
    if not isinstance(value, str) or (nonempty and not value.strip()):
        raise ValueError(f"{label} must be a {'nonempty ' if nonempty else ''}string")
    return value

def _json_text(value: Any) -> str:
    """Require real JSON types, finite numbers, string keys and valid UTF-8."""
    def check(item: Any) -> None:
        if isinstance(item, dict):
            for key, child in item.items():
                if not isinstance(key, str):
                    raise ValueError("JSON object keys must be strings")
                check(child)
        elif isinstance(item, list):
            for child in item:
                check(child)
        elif item is not None and type(item) not in (str, int, float, bool):
            raise ValueError("Report contains an unsupported JSON value")
    check(value)
    encoded = json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(",", ":"))
    encoded.encode("utf-8")
    return encoded

def _dataset_list(values: Sequence[Mapping[str, Any]] | None) -> list[dict[str, Any]]:
    if values is None:
        return []
    if isinstance(values, (str, bytes, dict)):
        raise ValueError("Dataset details must be a sequence of objects")
    result = []
    for item in values:
        if not isinstance(item, Mapping):
            raise ValueError("Each dataset detail must be an object")
        result.append(dict(item))
    return result

def build_report(
    *,
    name: str,
    job: str,
    exit_code: int,
    title: str | None = None,
    error_message: str | None = "",
    stderr_text: str | bytes | None = "",
    warning: bool = False,
    dry_run: bool = False,
    command: str = "",
    comment: str = "",
    version: str = "",
    run_id: str | None = None,
    skipped_datasets: Sequence[Mapping[str, Any]] | None = None,
    failed_datasets: Sequence[Mapping[str, Any]] | None = None,
    planned_datasets: Sequence[Mapping[str, Any]] | None = None,
    extra: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a detached JSON-compatible dictionary.

    exit_code is the authoritative *reported job result*: 0 means success,
    every other integer means failure (negative signal codes are allowed).
    Callers map their actual job semantics to that code; this function cannot
    verify backups or container updates. Warnings do not change the outcome.
    Extra top-level fields preserve project details but cannot replace core fields.
    """
    if type(exit_code) is not int:
        raise ValueError("exit_code must be an integer, not a boolean/string")
    if type(warning) is not bool or type(dry_run) is not bool:
        raise ValueError("warning and dry_run must be JSON booleans")
    if isinstance(stderr_text, bytes):
        stderr_text = stderr_text.decode("utf-8", errors="replace")
    success = exit_code == 0
    report = {
        "status": "success" if success else "failure",
        "success": success,
        "title": _text(title if title is not None else name, "title", nonempty=True),
        "name": _text(name, "name", nonempty=True),
        "job": _text(job, "job", nonempty=True),
        "dry_run": dry_run,
        "exit_code": exit_code,
        "error": _text(error_message if error_message is not None else "", "error_message"),
        "stderr": _text(stderr_text if stderr_text is not None else "", "stderr_text")[-STDERR_LIMIT:],
        "warning": warning,
        "schema_version": 1,
        "command": _text(command, "command"),
        "comment": _text(comment, "comment"),
        "version": _text(version, "version"),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "host": socket.gethostname(),
        "run_id": _text(run_id if run_id is not None else str(uuid.uuid4()), "run_id", nonempty=True),
    }
    # Dataset diagnostics belong to adapters such as Syncerate, not the generic
    # completion contract. Omitted means absent; an explicit [] is preserved.
    for key, values in (("planned_datasets", planned_datasets),
                        ("skipped_datasets", skipped_datasets),
                        ("failed_datasets", failed_datasets)):
        if values is not None:
            report[key] = _dataset_list(values)
    if extra is not None:
        if not isinstance(extra, Mapping):
            raise ValueError("extra must be an object")
        if set(extra).intersection(report):
            raise ValueError("extra cannot replace standard report fields")
        report.update(extra)
    # Round-trip also detaches nested objects supplied by the caller.
    return json.loads(encode_report(report))

def encode_report(report: Mapping[str, Any]) -> str:
    """Validate and serialize a template report as compact UTF-8 JSON.

    This validates this module's contract, not every historical Syncerate payload.
    Build legacy adapters through build_report rather than publishing unchecked JSON.
    """
    if not isinstance(report, Mapping):
        raise ValueError("report must be an object")
    report = dict(report)
    for key in ("title", "name", "job", "error", "stderr", "command", "comment",
                "version", "timestamp", "host", "run_id"):
        _text(report.get(key), key, nonempty=key in ("title", "name", "job", "run_id"))
    code = report.get("exit_code")
    if type(code) is not int:
        raise ValueError("exit_code must be an integer")
    for key in ("success", "warning", "dry_run"):
        if type(report.get(key)) is not bool:
            raise ValueError(f"{key} must be a JSON boolean")
    success = code == 0
    if report["success"] != success or report.get("status") != ("success" if success else "failure"):
        raise ValueError("status, success and exit_code must agree")
    if type(report.get("schema_version")) is not int or report["schema_version"] != 1:
        raise ValueError("schema_version must be 1")
    for key in ("planned_datasets", "skipped_datasets", "failed_datasets"):
        if key in report and (not isinstance(report[key], list) or any(not isinstance(x, dict) for x in report[key])):
            raise ValueError(f"{key} must be an array of objects")
    return _json_text(report)

_json = _json_text

def _now() -> str:
    return datetime.now(timezone.utc).isoformat()

def make_device_id(job: str, config_key: str, host: str | None = None) -> str:
    """Stable per-host/per-config identity. config_key should not contain secrets."""
    for value in (job, config_key):
        if not isinstance(value, str) or not value.strip():
            raise ValueError("job and config_key must be nonempty strings")
    label = re.sub(r"[^a-z0-9_]+", "_", job.lower()).strip("_")[:32] or "job"
    digest = hashlib.sha256(_json([host if host is not None else socket.gethostname(), job, config_key]).encode()).hexdigest()[:12]
    return f"{label}_{digest}"

@dataclass(frozen=True)
class LiveConfig:
    enabled: bool = False
    host: str = ""
    port: int = 1883
    username: str | None = None
    password: str | None = field(default=None, repr=False)
    client_id: str = ""
    qos: int = 1
    timeout: float = 5.0
    tls: bool = False
    ca_certs: str | None = None
    certfile: str | None = None
    keyfile: str | None = None
    device_id: str = "cleanup_syncoid_snapshots"
    manufacturer: str = "CleanUpInSyncoidSnapshots"
    backup_name: str = ""
    topic_prefix: str = "job-live"
    discovery: bool = True
    send_on_dry_run: bool = False
    discovery_prefix: str = "homeassistant"
    heartbeat_seconds: float = 10.0
    min_publish_interval: float = 1.0
    expire_after: int = 45
    discovery_interval: float = 300.0
    final_wait: float = 1.0
    notify_start: bool = False
    notify_success: bool = True
    notify_failure: bool = True

    @classmethod
    def from_mapping(cls, mqtt: dict[str, Any], *, job: str, config_key: str,
                     base_dir: str | Path = ".") -> LiveConfig:
        """Adapt the same parsed [mqtt] table used by completion notifications."""
        if not isinstance(mqtt, dict):
            raise ValueError("[mqtt] must be a mapping")
        heartbeat = mqtt.get("LiveHeartbeatSeconds", 10)
        timeout = mqtt.get("LivePublishTimeoutSeconds", 5)
        for value in (heartbeat, timeout):
            if type(value) not in (int, float) or not math.isfinite(value) or value <= 0:
                raise ValueError("Live heartbeat and publish timeout must be finite positive numbers")
        expiry = max(math.ceil(3 * heartbeat), math.ceil(2 * heartbeat + timeout + 1))
        def certificate(key: str) -> str | None:
            value = mqtt.get(key)
            if value in (None, ""):
                return None
            if not isinstance(value, str):
                raise ValueError(f"{key} must be text")
            return str((Path(base_dir) / Path(value).expanduser()).resolve())
        return cls(
            enabled=mqtt.get("LiveMQTTEnabled", False),
            host=mqtt.get("broker_address", ""), port=mqtt.get("broker_port", 1883),
            username=mqtt.get("mqtt_username"), password=mqtt.get("mqtt_password"),
            client_id=mqtt.get("LiveClientID", ""), qos=mqtt.get("LiveMQTTQoS", 1), timeout=timeout,
            tls=mqtt.get("MQTTTLS", False), ca_certs=certificate("MQTTCAFile"),
            certfile=certificate("MQTTCertFile"), keyfile=certificate("MQTTKeyFile"),
            device_id=mqtt.get("LiveDeviceID", make_device_id(job, config_key)),
            manufacturer=mqtt.get("LiveManufacturer", "CleanUpInSyncoidSnapshots"),
            backup_name=mqtt.get("LiveBackupName", ""),
            topic_prefix=mqtt.get("LiveTopicPrefix", "job-live"),
            discovery=mqtt.get("LiveMQTTDiscovery", True),
            discovery_prefix=mqtt.get("LiveDiscoveryPrefix", "homeassistant"),
            send_on_dry_run=mqtt.get("LiveMQTTOnDryRun", False),
            heartbeat_seconds=heartbeat, expire_after=mqtt.get("LiveExpireAfterSeconds", expiry),
            min_publish_interval=mqtt.get("LiveMinPublishIntervalSeconds", 1),
            discovery_interval=mqtt.get("LiveDiscoveryIntervalSeconds", 300),
            final_wait=mqtt.get("LiveFinalWaitSeconds", 1),
            notify_start=mqtt.get("LiveNotifyStart", False),
            notify_success=mqtt.get("LiveNotifySuccess", True),
            notify_failure=mqtt.get("LiveNotifyFailure", True),
        )

    def __post_init__(self) -> None:
        for key in ("enabled", "tls", "discovery", "send_on_dry_run", "notify_start", "notify_success", "notify_failure"):
            if type(getattr(self, key)) is not bool:
                raise ValueError(f"{key} must be a boolean")
        if not isinstance(self.host, str) or (self.enabled and not self.host.strip()) or "://" in self.host or "\x00" in self.host or self.host != self.host.strip():
            raise ValueError("host must be a hostname/IP without a scheme or surrounding whitespace")
        if type(self.port) is not int or not 1 <= self.port <= 65535:
            raise ValueError("port must be an integer from 1 to 65535")
        if type(self.qos) is not int or self.qos not in (0, 1, 2):
            raise ValueError("qos must be 0, 1 or 2")
        if not isinstance(self.device_id, str) or not re.fullmatch(r"[a-z0-9_]{1,80}", self.device_id):
            raise ValueError("device_id must contain 1-80 lowercase letters, digits or underscores")
        if not isinstance(self.manufacturer, str) or not self.manufacturer.strip() or self.manufacturer != self.manufacturer.strip() or "\x00" in self.manufacturer:
            raise ValueError("manufacturer must be nonempty text without NUL or surrounding whitespace")
        if not isinstance(self.backup_name, str):
            raise ValueError("backup_name must be a string")
        for key in ("topic_prefix", "discovery_prefix"):
            value = getattr(self, key)
            if not isinstance(value, str) or not value.strip("/").strip() or any(c in value for c in "+#\x00") or len(value.encode()) > 65000:
                raise ValueError(f"{key} must be a nonempty MQTT topic prefix without wildcards")
        for key in ("timeout", "heartbeat_seconds", "min_publish_interval", "discovery_interval", "final_wait"):
            value = getattr(self, key)
            if type(value) not in (int, float) or not math.isfinite(value) or value <= 0:
                raise ValueError(f"{key} must be finite and greater than zero")
        if self.min_publish_interval > self.heartbeat_seconds:
            raise ValueError("min_publish_interval cannot exceed heartbeat_seconds")
        if type(self.expire_after) is not int or self.expire_after <= 2 * self.heartbeat_seconds + self.timeout:
            raise ValueError("expire_after must exceed two heartbeats plus the publish timeout")
        for key in ("username", "password", "ca_certs", "certfile", "keyfile"):
            if getattr(self, key) is not None and not isinstance(getattr(self, key), str):
                raise ValueError(f"{key} must be a string or null")
        if not isinstance(self.client_id, str):
            raise ValueError("client_id must be a string")
        if self.password and not self.username:
            raise ValueError("password requires username")
        if bool(self.certfile) != bool(self.keyfile):
            raise ValueError("certfile and keyfile must be provided together")
        if any((self.ca_certs, self.certfile, self.keyfile)) and not self.tls:
            raise ValueError("certificate options require tls=true")

    @property
    def state_topic(self) -> str:
        return f"{self.topic_prefix.rstrip('/')}/{self.device_id}/state"

    @property
    def result_topic(self) -> str:
        return f"{self.topic_prefix.rstrip('/')}/{self.device_id}/last_result"

    @property
    def events_topic(self) -> str:
        return f"{self.topic_prefix.rstrip('/')}/{self.device_id}/events"


def discovery_messages(config: LiveConfig, name: str, version: str = "") -> list[dict[str, Any]]:
    """Retained single-component discovery; state is intentionally non-retained."""
    if not config.discovery:
        return []
    fields = [
        ("status", "Status", None), ("progress_percent", "Progress", "%"),
        ("completed", "Completed items", None), ("total", "Total items", None),
        ("current_item", "Current item", None), ("phase", "Phase", None),
        ("runtime_seconds", "Runtime", "s"), ("transferred_bytes", "Transferred", "B"),
        ("bytes_per_second", "Transfer speed", "B/s"),
        ("last_heartbeat", "Last heartbeat", None), ("last_result", "Last result", None),
        ("successful_item_count", "Successful items", None),
        ("failed_item_count", "Failed items", None),
        ("skipped_item_count", "Skipped items", None),
    ]
    messages = []
    for key, label, unit in fields:
        result = key == "last_result"
        field_name = "status" if result else key
        identifier = f"job_live_{config.device_id}_{key}"
        payload = {
            "name": label, "unique_id": identifier,
            "default_entity_id": f"sensor.{identifier}",
            "device": {"identifiers": [f"job_live_{config.device_id}"], "name": name,
                       "manufacturer": config.manufacturer, "model": "Live job preview",
                       "sw_version": version or __version__},
            "origin": {"name": "mqtt_reporting", "sw_version": __version__},
            "state_topic": config.result_topic if result else config.state_topic,
            "value_template": "{{ value_json." + field_name + " if value_json." + field_name + " is not none else none }}",
            "qos": config.qos,
        }
        if not result:
            payload["expire_after"] = config.expire_after
        if unit:
            payload["unit_of_measurement"] = unit
        if key in ("completed", "total", "progress_percent", "runtime_seconds", "transferred_bytes", "bytes_per_second",
                   "successful_item_count", "failed_item_count", "skipped_item_count"):
            payload["state_class"] = "measurement"
        if key == "last_heartbeat":
            payload["device_class"] = "timestamp"
        if key in ("current_item", "phase"):
            payload["value_template"] = "{{ value_json." + key + "[:255] }}"
        if result:
            payload["json_attributes_topic"] = config.result_topic
            payload["json_attributes_template"] = '{{ dict(value_json, live_preview_role="last_result") | tojson }}'
        elif key == "status":
            payload["json_attributes_topic"] = config.state_topic
            payload["json_attributes_template"] = '{{ dict(value_json, live_preview_role="status") | tojson }}'
        messages.append({"topic": f"{config.discovery_prefix.rstrip('/')}/sensor/{identifier}/config",
                         "payload": payload, "retain": True, "qos": config.qos})
    return messages

class LivePreview:
    """One run per instance. Caller owns the real job lock and progress counters.

    start/update/append_stderr only update memory or launch a daemon; never do
    network I/O on the job thread. finish has a bounded best-effort final drain.
    """

    def __init__(self, config: LiveConfig, *, job: str, name: str | None = None, version: str = "",
                 run_id: str | None = None, dry_run: bool = False,
                 job_type: str = "task", item_unit: str = "tasks",
                 outcome_item_unit: str | None = None):
        name = name if name is not None else (config.backup_name or job)
        outcome_item_unit = item_unit if outcome_item_unit is None else outcome_item_unit
        for value in (name, job, job_type, item_unit, outcome_item_unit):
            if not isinstance(value, str) or not value.strip():
                raise ValueError("name and job must be nonempty strings")
        if not isinstance(version, str) or type(dry_run) is not bool:
            raise ValueError("version must be a string and dry_run a boolean")
        if run_id is not None and (not isinstance(run_id, str) or not run_id.strip()):
            raise ValueError("run_id must be a nonempty string")
        self.config, self.name, self.job, self.version = config, name, job, version
        self.run_id, self.dry_run = run_id or str(uuid.uuid4()), dry_run
        self.job_type, self.item_unit = job_type, item_unit
        self.outcome_item_unit = outcome_item_unit
        self._lock, self._process_lock = Lock(), Lock()
        self._wake, self._stop = Event(), Event()
        self._thread: Thread | None = None
        self._process: subprocess.Popen | None = None
        self._started = self._finished = False
        self._dirty = True
        self._start_time = time.monotonic()
        self._end_time: float | None = None
        self._started_at = _now()
        self._result: dict[str, Any] | None = None
        self._events: list[dict[str, Any]] = []
        self._delivery = "not_started"
        self._state = {"status": "idle", "success": None, "exit_code": None,
                       "phase": "waiting", "current_item": "", "completed": None, "total": None,
                       "progress_percent": None, "transferred_bytes": None, "bytes_per_second": None,
                       "successful_items": [], "failed_items": [], "skipped_items": [],
                       "successful_item_count": 0, "failed_item_count": 0, "skipped_item_count": 0,
                       "stderr": "", "error": "", "warning": False, "message": "", "details": {}, "finished_at": None}

    def _snapshot_locked(self) -> dict[str, Any]:
        return json.loads(_json({"schema_version": 1, "job_type": self.job_type, "item_unit": self.item_unit, "outcome_item_unit": self.outcome_item_unit, "name": self.name, "title": self.name, "job": self.job,
                "device_id": self.config.device_id, "run_id": self.run_id,
                "manufacturer": self.config.manufacturer,
                "host": socket.gethostname(), "version": self.version, "dry_run": self.dry_run,
                "started_at": self._started_at, "last_heartbeat": _now(),
                "runtime_seconds": round(max(0, (self._end_time if self._end_time is not None else time.monotonic()) - self._start_time), 2),
                **self._state}))

    def snapshot(self) -> dict[str, Any]:
        """Local snapshot, not proof of delivery. Unknown measurements stay null."""
        with self._lock:
            return self._snapshot_locked()

    @property
    def last_delivery(self) -> str:
        with self._lock:
            return self._delivery

    def start(self) -> bool:
        with self._lock:
            if self._started or self._finished or self._stop.is_set():
                return False
            self._started = True
            self._start_time, self._started_at = time.monotonic(), _now()
            self._state.update(status="running", phase="starting")
            if not self.config.enabled or (self.dry_run and not self.config.send_on_dry_run):
                return False
            if self.config.notify_start:
                self._events.append({**self._snapshot_locked(), "event": "started", "timestamp": _now()})
            self._thread = Thread(target=self._worker, daemon=True, name=f"ha-live-{self.config.device_id}")
        try:
            self._thread.start()
            return True
        except Exception:
            with self._lock:
                self._delivery = "failed"
            return False

    def update(self, **values: Any) -> bool:
        """Local coalesced update. Counters refer to items with one caller-defined unit."""
        allowed = {"phase", "current_item", "completed", "total", "transferred_bytes",
                   "bytes_per_second", "stderr", "message", "successful_items",
                   "failed_items", "skipped_items", "details"}
        if set(values) - allowed:
            raise ValueError("Unsupported progress field")
        for key, value in values.items():
            if key == "details":
                if not isinstance(value, dict):
                    raise ValueError("details must be an object")
            elif key.endswith("_items"):
                if not isinstance(value, list) or any(not isinstance(row, dict) for row in value):
                    raise ValueError(f"{key} must be an array of objects")
            elif key in ("phase", "current_item", "stderr", "message"):
                if not isinstance(value, str):
                    raise ValueError(f"{key} must be a string")
            elif value is not None:
                if key == "bytes_per_second":
                    if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
                        raise ValueError("bytes_per_second must be a finite nonnegative number or null")
                elif type(value) is not int or value < 0:
                    raise ValueError(f"{key} must be a nonnegative integer or null")
        if "stderr" in values:
            values["stderr"] = values["stderr"][-4000:]
        values = json.loads(_json(values))
        with self._lock:
            if self._finished:
                return False
            merged = {**self._state, **values}
            done, total = merged["completed"], merged["total"]
            if done is not None and total is not None and done > total:
                raise ValueError("completed cannot exceed total")
            merged["progress_percent"] = round(100 * done / total, 2) if done is not None and total else None
            for outcome in ("successful", "failed", "skipped"):
                merged[outcome + "_item_count"] = len(merged[outcome + "_items"])
            self._state, self._dirty = merged, True
        self._wake.set()
        return True

    def record_item(self, outcome: str, *, name: str, reason: str = "", **details: Any) -> bool:
        """Record the latest item outcome by name, independent of progress counters."""
        groups = {"success": "successful_items", "failure": "failed_items", "skipped": "skipped_items"}
        if outcome not in groups:
            raise ValueError("item outcome must be success, failure or skipped")
        if not isinstance(name, str) or not name.strip() or not isinstance(reason, str):
            raise ValueError("name must be nonempty text and reason a string")
        row = {**details, "name": name, "reason": reason}
        _json(row)
        with self._lock:
            if self._finished:
                return False
            for group in groups.values():
                self._state[group] = [item for item in self._state[group]
                                      if item.get("name") != name]
            self._state[groups[outcome]].append(row)
            for label in ("successful", "failed", "skipped"):
                self._state[label + "_item_count"] = len(self._state[label + "_items"])
            self._dirty = True
        self._wake.set()
        return True

    def append_stderr(self, output: str | bytes) -> bool:
        if isinstance(output, bytes):
            output = output.decode("utf-8", errors="replace")
        if not isinstance(output, str):
            raise ValueError("stderr output must be text or bytes")
        with self._lock:
            if self._finished:
                return False
            self._state["stderr"] = (self._state["stderr"] + output)[-4000:]
            self._dirty = True
        self._wake.set()
        return True

    def finish(self, exit_code: int, *, error: str = "", stderr: str | None = None,
               warning: bool = False, interrupted: bool = False, incomplete: bool = False) -> bool:
        if type(exit_code) is not int or not isinstance(error, str):
            raise ValueError("exit_code must be an integer and error a string")
        if any(type(x) is not bool for x in (warning, interrupted, incomplete)):
            raise ValueError("terminal flags must be booleans")
        if interrupted and (exit_code == 0 or incomplete):
            raise ValueError("interrupted requires a nonzero code and cannot also be incomplete")
        if stderr is not None and not isinstance(stderr, str):
            raise ValueError("stderr must be a string or null")
        with self._lock:
            if self._finished:
                return False
            done, total = self._state["completed"], self._state["total"]
            remaining = (done is not None and total is not None and done < total) or bool(self._state["failed_items"])
            status = ("interrupted" if interrupted else "failure" if exit_code != 0 else
                      "incomplete" if incomplete or remaining else "success")
            self._end_time = time.monotonic()
            self._state.update(status=status, success=status == "success", exit_code=exit_code,
                               error=error, warning=warning, phase="finished", finished_at=_now())
            if stderr is not None:
                self._state["stderr"] = stderr[-4000:]
            self._finished = self._dirty = True
            self._result = self._snapshot_locked()
            if ((status == "success" and self.config.notify_success)
                    or (status != "success" and self.config.notify_failure)):
                self._events.append({**self._result, "event": "completed" if status == "success" else "failed", "timestamp": _now()})
        self._wake.set()
        if self._thread is not None and self._thread.is_alive():
            self._thread.join(timeout=self.config.final_wait)
            if self._thread.is_alive():
                self._cancel()
        return True

    def _cancel(self) -> None:
        self._stop.set()
        self._wake.set()
        with self._process_lock:
            if self._process is not None:
                try:
                    os.killpg(self._process.pid, signal.SIGKILL)
                except OSError:
                    pass

    def close(self) -> None:
        """Stop without inventing an outcome; a previously running sensor expires."""
        self._cancel()
        if self._thread is not None and self._thread.is_alive():
            self._thread.join(timeout=self.config.final_wait)

    def _send(self, messages: list[dict[str, Any]]) -> bool:
        request = _json({"config": asdict(self.config), "messages": messages})
        command = ([sys.executable, WORKER_FLAG] if getattr(sys, "frozen", False) else
                   [sys.executable, "-B", str(Path(__file__).resolve()), WORKER_FLAG])
        process = None
        try:
            with self._process_lock:
                if self._stop.is_set():
                    return False
                process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL,
                                           stderr=subprocess.DEVNULL, text=True, encoding="utf-8",
                                           start_new_session=True)
                self._process = process
            process.communicate(input=request, timeout=self.config.timeout)
            return process.returncode == 0
        except Exception:
            if process is not None:
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                    process.communicate(timeout=1)
                except (OSError, subprocess.TimeoutExpired):
                    pass
            return False
        finally:
            with self._process_lock:
                if self._process is process:
                    self._process = None

    def _worker(self) -> None:
        next_allowed = heartbeat_due = discovery_due = 0.0
        try:
            while not self._stop.is_set():
                with self._lock:
                    dirty, finished = self._dirty, self._finished
                due = 0 if finished else next_allowed if dirty else heartbeat_due
                delay = max(0, due - time.monotonic())
                if delay:
                    self._wake.wait(timeout=delay)
                    self._wake.clear()
                    continue
                with self._lock:
                    self._dirty = False
                    finished, result = self._finished, self._result
                    state = self._snapshot_locked()
                    events, self._events = self._events, []
                messages = []
                now = time.monotonic()
                include_discovery = self.config.discovery and now >= discovery_due
                if include_discovery:
                    messages.extend(discovery_messages(self.config, self.name, self.version))
                messages.append({"topic": self.config.state_topic, "payload": state,
                                 "qos": self.config.qos, "retain": False})
                if result is not None and not self.dry_run:
                    messages.append({"topic": self.config.result_topic, "payload": result,
                                     "qos": self.config.qos, "retain": True})
                messages.extend({"topic": self.config.events_topic, "payload": event,
                                 "qos": self.config.qos, "retain": False} for event in events)
                ok = self._send(messages)
                with self._lock:
                    self._delivery = "sent" if ok else "failed"
                if ok and include_discovery:
                    discovery_due = time.monotonic() + self.config.discovery_interval
                if finished:
                    return
                next_allowed = time.monotonic() + self.config.min_publish_interval
                heartbeat_due = time.monotonic() + self.config.heartbeat_seconds
        except Exception:
            with self._lock:
                self._delivery = "failed"

def run_worker_if_requested() -> bool:
    """Handle only the private live worker before the public application parser."""
    if sys.argv[1:] != [WORKER_FLAG]:
        return False
    try:
        request = json.load(sys.stdin)
        config = LiveConfig(**request["config"])
        if not config.enabled:
            raise ValueError("worker requires enabled monitoring")
        from paho.mqtt.publish import multiple
        context = None
        if config.tls:
            context = ssl.create_default_context(cafile=config.ca_certs or None)
            if config.certfile:
                context.load_cert_chain(config.certfile, config.keyfile)
        messages = [{**item, "payload": _json(item["payload"])} for item in request["messages"]]
        auth = {"username": config.username, "password": config.password} if config.username else None
        multiple(messages, hostname=config.host, port=config.port, auth=auth, tls=context,
                 client_id=config.client_id or f"ha-live-{config.device_id}")
    except Exception:
        raise SystemExit(1) from None
    raise SystemExit(0)

# Existing names remain aliases, so installed TOML files and topics keep working.
ALIASES = {
    "MQTT_JSON_Status": "enabled", "SendMQTTOnSuccess": "on_success",
    "mqtt_json_topic": "topic", "broker_address": "host", "broker_port": "port",
    "mqtt_username": "username", "mqtt_password": "password",
    "MQTTClientID": "client_id", "MQTTQoS": "qos", "MQTTTimeoutSeconds": "timeout",
    "MQTTTLS": "tls", "MQTTCAFile": "ca_certs", "MQTTCertFile": "certfile", "MQTTKeyFile": "keyfile",
}
LIVE_KEYS = {
    "LiveMQTTEnabled", "LiveMQTTDiscovery", "LiveBackupName", "LiveManufacturer",
    "LiveHeartbeatSeconds", "LiveNotifyStart", "LiveNotifySuccess", "LiveNotifyFailure",
    "LiveDeviceID", "LiveTopicPrefix", "LiveDiscoveryPrefix", "LiveMQTTQoS",
    "LivePublishTimeoutSeconds", "LiveClientID", "LiveMinPublishIntervalSeconds",
    "LiveExpireAfterSeconds", "LiveDiscoveryIntervalSeconds", "LiveFinalWaitSeconds", "LiveMQTTOnDryRun",
}
REPORTING_KEYS = set(ALIASES) | LIVE_KEYS | {"MQTTJSONOnDryRun"}


def configure_reporting(table: dict, config_path: Path, job: str):
    """Reuse the existing transport validator; canonical options override legacy aliases."""
    from .mqtt_notifications import validate_mqtt_config
    shared = {key: value for key, value in table.items() if key not in REPORTING_KEYS}
    for supplied, legacy in ALIASES.items():
        if supplied in table:
            shared[legacy] = table[supplied]
    completion = shared.pop("enabled", False)
    live_enabled = table.get("LiveMQTTEnabled", False)
    send_dry = table.get("MQTTJSONOnDryRun", True)
    for key, value in (("MQTT_JSON_Status", completion), ("LiveMQTTEnabled", live_enabled),
                       ("MQTTJSONOnDryRun", send_dry), ("SendMQTTOnSuccess", shared.get("on_success", False))):
        if type(value) is not bool:
            raise ValueError(f"mqtt.{key} must be true or false")
    # Reuse common broker/TLS validation without requiring an unused completion
    # topic when only live preview is enabled. This internal sentinel is never sent.
    transport_input = shared if completion else dict(shared, topic="job-live")
    transport = validate_mqtt_config(transport_input, config_path.parent) if completion or live_enabled else None
    completion_config = dict(transport, send_on_dry_run=send_dry) if completion else None
    live_config = None
    if live_enabled:
        adapted = dict(table)
        # Same validated transport, independently enabled publishing channels.
        for canonical, legacy in ALIASES.items():
            if legacy in transport:
                adapted[canonical] = transport[legacy]
        live_config = LiveConfig.from_mapping(adapted, job=job, config_key=str(config_path),
                                               base_dir=config_path.parent)
        if completion and transport["topic"] in (live_config.state_topic, live_config.result_topic, live_config.events_topic):
            raise ValueError("Completion topic must differ from live state/result/events topics")
    return completion_config, live_config


_CURRENT: ContextVar[RunReporting | None] = ContextVar("cleanup_reporting", default=None)


class RunReporting:
    """Small app adapter: shared identity, real stderr and snapshot/dataset observations."""

    def __init__(self, args, version: str):
        self.run_id = str(uuid.uuid4())
        self.stderr = ""
        self.failed_datasets = []
        self.completed = 0
        self.details = {"datasets_configured": None, "datasets_completed": 0, "datasets_processed": 0,
                        "current_dataset_index": None, "snapshots_processed": 0,
                        "dataset_failures": 0, "snapshots_matched": 0,
                        "snapshots_selected": 0, "snapshots_destroyed": 0,
                        "current_dataset": "", "current_hostname": ""}
        config = getattr(args, "live_config", None)
        self.live = LivePreview(config, job=args.log_prefix, name=args.reporting_name,
                                version=version, run_id=self.run_id, dry_run=args.command == "dry-run",
                                job_type="syncoid_snapshot_cleanup", item_unit="datasets",
                                outcome_item_unit="snapshots") if config else None
        self._token = None

    def start(self):
        self._token = _CURRENT.set(self)
        if self.live:
            self.live.start()
            self.live.update(completed=0, details=self.details)

    def update(self, *, phase=None, current_item=None, **details):
        self.details.update(details)
        self.completed = self.details["datasets_completed"] + self.details["dataset_failures"]
        self.details["datasets_processed"] = self.completed
        if self.live:
            values = {"details": self.details, "completed": self.completed,
                      "total": self.details["datasets_configured"]}
            if phase is not None:
                values["phase"] = phase
            if current_item is not None:
                values["current_item"] = current_item
            self.live.update(**values)

    def listed(self, count):
        self.details["snapshots_matched"] += count
        self.update()

    def item(self, outcome, name, reason="", **details):
        self.details["snapshots_processed"] += 1
        if outcome == "success":
            self.details["snapshots_destroyed"] += 1
        if self.live:
            self.live.record_item(outcome, name=name, reason=reason, **details)
        self.update()

    def selected(self, count):
        self.details["snapshots_selected"] += count
        self.update()

    def dataset_completed(self, report):
        self.details["datasets_completed"] += 1
        self.update()

    def dataset_failure(self, dataset, error):
        if not getattr(error, "stderr_captured", False):
            self.capture(error.stderr)
        self.failed_datasets.append({"name": dataset, "command": list(error.cmd),
                                     "exit_code": error.returncode, "error": str(error),
                                     "stderr": (error.stderr or "")[-4000:]})
        self.details["dataset_failures"] = len(self.failed_datasets)
        self.update()

    def scan_complete(self):
        # Synchronize observed attempts only; never force completed up to total.
        self.update()

    def capture(self, output):
        if isinstance(output, bytes):
            output = output.decode("utf-8", errors="replace")
        self.stderr = (self.stderr + (output or ""))[-4000:]
        if self.live:
            self.live.update(stderr=self.stderr)

    def finish(self, code, error, warning):
        try:
            if self.live:
                self.live.finish(code, error=str(error) if error is not None else "",
                                 stderr=self.stderr, warning=bool(warning), interrupted=code == 130)
        finally:
            if self.live:
                self.live.close()
            if self._token is not None:
                _CURRENT.reset(self._token)
                self._token = None


def observe(method: str, *args, **kwargs):
    """Best-effort local instrumentation: reporting must never fail the actual job."""
    reporter = _CURRENT.get()
    if reporter is not None:
        try:
            getattr(reporter, method)(*args, **kwargs)
        except Exception:
            # No credential/worker exceptions in logs and no fabricated job failure.
            pass


if __name__ == "__main__":
    run_worker_if_requested()
    print(__doc__, file=sys.stderr)
    raise SystemExit(2)
