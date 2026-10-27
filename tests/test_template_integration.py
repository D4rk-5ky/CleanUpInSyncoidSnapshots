"""Adapter checks: ZFS/mail/MQTT substituted; no production operations."""
from contextlib import ExitStack
from dataclasses import fields
import json
import logging
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import CleanUpInSyncoidSnapshots as app
from modules.config_loader import load_config
from modules.ha_live_preview import LiveConfig, LivePreview
from modules.mqtt_status import MQTTConfig, encode_report
from modules import mqtt_notifications as mqtt


def example():
    return json.loads((ROOT / 'config-example.json').read_text())


class ConfigTests(unittest.TestCase):
    def load(self, changes):
        with tempfile.TemporaryDirectory() as directory:
            cfg = example()
            cfg.update(changes)
            path = Path(directory) / 'config.json'
            path.write_text(json.dumps(cfg))
            return load_config(path, 'cleanup')

    def test_example_matches_template_fields_and_safe_defaults(self):
        cfg = example()
        for section, kind in [('completion', MQTTConfig), ('live', LiveConfig)]:
            self.assertEqual(set(cfg[section]), {f.name for f in fields(kind)})
        args = load_config(ROOT / 'config-example.json', 'fallback')
        self.assertTrue(args.dry_run)
        self.assertIsNone(args.mqtt_config)
        self.assertFalse(args.live_config.enabled)

    def test_independent_enables_and_template_defaults(self):
        for completion in (False, True):
            for live in (False, True):
                args = self.load({'completion': {'enabled': completion, 'host': 'localhost'},
                                  'live': {'enabled': live, 'host': 'localhost'}})
                self.assertEqual(args.mqtt_config is not None, completion)
                self.assertEqual(args.live_config.enabled, live)
                if completion:
                    self.assertTrue(args.mqtt_config['on_success'])
                    self.assertEqual(args.mqtt_config['qos'], 0)
                self.assertFalse(args.live_config.send_on_dry_run)
                self.assertNotEqual(args.live_config.device_id, 'example_job')

    def test_conflicting_aliases_and_invalid_values_rejected(self):
        for changes in [{'mqtt': {}}, {'completion': []}, {'live': []},
                        {'completion': {'enabled': 1}}, {'live': {'enabled': 'false'}},
                        {'completion': {'retain': True}}, {'live': {'on_success': True}},
                        {'live': {'heartbeat_seconds': float('inf')}}]:
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                self.load(changes)

    def test_both_tls_paths_resolve_relative_to_json_config(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            (folder / 'ca.pem').touch()
            cfg = example()
            for section in ('completion', 'live'):
                cfg[section].update(enabled=True, tls=True, ca_certs='ca.pem')
            path = folder / 'config.json'
            path.write_text(json.dumps(cfg))
            args = load_config(path, 'fallback')
            self.assertEqual(args.mqtt_config['ca_certs'], str(folder / 'ca.pem'))
            self.assertEqual(args.live_config.ca_certs, str(folder / 'ca.pem'))

    def test_bad_json_error_does_not_echo_source_credentials(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'bad.json'
            path.write_text('{"password": TOP_SECRET}')
            with self.assertRaises(ValueError) as caught:
                load_config(path, 'cleanup')
            self.assertNotIn('TOP_SECRET', str(caught.exception))


class LifecycleTests(unittest.TestCase):
    def invoke(self, *, completion=True, live=True, command='delete', on_success=True,
               live_dry_run=False, effect=None, root=True, hosts='host\n',
               continuation=True, retention_error=None, mail_error=None,
               duplicate=False, send_ok=True):
        with tempfile.TemporaryDirectory() as directory, ExitStack() as stack:
            folder = Path(directory)
            cfg = example()
            cfg['cleanup'].update(command=command, datasets_file='datasets', syncoid_hosts_file='hosts',
                                  continue_on_other_failures=continuation,
                                  continue_on_missing_dataset=continuation)
            cfg['completion'].update(enabled=completion, on_success=on_success)
            cfg['live'].update(enabled=live, send_on_dry_run=live_dry_run)
            cfg['mail'].update(enabled=bool(mail_error), on_success=True)
            (folder / 'datasets').write_text('tank/a\ntank/b\n')
            (folder / 'hosts').write_text(hosts)
            path = folder / 'config.json'
            path.write_text(json.dumps(cfg))
            monitors, batches = [], []
            def make_monitor(*args, **kwargs):
                monitor = LivePreview(*args, **kwargs)
                monitors.append(monitor)
                return monitor
            def send(_monitor, messages):
                batches.append(messages)
                return send_ok
            stack.enter_context(patch.object(app, 'LivePreview', side_effect=make_monitor))
            stack.enter_context(patch.object(LivePreview, '_send', send))
            stack.enter_context(patch.object(sys, 'argv', ['cleanup', '-c', str(path)]))
            stack.enter_context(patch.object(app.os, 'geteuid', return_value=0 if root else 1000))
            stack.enter_context(patch.object(app, 'get_script_log_folder', return_value=directory))
            logger = logging.Logger('errors')
            logger.addHandler(logging.NullHandler())
            stack.enter_context(patch.object(app, 'setup_logger', return_value=(Mock(), logger, str(folder / 'none.err'))))
            commands = stack.enter_context(patch.object(app, 'run_cmd', side_effect=effect, return_value=Mock(stdout='')))
            stack.enter_context(patch.object(app, 'delete_old_files', side_effect=retention_error,
                                            return_value={'groups_selected': 0, 'files_selected': 0}))
            stack.enter_context(patch.object(app, 'MailTo', side_effect=mail_error))
            notify = stack.enter_context(patch.object(app, 'notify_mqtt'))
            if duplicate:
                stack.enter_context(patch.object(app.fcntl, 'flock', side_effect=BlockingIOError))
            error = None
            try:
                app.main()
            except (Exception, SystemExit, KeyboardInterrupt) as exc:
                error = exc
            return monitors[0], batches, notify, commands, error

    def test_all_four_channel_combinations_and_shared_run_id(self):
        for completion in (False, True):
            for live in (False, True):
                with self.subTest(completion=completion, live=live):
                    monitor, batches, notify, commands, error = self.invoke(completion=completion, live=live)
                    self.assertIsNone(error)
                    self.assertEqual(commands.call_count, 2)
                    self.assertEqual(bool(batches), live)
                    self.assertEqual(bool(notify.call_count), completion)
                    state = monitor.snapshot()
                    self.assertEqual(state['status'], 'success')
                    self.assertEqual((state['completed'], state['total']), (2, 2))
                    self.assertEqual(state['successful_dataset_count'], 2)
                    self.assertIsNone(state['transferred_bytes'])
                    self.assertIsNone(state['bytes_per_second'])
                    if completion:
                        report = notify.call_args.args[1]
                        self.assertEqual(report['run_id'], state['run_id'])
                        self.assertTrue(report['success'])
                        self.assertEqual(report['schema_version'], 1)
                        encode_report(report)

    def test_suppressed_completion_success_keeps_live_enabled(self):
        monitor, batches, notify, _, error = self.invoke(on_success=False)
        self.assertIsNone(error)
        self.assertTrue(batches)
        notify.assert_not_called()
        self.assertEqual(monitor.snapshot()['status'], 'success')

    def test_separate_dry_run_gate_and_no_retained_preview_results(self):
        for enabled in (False, True):
            monitor, batches, notify, commands, error = self.invoke(command='dry-run', live_dry_run=enabled)
            self.assertIsNone(error)
            self.assertEqual(bool(batches), enabled)
            self.assertTrue(notify.call_args.args[1]['dry_run'])
            self.assertTrue(monitor.snapshot()['dry_run'])
            self.assertTrue(all(call.args[0][1] == 'list' for call in commands.call_args_list))
            self.assertFalse(any(message['topic'] == monitor.config.result_topic
                                 for batch in batches for message in batch))

    def test_continued_failure_retains_failure_and_stderr(self):
        exc = app.CommandError(['zfs', 'list', 'tank/a'], 1, '', 'dataset does not exist')
        monitor, _, notify, commands, error = self.invoke(effect=[exc, Mock(stdout='')])
        self.assertIsInstance(error, SystemExit)
        self.assertEqual(error.code, 1)
        self.assertEqual(commands.call_count, 2)
        state = monitor.snapshot()
        self.assertEqual(state['status'], 'failure')
        self.assertEqual(state['failed_dataset_count'], 1)
        self.assertEqual(state['successful_dataset_count'], 1)
        self.assertEqual(state['progress_percent'], 100)
        report = notify.call_args.args[1]
        self.assertEqual(report['failed_datasets'][0]['source'], 'tank/a')
        self.assertIn('dataset does not exist', report['stderr'])
        self.assertFalse(report['success'])

    def test_stopped_run_records_unattempted_datasets(self):
        exc = app.CommandError(['zfs', 'list', 'tank/a'], 1, '', 'permission denied')
        monitor, _, notify, commands, error = self.invoke(effect=exc, continuation=False)
        self.assertIsInstance(error, app.DatasetFailuresError)
        self.assertEqual(commands.call_count, 1)
        state = monitor.snapshot()
        self.assertEqual((state['completed'], state['total']), (1, 2))
        self.assertEqual(state['skipped_dataset_count'], 1)
        self.assertEqual(notify.call_args.args[1]['skipped_datasets'][0]['source'], 'tank/b')

    def test_interrupt_and_root_rejection_never_report_success(self):
        for options, code, status in [({'effect': KeyboardInterrupt}, 130, 'interrupted'),
                                       ({'root': False}, 1, 'failure')]:
            monitor, _, notify, _, error = self.invoke(**options)
            self.assertIsNotNone(error)
            self.assertEqual(monitor.snapshot()['status'], status)
            self.assertEqual(monitor.snapshot()['completed'], 0 if code == 130 else None)
            self.assertEqual(notify.call_args.args[1]['exit_code'], code)
            self.assertFalse(notify.call_args.args[1]['success'])

    def test_empty_hosts_are_skipped(self):
        monitor, _, notify, commands, error = self.invoke(hosts='')
        self.assertIsNone(error)
        commands.assert_not_called()
        self.assertEqual(monitor.snapshot()['skipped_dataset_count'], 2)
        self.assertEqual(len(notify.call_args.args[1]['skipped_datasets']), 2)

    def test_retention_failure_and_nonfatal_mail_warning(self):
        monitor, _, notify, _, error = self.invoke(retention_error=OSError('retention failed'))
        self.assertIsNotNone(error)
        self.assertEqual(monitor.snapshot()['status'], 'failure')
        self.assertFalse(notify.call_args.args[1]['success'])
        monitor, _, notify, _, error = self.invoke(mail_error=OSError('mail unavailable'))
        self.assertIsNone(error)
        self.assertTrue(monitor.snapshot()['warning'])
        self.assertTrue(notify.call_args.args[1]['success'])
        self.assertTrue(notify.call_args.args[1]['warning'])

    def test_live_delivery_failure_is_nonfatal(self):
        monitor, _, notify, commands, error = self.invoke(send_ok=False)
        self.assertIsNone(error)
        self.assertEqual(commands.call_count, 2)
        self.assertEqual(monitor.last_delivery, 'failed')
        self.assertTrue(notify.call_args.args[1]['success'])

    def test_duplicate_does_not_publish_live_or_run_zfs(self):
        monitor, batches, notify, commands, error = self.invoke(duplicate=True)
        self.assertIsInstance(error, RuntimeError)
        self.assertEqual(batches, [])
        commands.assert_not_called()
        self.assertFalse(notify.call_args.args[1]['success'])
        self.assertEqual(monitor.snapshot()['status'], 'idle')

    def test_run_cmd_captures_bounded_success_stderr(self):
        monitor = LivePreview(LiveConfig(), name='cleanup', job='cleanup')
        monitor.start()
        with patch.object(app.subprocess, 'run', return_value=Mock(returncode=0, stdout='', stderr='x' * 5000)):
            app.run_cmd(['zfs', 'list'], progress=monitor)
        self.assertEqual(len(monitor.snapshot()['stderr']), 4000)
        monitor.close()


class PolicyTests(unittest.TestCase):
    def test_completion_dry_run_gate_suppresses_both_outcomes(self):
        args = Mock(log_prefix='cleanup', backup_title='cleanup', backup_comment='', command='dry-run')
        for code in (0, 1):
            report = mqtt.build_mqtt_report(args, '0.0.16', code)
            with patch('modules.mqtt_status.subprocess.run') as launch:
                result = mqtt.notify_mqtt({'enabled': True, 'host': 'localhost', 'send_on_dry_run': False}, report)
                self.assertEqual(result.status, 'skipped')
                launch.assert_not_called()

    def test_worker_hooks_bypass_config_and_cleanup(self):
        for hook in ('completion_worker', 'live_worker'):
            with patch.object(app, hook, side_effect=SystemExit(0)) as worker, \
                    patch.object(app, 'load_config') as load, patch.object(app, 'run_cleanup') as cleanup:
                with self.assertRaises(SystemExit):
                    app.main()
                worker.assert_called_once()
                load.assert_not_called()
                cleanup.assert_not_called()


if __name__ == '__main__':
    unittest.main()
