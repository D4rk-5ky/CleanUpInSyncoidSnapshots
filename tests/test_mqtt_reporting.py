"""Offline live-preview contract, lifecycle, discovery and worker tests."""
import ast
from dataclasses import asdict, replace
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from threading import Event
import time
import types
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import mqtt_reporting as h


def wait_for(predicate, timeout=2):
    until = time.monotonic() + timeout
    while time.monotonic() < until:
        if predicate():
            return True
        time.sleep(0.01)
    return False


class LiveTests(unittest.TestCase):
    def live(self, **values):
        return h.LivePreview(h.LiveConfig(**values), name='NAS backup', job='backup', run_id='run-one')

    def test_identity_is_stable_and_separates_configs_and_hosts(self):
        first = h.make_device_id('NAS backup', '/etc/job.toml', 'nas')
        self.assertEqual(first, h.make_device_id('NAS backup', '/etc/job.toml', 'nas'))
        self.assertNotEqual(first, h.make_device_id('NAS backup', '/etc/job2.toml', 'nas'))
        self.assertNotEqual(first, h.make_device_id('NAS backup', '/etc/job.toml', 'other'))

    def test_config_validation_and_secret_repr(self):
        for change in ({'enabled': True}, {'host': 'mqtt://broker'}, {'device_id': 'Bad/id'},
                       {'topic_prefix': 'a/#'}, {'discovery_prefix': ''}, {'heartbeat_seconds': 0},
                       {'min_publish_interval': 11}, {'expire_after': 20}, {'final_wait': float('nan')},
                       {'qos': True}, {'timeout': -1}, {'tls': 'true'}, {'send_on_dry_run': 'false'},
                       {'password': 'secret'}, {'ca_certs': 'ca'}, {'tls': True, 'certfile': 'cert'}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                h.LiveConfig(**change)
        self.assertNotIn('secret-token', repr(h.LiveConfig(username='user', password='secret-token')))

    def test_manufacturer_is_configurable_in_discovery_and_state(self):
        config = h.LiveConfig(manufacturer='My Backup Jobs', device_id='nas_one')
        messages = h.discovery_messages(config, 'NAS one')
        self.assertTrue(all(item['payload']['device']['manufacturer'] == 'My Backup Jobs' for item in messages))
        live = h.LivePreview(config, name='NAS one', job='backup')
        self.assertEqual(live.snapshot()['manufacturer'], 'My Backup Jobs')
        defaults = h.discovery_messages(replace(config, manufacturer='MQTT job template'), 'NAS one')
        self.assertEqual([item['payload']['unique_id'] for item in messages],
                         [item['payload']['unique_id'] for item in defaults])

    def test_invalid_manufacturer_names_are_rejected(self):
        for value in ('', ' ', ' leading', 'trailing ', 'bad\x00name', None, True):
            with self.subTest(value=value), self.assertRaises(ValueError):
                h.LiveConfig(manufacturer=value)

    def test_aggregate_sensors_have_stable_role_markers(self):
        messages = h.discovery_messages(h.LiveConfig(), 'NAS')
        tagged = [item['payload']['json_attributes_template'] for item in messages
                  if 'json_attributes_template' in item['payload']]
        self.assertEqual(len(tagged), 2)
        self.assertTrue(any('live_preview_role="status"' in text for text in tagged))
        self.assertTrue(any('live_preview_role="last_result"' in text for text in tagged))

    def test_disabled_module_maintains_local_progress_without_processes(self):
        live = self.live()
        with patch.object(h, 'Thread') as thread, patch.object(h.subprocess, 'Popen') as process:
            self.assertFalse(live.start())
            live.update(total=4, completed=1)
            self.assertEqual(live.snapshot()['status'], 'running')
            live.finish(0)
            live.close()
        thread.assert_not_called()
        process.assert_not_called()

    def test_progress_is_derived_and_unknown_is_null(self):
        live = self.live()
        self.assertIsNone(live.snapshot()['progress_percent'])
        live.start()
        live.update(total=4, completed=1, transferred_bytes=123, bytes_per_second=20.5)
        self.assertEqual(live.snapshot()['progress_percent'], 25)
        live.update(total=None)
        self.assertIsNone(live.snapshot()['progress_percent'])

    def test_rejects_bad_counters_and_direct_status_updates(self):
        live = self.live()
        for changes in ({'completed': True}, {'total': -1}, {'completed': 5, 'total': 4},
                        {'bytes_per_second': float('nan')}, {'status': 'success'}, {'exit_code': 0}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                live.update(**changes)

    def test_stderr_tail_and_utf8_replacement(self):
        live = self.live()
        live.append_stderr(b'x' * 5000 + b'\xff')
        self.assertEqual(len(live.snapshot()['stderr']), 4000)
        self.assertTrue(live.snapshot()['stderr'].endswith('\ufffd'))
        live.update(stderr='new output')
        self.assertEqual(live.snapshot()['stderr'], 'new output')

    def test_completed_success_has_typed_code_and_shared_identity(self):
        live = self.live()
        live.start()
        live.update(total=3, completed=3)
        live.finish(0, warning=True)
        state = live.snapshot()
        self.assertEqual(state['status'], 'success')
        self.assertIs(state['success'], True)
        self.assertEqual(type(state['exit_code']), int)
        self.assertEqual(state['run_id'], 'run-one')
        self.assertEqual(state['progress_percent'], 100)
        self.assertTrue(state['warning'])

    def test_failure_and_interrupt_do_not_force_progress_to_100(self):
        for code, interrupted, status in ((12, False, 'failure'), (130, True, 'interrupted')):
            with self.subTest(status=status):
                live = self.live()
                live.start()
                live.update(total=4, completed=1)
                live.finish(code, error='failed', stderr='worker output', interrupted=interrupted)
                state = live.snapshot()
                self.assertEqual(state['status'], status)
                self.assertIs(state['success'], False)
                self.assertEqual(state['exit_code'], code)
                self.assertEqual(state['progress_percent'], 25)

    def test_zero_code_with_remaining_work_is_incomplete(self):
        live = self.live()
        live.start()
        live.update(total=4, completed=2)
        live.finish(0)
        state = live.snapshot()
        self.assertEqual(state['status'], 'incomplete')
        self.assertIs(state['success'], False)
        self.assertEqual(state['exit_code'], 0)
        self.assertEqual(state['progress_percent'], 50)

    def test_finish_is_idempotent_freezes_runtime_and_rejects_late_updates(self):
        live = self.live()
        live.start()
        live.finish(1)
        runtime = live.snapshot()['runtime_seconds']
        time.sleep(0.02)
        self.assertEqual(live.snapshot()['runtime_seconds'], runtime)
        self.assertFalse(live.finish(0))
        self.assertFalse(live.update(completed=1))
        self.assertFalse(live.append_stderr('late'))
        self.assertFalse(live.start())
        self.assertEqual(live.snapshot()['exit_code'], 1)
        with self.assertRaises(ValueError):
            self.live().finish(True)

    def test_close_without_finish_does_not_invent_a_terminal_result(self):
        live = self.live()
        live.start()
        live.close()
        self.assertEqual(live.snapshot()['status'], 'running')
        self.assertIsNone(live.snapshot()['exit_code'])

    def test_discovery_separates_expiring_state_and_retained_result(self):
        config = h.LiveConfig(device_id='nas_backup')
        messages = h.discovery_messages(config, 'NAS backup')
        self.assertEqual(len(messages), 14)
        for item in messages:
            self.assertTrue(item['retain'])
            payload = item['payload']
            self.assertTrue(payload['default_entity_id'].startswith('sensor.job_live_nas_backup_'))
            if payload['state_topic'] == config.result_topic:
                self.assertNotIn('expire_after', payload)
            else:
                self.assertEqual(payload['expire_after'], 45)
        self.assertEqual(h.discovery_messages(replace(config, discovery=False), 'NAS'), [])

    def test_live_has_dataset_lists_and_counts(self):
        state = self.live().snapshot()
        for label in ('successful', 'failed', 'skipped'):
            self.assertEqual(state[label + '_items'], [])
            self.assertEqual(state[label + '_item_count'], 0)

    def test_dataset_retries_replace_previous_outcome_and_keep_reasons(self):
        live = self.live()
        live.record_item('failure', name='pool/a', destination='backup/a', reason='Receive failed')
        live.record_item('skipped', name='pool/b', destination='backup/b', reason='Already present')
        live.record_item('success', name='pool/a', destination='backup/a')
        state = live.snapshot()
        self.assertEqual(state['successful_item_count'], 1)
        self.assertEqual(state['failed_item_count'], 0)
        self.assertEqual(state['skipped_item_count'], 1)
        self.assertEqual(state['skipped_items'][0]['reason'], 'Already present')
        self.assertIsNone(state['completed'])

    def test_dataset_lists_and_snapshots_are_detached(self):
        live = self.live()
        rows = [{'source': 'pool/a', 'destination': 'backup/a', 'details': {'note': 'original'}}]
        live.update(successful_items=rows)
        rows[0]['source'] = 'changed'
        state = live.snapshot()
        state['successful_items'][0]['details']['note'] = 'changed'
        self.assertEqual(live.snapshot()['successful_items'][0]['source'], 'pool/a')
        self.assertEqual(live.snapshot()['successful_items'][0]['details']['note'], 'original')

    def test_failed_items_prevent_zero_code_live_success(self):
        live = self.live()
        live.update(total=1, completed=1)
        live.record_item('failure', name='pool/a', reason='Failed')
        live.finish(0)
        self.assertEqual(live.snapshot()['status'], 'incomplete')
        self.assertIs(live.snapshot()['success'], False)

    def test_dataset_input_validation_and_no_updates_after_finish(self):
        live = self.live()
        for rows in ('text', [None], [{'reason': float('nan')}], None):
            with self.subTest(rows=rows), self.assertRaises(ValueError):
                live.update(failed_items=rows)
        with self.assertRaises(ValueError):
            live.record_item('completed', name='pool/a')
        live.finish(0)
        self.assertFalse(live.record_item('success', name='pool/a'))

    def test_background_heartbeat_and_terminal_batch(self):
        live = self.live(enabled=True, host='broker', heartbeat_seconds=0.05,
                         min_publish_interval=0.01, timeout=0.1, expire_after=1)
        captured = []
        def send(messages):
            captured.append(messages)
            return True
        with patch.object(live, '_send', side_effect=send):
            live.start()
            self.assertTrue(wait_for(lambda: len(captured) >= 2))
            live.update(total=4, completed=2)
            live.finish(12, error='failed')
            live.close()
        self.assertEqual(live.last_delivery, 'sent')
        result = [item for batch in captured for item in batch if item['topic'] == live.config.result_topic]
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]['payload']['exit_code'], 12)
        self.assertTrue(result[0]['retain'])
        state = [item for batch in captured for item in batch if item['topic'] == live.config.state_topic]
        self.assertTrue(all(not item['retain'] for item in state))

    def test_updates_are_local_and_coalesced_while_network_is_slow(self):
        live = self.live(enabled=True, host='broker', final_wait=0.05)
        entered, release = Event(), Event()
        captured = []
        def slow(messages):
            entered.set()
            release.wait(1)
            captured.append(messages)
            return True
        with patch.object(live, '_send', side_effect=slow):
            live.start()
            self.assertTrue(entered.wait(1))
            started = time.monotonic()
            for done in range(101):
                live.update(total=100, completed=done)
            self.assertLess(time.monotonic() - started, 0.2)
            release.set()
            live.finish(0)
            live.close()
        self.assertLess(len(captured), 10)

    def test_disabled_dry_run_does_not_start_worker(self):
        live = h.LivePreview(h.LiveConfig(enabled=True, host='broker'), name='Preview', job='preview', dry_run=True)
        with patch.object(h, 'Thread') as thread:
            self.assertFalse(live.start())
            live.finish(0)
        thread.assert_not_called()

    def test_opted_in_dry_run_never_overwrites_retained_last_result(self):
        live = h.LivePreview(h.LiveConfig(enabled=True, host='broker', send_on_dry_run=True),
                             name='Preview', job='preview', dry_run=True)
        batches = []
        with patch.object(live, '_send', side_effect=lambda batch: batches.append(batch) or True):
            live.start()
            live.finish(0)
            live.close()
        self.assertFalse(any(item['topic'] == live.config.result_topic for batch in batches for item in batch))

    def test_actual_worker_isolation_and_final_payload_with_fake_paho(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            package = root / 'paho' / 'mqtt'
            package.mkdir(parents=True)
            (root / 'paho' / '__init__.py').write_text('')
            (package / '__init__.py').write_text('')
            (package / 'publish.py').write_text(
                'import json, os\n'
                'def multiple(messages, **kwargs):\n'
                '    with open(os.environ["LIVE_CAPTURE"], "a") as f:\n'
                '        f.write(json.dumps({"messages": messages, "options": kwargs}) + "\\n")\n')
            capture = root / 'capture.jsonl'
            live = self.live(enabled=True, host='broker', timeout=2, final_wait=1,
                             username='user', password='dummy-secret')
            with patch.dict(os.environ, {'PYTHONPATH': temp, 'LIVE_CAPTURE': str(capture)}):
                live.start()
                self.assertTrue(wait_for(capture.exists))
                live.update(total=2, completed=1)
                live.finish(1, stderr='child failure')
                live.close()
            requests = [json.loads(line) for line in capture.read_text().splitlines()]
            result = [message for request in requests for message in request['messages']
                      if message['topic'] == live.config.result_topic]
            self.assertEqual(len(result), 1)
            self.assertEqual(json.loads(result[0]['payload'])['stderr'], 'child failure')
            self.assertEqual(requests[0]['options']['auth']['username'], 'user')

    def test_real_stalled_worker_is_killed_with_bounded_final_wait(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            package = root / 'paho' / 'mqtt'
            package.mkdir(parents=True)
            (root / 'paho' / '__init__.py').write_text('')
            (package / '__init__.py').write_text('')
            (package / 'publish.py').write_text('import time\ndef multiple(*args, **kwargs): time.sleep(5)\n')
            live = self.live(enabled=True, host='broker', final_wait=0.05, timeout=3)
            with patch.dict(os.environ, {'PYTHONPATH': temp}):
                live.start()
                self.assertTrue(wait_for(lambda: live._process is not None))
                process = live._process
                started = time.monotonic()
                live.finish(0)
                self.assertLess(time.monotonic() - started, 0.3)
                live.close()
                self.assertTrue(wait_for(lambda: process.poll() is not None))

    def test_failed_delivery_does_not_change_job_outcome(self):
        live = self.live(enabled=True, host='broker')
        with patch.object(live, '_send', return_value=False):
            live.start()
            live.finish(12, error='original failure')
            live.close()
        self.assertEqual(live.last_delivery, 'failed')
        self.assertEqual(live.snapshot()['exit_code'], 12)

    def test_frozen_launch_and_tls_worker_hook(self):
        live = self.live(enabled=True, host='broker')
        fake = Mock()
        fake.returncode = 0
        with patch.object(sys, 'frozen', True, create=True), patch.object(h.subprocess, 'Popen', return_value=fake) as popen:
            self.assertTrue(live._send([]))
        self.assertEqual(popen.call_args.args[0], [sys.executable, h.WORKER_FLAG])
        config = h.LiveConfig(enabled=True, host='broker', tls=True, ca_certs='ca', certfile='cert', keyfile='key')
        module = types.ModuleType('paho.mqtt.publish')
        module.multiple = Mock()
        with patch.dict(sys.modules, {'paho.mqtt.publish': module}), patch.object(sys, 'argv', ['app', h.WORKER_FLAG]), patch.object(sys, 'stdin', io.StringIO(json.dumps({'config': asdict(config), 'messages': []}))), patch.object(h.ssl, 'create_default_context') as context:
            with self.assertRaises(SystemExit) as caught:
                h.run_worker_if_requested()
        self.assertEqual(caught.exception.code, 0)
        context.assert_called_once_with(cafile='ca')
        context.return_value.load_cert_chain.assert_called_once_with('cert', 'key')

    def test_module_imports_without_paho_and_uses_python310_syntax(self):
        code = "import sys; sys.modules['paho'] = None; import mqtt_reporting; assert not mqtt_reporting.LiveConfig().enabled"
        result = subprocess.run([sys.executable, '-B', '-c', code], cwd=ROOT,
                                capture_output=True, text=True, timeout=5)
        self.assertEqual(result.returncode, 0, result.stderr)
        for filename in ('mqtt_reporting.py', 'config_loader.py', 'CleanUpInSyncoidSnapshots.py'):
            ast.parse((ROOT / filename).read_text(), feature_version=(3, 10))

"""Offline card rendering against discovery/state generated by the actual module."""
from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
import unittest

try:
    import yaml
    from jinja2 import StrictUndefined
    from jinja2.nativetypes import NativeEnvironment
except ImportError:
    yaml = NativeEnvironment = None

import mqtt_reporting as h


@dataclass
class Entity:
    entity_id: str
    name: str
    state: str
    attributes: dict
    device: str


class FakeHA:
    def __init__(self):
        self.entities = {}
        self.devices = {}

    @property
    def sensor(self):
        return list(self.entities.values())

    def __call__(self, entity_id):
        return self.entities[entity_id].state if entity_id in self.entities else 'unknown'

    def state_attr(self, entity_id, key):
        return self.entities[entity_id].attributes.get(key) if entity_id in self.entities else None

    def device_id(self, entity_id):
        return self.entities[entity_id].device if entity_id in self.entities else None

    def device_attr(self, value, key):
        device = self.device_id(value) or value
        return self.devices.get(device, {}).get(key)

    def device_entities(self, device):
        return [eid for eid, item in self.entities.items() if item.device == device]


@unittest.skipIf(NativeEnvironment is None, 'Card rendering needs optional requirements-test.txt')
class CardTests(unittest.TestCase):
    def setUp(self):
        self.env = NativeEnvironment(undefined=StrictUndefined)
        self.env.filters['bool'] = lambda value: value.lower() in ('true', 'yes', 'on', '1') if isinstance(value, str) else bool(value)
        self.ha = FakeHA()
        self.content = yaml.safe_load((ROOT / 'live-preview-card.yaml').read_text())['content']

    def state(self, outcome='running', run_id='current', unknown=False):
        live = h.LivePreview(h.LiveConfig(), name='NAS backup', job='cleanup', run_id=run_id, job_type='syncoid_snapshot_cleanup', item_unit='datasets', outcome_item_unit='snapshots')
        live.start()
        if not unknown:
            live.update(total=4, completed=3, current_item='pool/current', phase='sending',
                        transferred_bytes=1073741824, bytes_per_second=1048576)
        if outcome == 'failure':
            live.record_item('success', name='pool/a', destination='backup/a')
            live.record_item('failure', name='pool/b', destination='backup/b', reason='Out of space')
            live.record_item('skipped', name='pool/c', destination='backup/c', reason='Already present')
            live.finish(12, error='Receive failed', stderr='cannot receive: out of space <unsafe>')
        elif outcome == 'success':
            live.update(total=4, completed=4)
            live.finish(0)
        elif outcome == 'incomplete':
            live.finish(0, incomplete=True)
        elif outcome == 'interrupted':
            live.finish(130, interrupted=True)
        return live.snapshot()

    def add(self, identity, name='NAS backup', *, live=None, last=None,
            manufacturer='CleanUpInSyncoidSnapshots', expired=False, renamed=False):
        config = h.LiveConfig(device_id=identity, manufacturer=manufacturer)
        device = 'device_' + identity
        self.ha.devices[device] = {'manufacturer': manufacturer, 'name': name}
        for index, item in enumerate(h.discovery_messages(config, name)):
            spec = item['payload']
            payload = last if spec['state_topic'] == config.result_topic else live
            eid = f'sensor.renamed_{identity}_{index}' if renamed else spec['default_entity_id']
            label = f'Renamed field {index}' if renamed else name + ' ' + spec['name']
            attributes = {'friendly_name': label}
            value = 'unknown'
            if payload is not None:
                raw = self.env.from_string(spec['value_template']).render(value_json=payload)
                value = str(raw) if raw is not None else 'unknown'
                if 'json_attributes_template' in spec:
                    data = self.env.from_string(spec['json_attributes_template']).render(value_json=payload)
                    attributes.update(json.loads(data) if isinstance(data, str) else data)
            if expired and spec['state_topic'] == config.state_topic:
                value = 'unavailable'
            self.ha.entities[eid] = Entity(eid, label, value, attributes, device)

    def render(self, manufacturer=None):
        content = self.content
        if manufacturer is not None:
            content = content.replace("{% set manufacturer = 'CleanUpInSyncoidSnapshots' %}",
                                      '{% set manufacturer = ' + repr(manufacturer) + ' %}')
        def as_datetime(value, default=None):
            try:
                return datetime.fromisoformat(value.replace('Z', '+00:00'))
            except (ValueError, TypeError, AttributeError):
                return default
        return str(self.env.from_string(content).render(
            states=self.ha, state_attr=self.ha.state_attr, device_id=self.ha.device_id,
            device_attr=self.ha.device_attr, device_entities=self.ha.device_entities,
            as_datetime=as_datetime, as_local=lambda value: value.astimezone(timezone.utc)))

    def test_yaml_wrapper_preserves_markdown_content(self):
        card = yaml.safe_load((ROOT / 'live-preview-card.yaml').read_text())
        self.assertEqual(card['type'], 'markdown')
        self.assertEqual(card['content'], self.content)

    def test_manufacturer_filter_and_custom_name(self):
        self.add('one', name='Custom manufacturer job', live=self.state(), manufacturer='My Backup Jobs')
        self.add('other', name='Other manufacturer job', live=self.state(), manufacturer='Other')
        self.assertIn('No matching live-preview devices', self.render())
        text = self.render('My Backup Jobs')
        self.assertIn('Custom manufacturer job', text)
        self.assertNotIn('Other manufacturer job', text)
        self.assertIn('**1 job(s) discovered**', text)

    def test_devices_added_automatically_and_deduplicated(self):
        self.add('one', name='First job', live=self.state())
        self.assertIn('**1 job(s) discovered**', self.render())
        self.add('two', name='Second job', live=self.state('success'), last=self.state('success'))
        text = self.render()
        self.assertIn('**2 job(s) discovered**', text)
        self.assertEqual(text.count('First job — RUNNING'), 1)
        self.assertEqual(text.count('Second job — SUCCESS'), 1)

    def test_running_metrics_use_current_state_over_previous_result(self):
        self.add('one', live=self.state(), last=self.state('success', run_id='old'))
        text = self.render()
        self.assertIn('— RUNNING', text)
        self.assertIn('pool/current', text)
        self.assertIn('75.0%', text)
        self.assertIn('**Datasets:** 3 / 4 processed', text)
        self.assertIn('1.00 GiB', text)
        self.assertIn('**Current speed:** 1.00 MiB/s', text)

    def test_expired_terminal_state_uses_retained_result(self):
        state = self.state('success')
        self.add('one', live=state, last=state, expired=True)
        text = self.render()
        self.assertIn('— SUCCESS', text)
        self.assertIn('100%', text.replace('100.0%', '100%'))
        self.assertIn('**Exit code:** 0', text)

    def test_newer_run_with_lost_heartbeat_does_not_claim_old_success(self):
        self.add('one', live=self.state(run_id='new'), last=self.state('success', run_id='old'), expired=True)
        text = self.render()
        self.assertIn('— HEARTBEAT LOST', text)
        self.assertIn('Its outcome is unknown', text)
        self.assertNotIn('— SUCCESS', text)

    def test_first_run_without_retained_result_is_visible(self):
        self.add('one', live=self.state())
        text = self.render()
        self.assertIn('— RUNNING', text)
        self.assertIn('**1 job(s) discovered**', text)

    def test_incomplete_and_interrupted_are_explicit(self):
        for outcome in ('incomplete', 'interrupted'):
            with self.subTest(outcome=outcome):
                self.ha = FakeHA()
                state = self.state(outcome)
                self.add('one', live=state, last=state)
                self.assertIn('— ' + outcome.upper(), self.render())

    def test_unknown_progress_stays_unknown(self):
        self.add('one', live=self.state(unknown=True))
        text = self.render()
        self.assertIn('**Progress:** Unknown', text)
        self.assertIn('**Datasets:** ? / ? processed', text)
        self.assertNotIn('**0.0%**', text)

    def test_snapshot_results_and_stderr_are_formatted(self):
        state = self.state('failure')
        self.add('one', live=state, last=state)
        text = self.render()
        self.assertIn('**Snapshots outcomes:** 1 successful · 1 failed · 1 skipped', text)
        self.assertIn('- pool/a → backup/a', text)
        self.assertIn('- pool/b → backup/b: Out of space', text)
        self.assertIn('- pool/c → backup/c: Already present', text)
        self.assertIn('cannot receive: out of space &lt;unsafe&gt;', text)
        self.assertNotIn('<unsafe>', text)

    def test_renamed_entities_use_role_markers(self):
        state = self.state('failure')
        self.add('one', live=state, last=state, renamed=True)
        text = self.render()
        self.assertIn('— FAILURE', text)
        self.assertIn('**Exit code:** 12', text)
        self.assertIn('75.0%', text)

    def test_empty_registry_shows_setup_instructions(self):
        text = self.render()
        self.assertIn('**0 job(s) discovered**', text)
        self.assertIn('No matching live-preview devices detected', text)



from contextlib import ExitStack
import logging
import CleanUpInSyncoidSnapshots as app
import config_loader as config
import mqtt_notifications as mqtt
from test_project import write_config, arguments, PAHO_AVAILABLE


class IntegrationTests(unittest.TestCase):
    """Real cleanup lifecycle with external ZFS/mail/MQTT effects intercepted."""

    def run_job(self, *, mode='delete', completion=True, live=True, outcome='success',
                reporting_error=False, stderr_text='', datasets_text=None, empty_snapshots=False,
                continue_on_other_failures=True, interrupt_at=None, before_command=None):
        captured, batches, commands, observers = [], [], [], []
        with tempfile.TemporaryDirectory() as temp, ExitStack() as stack:
            folder = Path(temp)
            path = write_config(folder, command=mode, mqtt_enabled=completion, mqtt_on_success=True,
                                continue_on_other_failures=continue_on_other_failures)
            if datasets_text is not None:
                (folder/'datasets.txt').write_text(datasets_text)
            text = path.read_text() + f'\nLiveMQTTEnabled = {str(live).lower()}\nLiveMQTTOnDryRun = true\nLiveManufacturer = "Cleanup tests"\nLiveFinalWaitSeconds = 1\n'
            path.write_text(text)
            old = 'tank/data@syncoid_host_2020-01-01:00:00:00-GMT+00:00'
            middle = 'tank/data@syncoid_host_2021-01-01:00:00:00-GMT+00:00'
            newest = 'tank/data@syncoid_host_2099-01-01:00:00:00-GMT+00:00'
            bad = 'tank/data@syncoid_host_2020-99-01:00:00:00-GMT+00:00'
            ignored = 'tank/data@syncoid_other_2020-01-01:00:00:00-GMT+00:00'
            def command(argv, **kwargs):
                commands.append(argv)
                self.assertEqual(argv[0], 'zfs', 'No other real child command is permitted')
                if before_command is not None:
                    before_command(argv, observers[0].live.snapshot())
                if argv[1] == 'list' and argv[-1] == interrupt_at:
                    raise KeyboardInterrupt()
                if outcome == 'interrupt':
                    raise KeyboardInterrupt()
                if argv[1] == 'list':
                    if outcome == 'list_failure':
                        return subprocess.CompletedProcess(argv, 29, '', stderr_text)
                    return subprocess.CompletedProcess(argv, 0, '' if empty_snapshots else '\n'.join([old, middle, newest, bad, ignored]), stderr_text)
                self.assertEqual(argv[:2], ['zfs', 'destroy'])
                if outcome == 'destroy_failure':
                    return subprocess.CompletedProcess(argv, 23, '', stderr_text)
                return subprocess.CompletedProcess(argv, 0, '', stderr_text)
            def publish(command, *, input, **kwargs):
                captured.append(json.loads(input)['report'])
                if reporting_error:
                    raise subprocess.TimeoutExpired('publisher', 1)
                return subprocess.CompletedProcess(command, 0, '', '')
            real_adapter = h.RunReporting
            def adapter(*args, **kwargs):
                value = real_adapter(*args, **kwargs)
                observers.append(value)
                return value
            stack.enter_context(patch.object(sys, 'argv', ['cleanup', '-c', str(path)]))
            stack.enter_context(patch.object(app.os, 'geteuid', return_value=0))
            stack.enter_context(patch.object(app, 'get_script_log_folder', return_value=str(folder/'logs')))
            stack.enter_context(patch.object(app.subprocess, 'run', side_effect=command))
            stack.enter_context(patch.object(mqtt, '_run_publisher', side_effect=publish))
            stack.enter_context(patch.object(h.LivePreview, '_send', side_effect=lambda batch: batches.append(batch) or not reporting_error))
            stack.enter_context(patch.object(app, 'RunReporting', side_effect=adapter))
            error = None
            try:
                app.main()
            except BaseException as exc:
                error = exc
            for logger in (logging.getLogger('cleanup'), logging.getLogger('cleanupError')):
                for handler in list(logger.handlers):
                    handler.close()
                    logger.removeHandler(handler)
            self.assertFalse(any(folder.glob('*.json')))
            self.assertFalse(any(folder.glob('*.jsonl')))
            observer = observers[0]
            state = observer.live.snapshot() if observer.live else None
        return captured, state, commands, error, batches, observer

    def test_success_has_typed_completion_and_honest_snapshot_counts(self):
        reports, state, commands, error, batches, observer = self.run_job()
        self.assertIsNone(error)
        self.assertEqual([c[1] for c in commands], ['list', 'destroy', 'destroy'])
        report = reports[0]
        self.assertEqual(report['status'], 'success')
        self.assertIs(report['success'], True)
        self.assertIs(type(report['exit_code']), int)
        self.assertEqual(report['name'], report['title'])
        self.assertEqual(report['job'], 'cleanup')
        self.assertEqual(report['run_id'], state['run_id'])
        self.assertEqual(report['host'], state['host'])
        for key in ('timestamp', 'run_id', 'host'):
            self.assertTrue(report[key])
        self.assertTrue(report['warning'])  # Invalid timestamp is logged by the original job.
        self.assertEqual(report['stderr'], '')  # Log text is never fabricated as child stderr.
        self.assertNotIn('failed_datasets', report)
        self.assertEqual(state['job_type'], 'syncoid_snapshot_cleanup')
        self.assertEqual(state['item_unit'], 'datasets')
        self.assertEqual(state['outcome_item_unit'], 'snapshots')
        self.assertEqual((state['completed'], state['total']), (1, 1))
        self.assertEqual(state['details']['snapshots_processed'], 4)
        self.assertEqual((state['successful_item_count'], state['failed_item_count'], state['skipped_item_count']), (2, 0, 2))
        self.assertEqual(state['details']['snapshots_selected'], 2)
        self.assertEqual(state['details']['snapshots_destroyed'], 2)
        self.assertIsNone(state['transferred_bytes'])
        self.assertIsNone(state['bytes_per_second'])
        running = [m['payload'] for b in batches for m in b if m['topic'].endswith('/state') and m['payload']['status'] == 'running']
        self.assertTrue(running)
        self.assertTrue(any(s['total'] is None and s['progress_percent'] is None for s in running))

    def test_destroy_failure_preserves_job_code_child_code_and_actual_stderr_tail(self):
        output = 'real child diagnostic <unsafe>\n' + 'é' * 4100
        reports, state, commands, error, batches, observer = self.run_job(outcome='destroy_failure', stderr_text=output)
        self.assertIsInstance(error, SystemExit)
        self.assertEqual(error.code, 1)  # Existing overall cleanup semantics, not child rc 23.
        report = reports[0]
        self.assertEqual((report['status'], report['success'], report['exit_code']), ('failure', False, 1))
        self.assertEqual(report['stderr'], (output + output)[-4000:])
        self.assertEqual(report['failed_datasets'][0]['exit_code'], 23)
        self.assertEqual(state['failed_items'][0]['exit_code'], 23)
        self.assertEqual((state['completed'], state['total']), (1, 1))
        self.assertEqual(state['progress_percent'], 100)  # The one dataset was attempted, and failed.
        self.assertEqual(state['details']['snapshots_processed'], 3)
        self.assertEqual([c[1] for c in commands], ['list', 'destroy'])
        self.assertEqual(state['stderr'], report['stderr'])

    def test_failed_listing_and_interrupt_never_invent_totals_or_success(self):
        for outcome,code,status in (('list_failure',1,'failure'), ('interrupt',130,'interrupted')):
            with self.subTest(outcome=outcome):
                reports,state,commands,error,batches,observer=self.run_job(outcome=outcome,stderr_text='real list error')
                self.assertEqual(reports[0]['exit_code'],code)
                self.assertFalse(reports[0]['success'])
                self.assertEqual(state['status'],status)
                self.assertEqual(state['total'], 1)
                self.assertEqual(state['completed'], 1 if outcome == 'list_failure' else 0)
                self.assertEqual(state['progress_percent'], 100 if outcome == 'list_failure' else 0)
                self.assertTrue(all(c[1]=='list' for c in commands))

    def test_completion_and_live_are_independent_in_all_enablement_combinations(self):
        for completion in (False,True):
            for live in (False,True):
                with self.subTest(completion=completion,live=live):
                    reports,state,commands,error,batches,observer=self.run_job(completion=completion,live=live)
                    self.assertIsNone(error)
                    self.assertEqual(bool(reports),completion)
                    self.assertEqual(bool(batches),live)
                    self.assertEqual(state is not None,live)

    def test_dry_run_skips_snapshot_destruction_and_preserves_last_real_result(self):
        reports,state,commands,error,batches,observer=self.run_job(mode='dry-run')
        self.assertIsNone(error)
        self.assertTrue(reports[0]['dry_run'])
        self.assertIs(type(reports[0]['dry_run']),bool)
        self.assertTrue(all(c[1]=='list' for c in commands))
        self.assertEqual(state['successful_item_count'],0)
        self.assertEqual(state['skipped_item_count'],4)
        self.assertFalse(any(m['topic'].endswith('/last_result') for b in batches for m in b))
        self.assertEqual(reports[0]['dry_run_report']['snapshots_would_delete'],2)

    def test_broker_failures_never_replace_actual_success_or_failure(self):
        for outcome in ('success','destroy_failure'):
            with self.subTest(outcome=outcome):
                reports,state,commands,error,batches,observer=self.run_job(outcome=outcome,reporting_error=True)
                self.assertEqual(state['exit_code'],0 if outcome=='success' else 1)
                self.assertEqual(observer.live.last_delivery,'failed')
                if outcome=='success':self.assertIsNone(error)
                else:self.assertEqual(error.code,1)

    def test_arbitrary_system_exit_is_preserved_even_when_reporting_raises(self):
        with tempfile.TemporaryDirectory() as temp:
            path=write_config(Path(temp),mqtt_enabled=True)
            with patch.object(sys,'argv',['cleanup','-c',str(path)]), patch.object(app,'run_cleanup',side_effect=SystemExit(37)), patch.object(app,'build_mqtt_report',side_effect=RuntimeError('report broken')):
                with self.assertRaises(SystemExit) as caught:app.main()
            self.assertEqual(caught.exception.code,37)

    def test_real_run_cmd_stderr_on_success_and_mail_stderr_are_captured_verbatim(self):
        args=arguments()
        args.reporting_name='Cleanup';args.live_config=None
        observer=h.RunReporting(args,'test')
        observer.start()
        try:
            with patch.object(app.subprocess,'run',return_value=subprocess.CompletedProcess(['zfs'],0,'output','  actual stderr\n')):
                app.run_cmd(['zfs','list'])
            child=Mock(returncode=0)
            child.communicate.return_value=(None,b'mail diagnostic\n')
            with patch.object(app.subprocess,'Popen',return_value=child):
                app.send_mail('Test','body','nobody@example.invalid')
            self.assertEqual(observer.stderr,'  actual stderr\nmail diagnostic\n')
        finally:observer.finish(0,None,False)

    def test_canonical_options_legacy_aliases_and_non_mqtt_sections(self):
        with tempfile.TemporaryDirectory() as temp:
            folder=Path(temp);path=write_config(folder,mqtt_enabled=True)
            old=config.load_config(path,'fallback')
            path.write_text(path.read_text()+'\nMQTT_JSON_Status = false\nLiveMQTTEnabled = true\nLiveBackupName = "Fallback"\n')
            loaded=config.load_config(path,'fallback')
            self.assertIsNone(loaded.mqtt_config)
            self.assertTrue(loaded.live_config.enabled)
            self.assertEqual(loaded.live_config.host,old.mqtt_config['host'])
            self.assertEqual(loaded.datasets_file,old.datasets_file)
            self.assertEqual(loaded.older_than,old.older_than)
            self.assertEqual(loaded.retain_count,old.retain_count)
        baseline=Path(__file__).parents[3]/'original/CleanUpInSyncoidSnapshots-CleanUpInSyncoidSnapshots-Next/config-example.toml'
        # Distributed configs are complete, identical, safe, and keep the topic.
        self.assertEqual((ROOT/'config.toml').read_bytes(),(ROOT/'config-example.toml').read_bytes())
        current=config.tomllib.loads((ROOT/'config.toml').read_text())
        self.assertEqual(current['mqtt']['mqtt_json_topic'],'homeassistant/CleanUpInSyncoidSnapshots/Zotac-RI531/status')
        self.assertFalse(current['mqtt']['MQTT_JSON_Status'])
        self.assertFalse(current['mqtt']['LiveMQTTEnabled'])

    def test_generic_completion_has_no_dataset_fields_and_rejects_inconsistent_types(self):
        report=h.build_report(name='Task job',job='tasks',exit_code=0)
        self.assertFalse(any('dataset' in k for k in report))
        for field,value in (('exit_code',True),('success','true'),('status','failed'),('warning',1),('dry_run','false')):
            broken=dict(report,**{field:value})
            with self.subTest(field=field),self.assertRaises(ValueError):h.encode_report(broken)
        self.assertEqual(h.build_report(name='Task',job='tasks',exit_code=-9)['exit_code'],-9)
        self.assertEqual(mqtt.build_mqtt_report(arguments(),'test',1,app.CommandError(['zfs'],9,'stdout only',''))['stderr'],'')

    def test_no_new_application_commands_or_scheduling_and_worker_hook_is_private(self):
        loaded=Mock()
        with patch.object(sys,'argv',['cleanup',h.WORKER_FLAG]),patch.object(app,'run_worker_if_requested',side_effect=SystemExit(0)),patch.object(app,'run_cleanup') as cleanup:
            with self.assertRaises(SystemExit):app.main()
        cleanup.assert_not_called()
        with patch.object(sys,'argv',['cleanup','--version']),patch.object(sys,'stdout',io.StringIO()) as stream:
            with self.assertRaises(SystemExit):app.main()
        self.assertIn('0.0.19',stream.getvalue())


@unittest.skipIf(NativeEnvironment is None,'YAML/Jinja rendering dependencies unavailable')
class AutomationTests(unittest.TestCase):
    def setUp(self):
        self.spec=yaml.safe_load((ROOT/'success-failure-automation.yaml').read_text())
        self.env=NativeEnvironment(undefined=StrictUndefined)
        self.env.filters['bool']=lambda x,default=False: x.lower() in ('true','on','yes','1') if isinstance(x,str) else bool(x)

    def test_topic_guards_pushover_limits_and_actual_completion_payload(self):
        self.assertEqual(self.spec['triggers'][0]['topic'],'homeassistant/CleanUpInSyncoidSnapshots/Zotac-RI531/status')
        actions=self.spec['actions']
        self.assertIn('stop',actions[1]['then'][0])
        self.assertIn('condition',actions[3])
        self.assertEqual(actions[-1]['action'],'notify.pushover')
        for code in (0,37):
            for huge in (False,True):
                report=h.build_report(name='Cleanup'*100 if huge else 'NAS cleanup',job='cleanup',exit_code=code,warning=True,stderr_text='real stderr 🧪\n'*1000,error_message='original error'*100)
                ctx={'report':report}
                for action in actions:
                    if 'variables' in action:
                        for key,template in action['variables'].items():
                            if key=='report':continue
                            ctx[key]=self.env.from_string(template).render(**ctx)
                self.assertTrue(ctx['valid_report'])
                self.assertLessEqual(len(str(ctx['notice_title'])),250)
                self.assertLessEqual(len(str(ctx['notice_message'])),1024)
                self.assertIn('Stderr',ctx['notice_message'])
                self.assertIn('Exit code',ctx['notice_message'])
                self.assertIn('Warning',ctx['notice_message'])
        guard=actions[1]['if'][0]['value_template']
        report=h.build_report(name='Preview',job='cleanup',exit_code=0,dry_run=True)
        self.assertTrue(self.env.from_string(guard).render(report=report))
        validity=actions[2]['variables']['valid_report']
        for changes in ({'success':True,'exit_code':2},{'exit_code':True},{'status':'failed'}):
            bad=dict(report,**changes)
            self.assertFalse(self.env.from_string(validity).render(report=bad))

    def test_generic_card_hides_dataset_details_and_unmeasured_transfer(self):
        fixture=CardTests();fixture.setUp()
        live=h.LivePreview(h.LiveConfig(),job='task',name='Packages',job_type='package_update',item_unit='packages')
        live.start();live.record_item('skipped',name='package-one',reason='Already current')
        state=live.snapshot();fixture.add('packages',name='Package job',live=state)
        text=fixture.render()
        self.assertIn('**Packages:**',text)
        self.assertIn('Already current',text)
        self.assertNotIn('**Dataset scan:**',text)
        self.assertNotIn('**Transferred:**',text)
        self.assertIn('**Progress:** Unknown',text)



@unittest.skipUnless(PAHO_AVAILABLE, "optional paho-mqtt dependency is not installed")
class LiveBrokerTests(unittest.TestCase):
    def exchange(self, reject=False):
        """Only an ephemeral loopback listener receives these discovery/state packets."""
        import socket
        from threading import Thread
        from test_project import receive_packet
        captured=[];failures=[];stop=Event()
        listener=socket.socket();listener.bind(('127.0.0.1',0));listener.listen(4);listener.settimeout(.1)
        port=listener.getsockname()[1]
        def serve():
            with listener:
                while not stop.is_set():
                    try:connection,_=listener.accept()
                    except socket.timeout:continue
                    try:
                        with connection:
                            connection.settimeout(2)
                            receive_packet(connection)
                            connection.sendall(b'\x20\x02\x00\x05' if reject else b'\x20\x02\x00\x00')
                            if reject:continue
                            while True:
                                header,data=receive_packet(connection)
                                if header>>4==14:break
                                if header>>4!=3:raise AssertionError('Unexpected MQTT packet')
                                size=int.from_bytes(data[:2],'big');topic=data[2:2+size].decode();rest=data[2+size:]
                                self.assertEqual((header>>1)&3,1)
                                captured.append({'topic':topic,'payload':json.loads(rest[2:]),'retain':bool(header&1)})
                                connection.sendall(b'\x40\x02'+rest[:2])
                    except EOFError:pass
                    except Exception as exc:failures.append(exc)
        thread=Thread(target=serve,daemon=True);thread.start()
        cfg=h.LiveConfig(enabled=True,host='127.0.0.1',port=port,device_id='cleanup_test',manufacturer='Test Manufacturer',
                         heartbeat_seconds=.05,min_publish_interval=.01,timeout=1,expire_after=2,final_wait=1,notify_start=True)
        live=h.LivePreview(cfg,job='cleanup',name='Snapshot cleanup',job_type='syncoid_snapshot_cleanup',item_unit='snapshots')
        try:
            live.start()
            self.assertTrue(wait_for(lambda:live.last_delivery!='not_started'))
            live.update(completed=1,total=2)
            live.finish(12,error='Actual test failure',stderr='captured worker stderr')
            live.close()
        finally:
            stop.set();thread.join(3)
        self.assertFalse(thread.is_alive());self.assertEqual(failures,[])
        return live,captured

    def test_real_paho_live_discovery_state_result_and_event_routing(self):
        live,messages=self.exchange()
        self.assertEqual(live.last_delivery,'sent')
        discovery=[m for m in messages if m['topic'].endswith('/config')]
        self.assertTrue(discovery)
        self.assertTrue(all(m['retain'] and m['payload']['device']['manufacturer']=='Test Manufacturer' for m in discovery))
        results=[m for m in messages if m['topic'].endswith('/last_result')]
        self.assertEqual(len(results),1)
        self.assertTrue(results[0]['retain'])
        self.assertEqual(results[0]['payload']['progress_percent'],50)
        self.assertEqual(results[0]['payload']['exit_code'],12)
        self.assertTrue(all(not m['retain'] for m in messages if m['topic'].endswith(('/state','/events'))))
        self.assertTrue(all(m['topic']!='homeassistant/CleanUpInSyncoidSnapshots/Zotac-RI531/status' for m in messages))

    def test_real_live_broker_rejection_preserves_job_code(self):
        live,messages=self.exchange(reject=True)
        self.assertEqual(live.last_delivery,'failed')
        self.assertEqual(live.snapshot()['exit_code'],12)
        self.assertEqual(messages,[])


class IndependenceEdgeTests(unittest.TestCase):
    def test_live_only_does_not_require_or_validate_a_completion_topic(self):
        with tempfile.TemporaryDirectory() as temp:
            path=write_config(Path(temp),mqtt_enabled=False)
            text=path.read_text().replace('topic = "test/cleanup/status"\n','')
            path.write_text(text+'\nLiveMQTTEnabled = true\nSendMQTTOnSuccess = false\n')
            loaded=config.load_config(path,'cleanup')
            self.assertIsNone(loaded.mqtt_config)
            self.assertTrue(loaded.live_config.enabled)
            self.assertTrue(loaded.live_config.notify_success)
            self.assertNotIn('test/cleanup/status',loaded.live_config.state_topic)

    def test_live_event_and_discovery_switches_do_not_suppress_state_or_result(self):
        cfg=h.LiveConfig(enabled=True,host='broker',discovery=False,
                         notify_start=False,notify_success=False,notify_failure=False)
        for code in (0,12):
            batches=[];live=h.LivePreview(cfg,job='cleanup')
            with patch.object(live,'_send',side_effect=lambda batch:batches.append(batch) or True):
                live.start();live.finish(code);live.close()
            messages=[m for batch in batches for m in batch]
            self.assertTrue(any(m['topic']==cfg.state_topic for m in messages))
            self.assertTrue(any(m['topic']==cfg.result_topic for m in messages))
            self.assertFalse(any(m['topic']==cfg.events_topic or m['topic'].endswith('/config') for m in messages))

    def test_completion_dry_run_switch_never_suppresses_live_or_starts_its_worker(self):
        cfg=dict(mqtt.DEFAULTS,host='broker',topic='completion',on_success=True,send_on_dry_run=False)
        report=mqtt.build_mqtt_report(arguments(command='dry-run'),'test',1,error=RuntimeError('test failure'))
        with patch.object(mqtt,'_run_publisher') as publish:
            mqtt.notify_mqtt(cfg,report)
        publish.assert_not_called()


class DatasetFileProgressTests(unittest.TestCase):
    def run_job(self, **kwargs):
        return IntegrationTests().run_job(**kwargs)

    def test_five_entries_show_two_of_five_before_third_dataset_in_both_modes(self):
        text='tank/one\n\n  tank/two  \ntank/three\n  \ntank/four\ntank/five\n'
        for mode in ('delete','dry-run'):
            seen=[]
            reports,state,commands,error,batches,observer=self.run_job(mode=mode,datasets_text=text,empty_snapshots=True,
                    before_command=lambda cmd,progress:seen.append((cmd,progress)))
            self.assertIsNone(error)
            self.assertEqual(len(commands),5)
            third=seen[2][1]
            self.assertEqual((third['completed'],third['total']),(2,5))
            self.assertEqual(third['progress_percent'],40)
            self.assertEqual(third['details']['current_dataset_index'],3)
            self.assertEqual(third['details']['current_dataset'],'tank/three')
            self.assertEqual((state['completed'],state['total']),(5,5))
            self.assertEqual(state['successful_item_count'],0)  # No snapshots are needed to advance dataset progress.
            self.assertEqual(reports[0]['item_unit'],'datasets')
            self.assertEqual(reports[0]['outcome_item_unit'],'snapshots')

    def test_failed_entries_advance_position_without_becoming_successful(self):
        text='\n'.join('tank/'+str(i) for i in range(5))+'\n'
        reports,state,commands,error,batches,observer=self.run_job(datasets_text=text,outcome='list_failure')
        self.assertEqual(error.code,1)
        self.assertFalse(reports[0]['success'])
        self.assertEqual((state['completed'],state['total']),(5,5))
        self.assertEqual(state['details']['dataset_failures'],5)
        self.assertEqual(state['details']['datasets_completed'],0)
        self.assertEqual(state['status'],'failure')

    def test_stopped_failure_and_midfile_interrupt_leave_remaining_entries_unprocessed(self):
        text='tank/one\ntank/two\ntank/three\ntank/four\ntank/five\n'
        reports,state,commands,error,batches,observer=self.run_job(datasets_text=text,outcome='list_failure',continue_on_other_failures=False)
        self.assertIsInstance(error,app.DatasetFailuresError)
        self.assertEqual((state['completed'],state['total']),(1,5))
        self.assertEqual(state['progress_percent'],20)
        reports,state,commands,error,batches,observer=self.run_job(datasets_text=text,empty_snapshots=True,interrupt_at='tank/three')
        self.assertIsInstance(error,KeyboardInterrupt)
        self.assertEqual((state['completed'],state['total']),(2,5))
        self.assertEqual(state['details']['current_dataset_index'],3)
        self.assertEqual(state['status'],'interrupted')
        self.assertEqual(state['progress_percent'],40)

    def test_duplicate_entries_and_empty_file_use_exact_existing_input_rules(self):
        for text,total in (('tank/repeated\n\ntank/repeated\n',2),(' \n\n',0)):
            reports,state,commands,error,batches,observer=self.run_job(datasets_text=text,empty_snapshots=True)
            self.assertIsNone(error)
            self.assertEqual((state['completed'],state['total']),(total,total))
            self.assertEqual(len(commands),total)
            if total==0:self.assertIsNone(state['progress_percent'])

    def test_card_renders_dataset_ratio_and_separate_snapshot_outcomes(self):
        fixture=CardTests();fixture.setUp()
        live=h.LivePreview(h.LiveConfig(),job='cleanup',name='NAS',job_type='syncoid_snapshot_cleanup',
                           item_unit='datasets',outcome_item_unit='snapshots')
        live.start();live.update(completed=2,total=5,details={'datasets_completed':1,'dataset_failures':1,
                              'current_dataset':'tank/three','current_dataset_index':3})
        live.record_item('skipped',name='tank/one@snap',reason='Protected by retention')
        fixture.add('ratio',name='Dataset cleanup',live=live.snapshot(),renamed=True)
        text=fixture.render()
        self.assertIn('**Datasets:** 2 / 5 processed',text)
        self.assertIn('position 3 / 5',text)
        self.assertIn('**Snapshots outcomes:** 0 successful · 0 failed · 1 skipped',text)
        self.assertIn('40.0%',text)
        self.assertNotIn('Successful datasets',text)


if __name__ == '__main__':
    unittest.main()
