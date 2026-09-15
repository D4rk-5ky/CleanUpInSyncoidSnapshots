"""Safe regression checks: ZFS/mail are mocked; MQTT integration uses loopback only."""

import argparse
from contextlib import ExitStack
import importlib.util
import io
import json
import logging
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import threading
import time
import types
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import CleanUpInSyncoidSnapshots as app
import mqtt_notifications as mqtt


def arguments(**overrides):
    """Supply representative parsed CLI values for report tests."""
    values = dict(backup_title="NAS cleanup", backup_comment="After replication",
                  log_prefix="cleanup", command="delete")
    return argparse.Namespace(**dict(values, **overrides))


class ConfigTests(unittest.TestCase):
    def load(self, **overrides):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "mqtt.json"
            path.write_text(json.dumps(dict(host="localhost", topic="cleanup/status", **overrides)))
            return mqtt.load_mqtt_config(path)

    def test_example_covers_every_option(self):
        config = mqtt.load_mqtt_config(ROOT / "mqtt-config-example.json")
        self.assertEqual(set(config), set(mqtt.DEFAULTS) | {"host", "topic"})

    def test_defaults(self):
        config = self.load()
        self.assertEqual(config["qos"], 1)
        self.assertFalse(config["publish_dry_run"])

    def test_invalid_options(self):
        for overrides in ({"port": 0}, {"qos": True}, {"timeout": 0},
                          {"timeout": float("nan")}, {"tls": "false"},
                          {"password": "secret"}, {"retain": True},
                          {"certfile": "missing"}, {"client_id": None}):
            with self.subTest(overrides=overrides), self.assertRaises(ValueError):
                self.load(**overrides)

    def test_invalid_topic_and_shape(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "mqtt.json"
            for value in ([], {"host": "localhost", "topic": "cleanup/#"},
                          {"host": "localhost", "topic": ""}):
                path.write_text(json.dumps(value))
                with self.assertRaises(ValueError):
                    mqtt.load_mqtt_config(path)

    def test_relative_certificate_paths(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "mqtt.json"
            certificate = Path(directory) / "ca.pem"
            certificate.write_text("placeholder; parsing happens in TLS library")
            path.write_text(json.dumps(dict(host="localhost", topic="status", tls=True, ca_certs="ca.pem")))
            self.assertEqual(mqtt.load_mqtt_config(path)["ca_certs"], str(certificate))


class ReportTests(unittest.TestCase):
    def test_success_schema_and_types(self):
        report = mqtt.build_mqtt_report(arguments(), "0.0.1", 0, warning=True)
        self.assertEqual(report["status"], "success")
        self.assertEqual(report["title"], "NAS cleanup")
        self.assertIs(type(report["exit_code"]), int)
        self.assertIs(report["warning"], True)
        self.assertEqual(report["error"], "")
        self.assertEqual(json.loads(json.dumps(report)), report)

    def test_failure_command_diagnostics(self):
        error = app.CommandError(["zfs", "destroy", "tank/data@snap"], 7, "", "dataset is busy")
        report = mqtt.build_mqtt_report(arguments(), "0.0.1", 1, error)
        self.assertEqual(report["status"], "failure")
        self.assertEqual(report["exit_code"], 1)
        self.assertIn("Command failed (7)", report["error"])
        self.assertEqual(report["stderr"], "dataset is busy")

    def test_fallback_title_and_output_limit(self):
        error = app.CommandError(["zfs"], 1, "x" * 5000, "")
        report = mqtt.build_mqtt_report(arguments(backup_title="  "), "0.0.1", 1, error)
        self.assertEqual(report["title"], "CleanUpInSyncoidSnapshots")
        self.assertEqual(len(report["stderr"]), 4096)

    def test_disabled_and_default_dry_run_do_not_launch_worker(self):
        with patch.object(mqtt.subprocess, "run") as launch:
            mqtt.notify_mqtt(None, {"dry_run": False})
            mqtt.notify_mqtt(dict(mqtt.DEFAULTS), {"dry_run": True})
        launch.assert_not_called()

    def test_worker_input_and_timeout(self):
        config = dict(mqtt.DEFAULTS, host="localhost", topic="status", username="u", password="secret")
        report = mqtt.build_mqtt_report(arguments(), "0.0.1", 0)
        with patch.object(mqtt.subprocess, "run", return_value=Mock(returncode=0)) as launch:
            mqtt.notify_mqtt(config, report)
        call = launch.call_args
        self.assertNotIn("secret", " ".join(call.args[0]))
        self.assertEqual(json.loads(call.kwargs["input"])["report"], report)
        self.assertEqual(call.kwargs["timeout"], 15)

    def test_dry_run_requires_explicit_publish_opt_in(self):
        config = dict(mqtt.DEFAULTS, publish_dry_run=True)
        report = mqtt.build_mqtt_report(arguments(command="dry-run"), "0.0.1", 0)
        with patch.object(mqtt.subprocess, "run", return_value=Mock(returncode=0)) as launch:
            mqtt.notify_mqtt(config, report)
        self.assertTrue(json.loads(launch.call_args.kwargs["input"])["report"]["dry_run"])

    def test_delivery_failure_is_logged_and_secret_not_echoed(self):
        logger = Mock()
        with patch.object(mqtt.subprocess, "run", return_value=Mock(returncode=1, stderr="secret")):
            mqtt.notify_mqtt(dict(mqtt.DEFAULTS), {"dry_run": False}, logger)
        self.assertIn("MQTT notification failed", logger.error.call_args.args[0])
        self.assertNotIn("secret", logger.error.call_args.args[0])

    def test_timeout_is_nonfatal(self):
        logger = Mock()
        with patch.object(mqtt.subprocess, "run", side_effect=subprocess.TimeoutExpired("worker", 1)):
            mqtt.notify_mqtt(dict(mqtt.DEFAULTS), {"dry_run": False}, logger)
        self.assertIn("timed out", logger.error.call_args.args[0])

    def test_worker_tls_and_auth(self):
        single = Mock()
        publish = types.ModuleType("paho.mqtt.publish")
        publish.single = single
        config = dict(mqtt.DEFAULTS, host="localhost", topic="status", tls=True,
                      username="test", password="secret", ca_certs="ca.pem",
                      certfile="client.pem", keyfile="client.key")
        with patch.dict(sys.modules, {"paho.mqtt.publish": publish}), \
                patch.object(sys, "stdin", io.StringIO(json.dumps({"config": config, "report": {"status": "success"}}))), \
                patch.object(mqtt.ssl, "create_default_context") as context:
            mqtt.publish_worker()
        context.assert_called_once_with(cafile="ca.pem")
        context.return_value.load_cert_chain.assert_called_once_with("client.pem", "client.key")
        self.assertFalse(single.call_args.kwargs["retain"])
        self.assertEqual(single.call_args.kwargs["auth"]["password"], "secret")


class BlueprintTests(unittest.TestCase):
    def setUp(self):
        self.path = ROOT / "home-assistant" / "CleanUpInSyncoidSnapshots-mqtt-persistent-notification.yaml"
        self.text = self.path.read_text(encoding="utf-8")

    def test_blueprint_is_receive_only_mqtt_reporter(self):
        self.assertIn("domain: automation", self.text)
        self.assertIn("trigger: mqtt", self.text)
        self.assertIn("topic: !input mqtt_topic", self.text)
        self.assertIn("persistent_notification.create", self.text)
        self.assertNotIn("mqtt.publish", self.text)
        self.assertNotIn("zfs destroy", self.text.lower())

    def test_blueprint_validates_cleanup_report_contract(self):
        for expected in (
            "CleanUpInSyncoidSnapshots",
            "get('status') in ['success', 'failure']",
            "get('warning', false)",
            "get('dry_run', false)",
            "get('exit_code', 'unknown')",
            "get('error', '')",
            "get('stderr', '')",
            "get('version', '')",
            "get('timestamp', '')",
        ):
            self.assertIn(expected, self.text)

    def test_blueprint_notification_controls_are_present(self):
        for expected in (
            "notify_success:",
            "notify_warning:",
            "notify_failure:",
            "notify_dry_run:",
            "replace_previous:",
            "notification_id:",
        ):
            self.assertIn(expected, self.text)


class LifecycleTests(unittest.TestCase):
    def invoke(self, command="delete", root=True, zfs_error=None, cleanup_error=None, mail_error=None, mqtt_enabled=True, missing_input=False):
        """Exercise actual CLI/lifecycle with harmless command and logger substitutes."""
        with tempfile.TemporaryDirectory() as directory, ExitStack() as stack:
            folder = Path(directory)
            datasets = folder / "datasets"
            hosts = folder / "hosts"
            datasets.write_text("tank/data\n")
            hosts.write_text("host\n")
            if missing_input:
                datasets.unlink()
            argv = ["cleanup", "-c", command, "-d", str(datasets), "-s", str(hosts), "-r", "1"]
            if mqtt_enabled:
                argv += ["--mqtt-config", str(ROOT / "mqtt-config-example.json")]
            if mail_error:
                argv += ["--send-mail", "nobody@example.invalid", "--mail-on-success"]
            stack.enter_context(patch.object(sys, "argv", argv))
            stack.enter_context(patch.object(app.os, "geteuid", return_value=0 if root else 1000, create=True))
            stack.enter_context(patch.object(app, "pick_log_folder", return_value=directory))
            error_logger = logging.Logger("test-errors")
            error_logger.addHandler(logging.NullHandler())
            stack.enter_context(patch.object(app, "setup_logger", return_value=(Mock(), error_logger, str(folder / "absent.err"))))
            command_mock = stack.enter_context(patch.object(app, "run_cmd", side_effect=zfs_error,
                                                           return_value=Mock(stdout="")))
            stack.enter_context(patch.object(app, "delete_old_files", side_effect=cleanup_error))
            stack.enter_context(patch.object(app, "MailTo", side_effect=mail_error))
            notify = stack.enter_context(patch.object(app, "notify_mqtt"))
            exception = None
            try:
                app.main()
            except (Exception, SystemExit, KeyboardInterrupt) as exc:
                exception = exc
            return notify, command_mock, exception

    def test_success_final_report(self):
        notify, command, error = self.invoke()
        self.assertIsNone(error)
        self.assertEqual(command.call_count, 1)
        self.assertEqual(notify.call_args.args[1]["status"], "success")

    def test_original_mode_needs_no_mqtt(self):
        notify, command, error = self.invoke(mqtt_enabled=False)
        self.assertIsNone(error)
        notify.assert_not_called()
        self.assertEqual(command.call_count, 1)

    def test_root_rejection_reports_failure(self):
        notify, command, error = self.invoke(root=False)
        self.assertIsInstance(error, SystemExit)
        self.assertEqual(error.code, 1)
        command.assert_not_called()
        report = notify.call_args.args[1]
        self.assertEqual(report["status"], "failure")
        self.assertIn("root", report["error"])

    def test_command_failure_reports_stderr(self):
        failure = app.CommandError(["zfs", "list"], 2, "", "unavailable")
        notify, _, error = self.invoke(zfs_error=failure)
        self.assertIs(error, failure)
        self.assertEqual(notify.call_args.args[1]["stderr"], "unavailable")

    def test_missing_input_reports_failure_before_zfs(self):
        notify, command, error = self.invoke(missing_input=True)
        self.assertIsInstance(error, FileNotFoundError)
        command.assert_not_called()
        self.assertEqual(notify.call_args.args[1]["status"], "failure")

    def test_finalization_failure_cannot_report_success(self):
        notify, _, error = self.invoke(cleanup_error=OSError("log cleanup failed"))
        self.assertIsInstance(error, OSError)
        self.assertEqual(notify.call_args.args[1]["status"], "failure")

    def test_mail_warning_is_nonfatal(self):
        notify, _, error = self.invoke(mail_error=OSError("mail unavailable"))
        self.assertIsNone(error)
        report = notify.call_args.args[1]
        self.assertEqual(report["status"], "success")
        self.assertTrue(report["warning"])

    def test_interrupt_is_never_success(self):
        notify, _, error = self.invoke(zfs_error=KeyboardInterrupt())
        self.assertIsInstance(error, KeyboardInterrupt)
        self.assertEqual(notify.call_args.args[1]["exit_code"], 130)
        self.assertEqual(notify.call_args.args[1]["status"], "failure")

    def test_invalid_config_stops_before_cleanup(self):
        argv = ["cleanup", "-c", "delete", "-d", "datasets", "-s", "hosts", "--mqtt-config", "missing.json"]
        with patch.object(sys, "argv", argv), patch.object(sys, "stderr", io.StringIO()), \
                patch.object(app, "run_cleanup") as cleanup, self.assertRaises(SystemExit) as caught:
            app.main()
        self.assertEqual(caught.exception.code, 2)
        cleanup.assert_not_called()


class RetentionTests(unittest.TestCase):
    def prune(self, names, older_than=None, retain_count=0, dry_run=False):
        with patch.object(app, "run_cmd", return_value=Mock(stdout="\n".join(names))) as command:
            app.delete_syncoid_snapshots(Mock(), Mock(), "tank/data", ["host"], older_than, retain_count, dry_run)
        return [call.args[0] for call in command.call_args_list]

    def test_matching_count_and_dry_run(self):
        old = "tank/data@syncoid_host_2020-01-01:00:00:00-GMT00:00"
        new = "tank/data@syncoid_host_2021-01-01:00:00:00-GMT00:00"
        ignored = "tank/data@syncoid_other_2019-01-01:00:00:00-GMT00:00"
        self.assertEqual(self.prune([old, new, ignored], retain_count=1)[1:], [["zfs", "destroy", old]])
        self.assertEqual(len(self.prune([old, new], dry_run=True)), 1)

    def test_original_no_retention_behavior_is_preserved(self):
        old = "tank/data@syncoid_host_2020-01-01:00:00:00-GMT00:00"
        self.assertEqual(self.prune([old])[1:], [["zfs", "destroy", old]])

    def test_age_and_count_work_together(self):
        names = [f"tank/data@syncoid_host_{year}-01-01:00:00:00-GMT00:00" for year in (2020, 2021, 2099)]
        self.assertEqual(self.prune(names, app.parse_older_than("7d"), 2)[1:], [["zfs", "destroy", names[0]]])

    def test_log_dry_run_and_group_retention(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            old = [folder / f"cleanup-Date-2020-01-01_00_00_00.{ext}" for ext in ("log", "err")]
            newest = folder / "cleanup-Date-2021-01-01_00_00_00.log"
            unrelated = folder / "other.log"
            for file in old + [newest, unrelated]:
                file.write_text("test")
            app.delete_old_files(Mock(), Mock(), directory, "cleanup", None, 1, True)
            self.assertTrue(all(file.exists() for file in old))
            app.delete_old_files(Mock(), Mock(), directory, "cleanup", None, 1, False)
            self.assertTrue(all(not file.exists() for file in old))
            self.assertTrue(newest.exists() and unrelated.exists())


def receive_packet(connection):
    """Read a complete MQTT packet from the loopback test client."""
    def read_exact(count):
        data = b""
        while len(data) < count:
            chunk = connection.recv(count - len(data))
            if not chunk:
                raise EOFError("client disconnected")
            data += chunk
        return data

    header = read_exact(1)[0]
    length, multiplier = 0, 1
    while True:
        byte = read_exact(1)[0]
        length += (byte & 127) * multiplier
        if not byte & 128:
            break
        multiplier *= 128
    return header, read_exact(length)


try:
    PAHO_AVAILABLE = importlib.util.find_spec("paho.mqtt") is not None
except ModuleNotFoundError:
    PAHO_AVAILABLE = False


@unittest.skipUnless(PAHO_AVAILABLE, "optional paho-mqtt dependency is not installed")
class BrokerIntegrationTests(unittest.TestCase):
    def exchange(self, qos=1, mode="success"):
        """Receive a real Paho publish locally, or simulate rejection/a stalled broker."""
        captured = {}
        listener = socket.socket()
        listener.bind(("127.0.0.1", 0))
        listener.listen(1)
        listener.settimeout(5)

        def serve():
            try:
                with listener, listener.accept()[0] as connection:
                    connection.settimeout(5)
                    captured["connect"] = receive_packet(connection)
                    if mode == "stall":
                        try:
                            captured["closed"] = connection.recv(1) == b""
                        except ConnectionResetError:
                            captured["closed"] = True
                        return
                    connection.sendall(b"\x20\x02\x00\x05" if mode == "reject" else b"\x20\x02\x00\x00")
                    if mode == "reject":
                        return
                    header, data = receive_packet(connection)
                    captured["retain"] = bool(header & 1)
                    captured["qos"] = (header >> 1) & 3
                    size = int.from_bytes(data[:2], "big")
                    captured["topic"] = data[2:2 + size].decode()
                    rest = data[2 + size:]
                    mid = rest[:2] if qos else b""
                    captured["report"] = json.loads(rest[2:] if qos else rest)
                    if qos == 1:
                        connection.sendall(b"\x40\x02" + mid)
                    elif qos == 2:
                        connection.sendall(b"\x50\x02" + mid)
                        receive_packet(connection)
                        connection.sendall(b"\x70\x02" + mid)
            except Exception as exc:
                captured["exception"] = exc

        worker = threading.Thread(target=serve, daemon=True)
        worker.start()
        config = dict(mqtt.DEFAULTS, host="127.0.0.1", topic="test/cleanup/status",
                      port=listener.getsockname()[1], qos=qos, timeout=1 if mode == "stall" else 5,
                      username="test-user", password="test-password")
        logger = Mock()
        report = mqtt.build_mqtt_report(arguments(), "0.0.1", 0)
        start = time.monotonic()
        mqtt.notify_mqtt(config, report, logger)
        elapsed = time.monotonic() - start
        worker.join(6)
        self.assertFalse(worker.is_alive())
        self.assertNotIn("exception", captured, str(captured.get("exception")))
        return captured, logger, elapsed

    def test_real_qos_0_1_2_delivery(self):
        for qos in (0, 1, 2):
            with self.subTest(qos=qos):
                captured, logger, _ = self.exchange(qos)
                logger.error.assert_not_called()
                self.assertFalse(captured["retain"])
                self.assertEqual(captured["qos"], qos)
                self.assertEqual(captured["topic"], "test/cleanup/status")
                self.assertEqual(captured["report"]["status"], "success")
                self.assertNotIn("test-password", json.dumps(captured["report"]))

    def test_broker_rejection(self):
        _, logger, _ = self.exchange(mode="reject")
        logger.error.assert_called_once()

    def test_stalled_broker_is_killed_at_timeout(self):
        captured, logger, elapsed = self.exchange(mode="stall")
        self.assertTrue(captured["closed"])
        self.assertLess(elapsed, 4)
        self.assertIn("timed out", logger.error.call_args.args[0])


if __name__ == "__main__":
    unittest.main()
