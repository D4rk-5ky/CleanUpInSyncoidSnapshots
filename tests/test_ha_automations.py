"""Feed real cleanup JSON through the delivered HA automation/card templates."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from modules.config_loader import load_config
from modules.ha_live_preview import LivePreview, discovery_messages
import CleanUpInSyncoidSnapshots as app
import test_template_integration as integration

try:
    import yaml
    from jinja2.nativetypes import NativeEnvironment
except ImportError:
    yaml = NativeEnvironment = None


@unittest.skipIf(NativeEnvironment is None, 'Install requirements-test.txt for HA template checks')
class AutomationTests(unittest.TestCase):
    def setUp(self):
        self.env = NativeEnvironment()
        self.env.filters['bool'] = lambda value: value.lower() in ('true', 'yes', 'on', '1') if isinstance(value, str) else bool(value)
        self.automation = yaml.safe_load((ROOT / 'home-assistant/CleanUpInSyncoidSnapshots-mqtt-automation.yaml').read_text())
        # Compose rather than load to preserve the blueprint's custom !input tags.
        doc = yaml.compose((ROOT / 'home-assistant/CleanUpInSyncoidSnapshots-mqtt-persistent-notification.yaml').read_text())
        conditions = next(value for key, value in doc.value if key.value == 'conditions')
        self.blueprint_guard = next(value.value for key, value in conditions.value[0].value if key.value == 'value_template')

    def routes(self, report):
        return [bool(self.env.from_string(branch['conditions'][0]['value_template']).render(report=report))
                for branch in self.automation['actions'][2]['choose']]

    def test_actual_cleanup_success_and_failure_route_into_ha_automations(self):
        for failed in (False, True):
            with self.subTest(failed=failed):
                error = app.CommandError(['zfs', 'list', 'tank/a'], 1, '', 'dataset does not exist') if failed else None
                _, _, notify, _, caught = integration.LifecycleTests().invoke(effect=error)
                report = notify.call_args.args[1]
                # Simulate the MQTT JSON encoding/decoding step, preserving boolean types.
                report = json.loads(json.dumps(report))
                self.assertEqual(report['status'], 'failure' if failed else 'success')
                self.assertIs(report['success'], not failed)
                self.assertIs(type(report['exit_code']), int)
                self.assertEqual(self.routes(report), [not failed, failed])
                self.assertTrue(self.env.from_string(self.blueprint_guard).render(trigger={'payload_json': report}))
                self.assertEqual(report['version'], app.__version__)
                if failed:
                    self.assertIsNotNone(caught)
                    self.assertIn('dataset does not exist', report['stderr'])

    def test_inconsistent_or_live_payloads_cannot_take_success_or_failure_branch(self):
        _, _, notify, _, _ = integration.LifecycleTests().invoke()
        good = notify.call_args.args[1]
        for change in ({'success': False}, {'exit_code': True}, {'exit_code': '0'},
                       {'status': 'running', 'exit_code': None, 'success': None}, {'status': 'failure'}):
            with self.subTest(change=change):
                report = {**good, **change}
                self.assertEqual(self.routes(report), [False, False])
                self.assertFalse(self.env.from_string(self.blueprint_guard).render(trigger={'payload_json': report}))

    def test_example_completion_topic_matches_both_automation_files(self):
        config = json.loads((ROOT / 'config-example.json').read_text())
        topic = config['completion']['topic']
        self.assertEqual(self.automation['triggers'][0]['topic'], topic)
        source = (ROOT / 'home-assistant/CleanUpInSyncoidSnapshots-mqtt-persistent-notification.yaml').read_text()
        self.assertIn('default: ' + topic, source)
        gate = self.automation['actions'][1]['if'][0]['value_template']
        self.assertTrue(self.env.from_string(gate).render(report={'dry_run': True}))
        self.assertFalse(self.env.from_string(gate).render(report={'dry_run': False}))

    def test_app_manufacturer_default_and_full_attributes_feed_automatic_card(self):
        with tempfile.TemporaryDirectory() as directory:
            cfg = json.loads((ROOT / 'config-example.json').read_text())
            cfg['live'].pop('manufacturer')
            cfg['live'].pop('device_id')
            path = Path(directory) / 'config.json'
            path.write_text(json.dumps(cfg))
            args = load_config(path, 'cleanup')
        self.assertEqual(args.live_config.manufacturer, 'CleanUpInSyncoidSnapshots')
        monitor = LivePreview(args.live_config, name='CleanUpInSyncoidSnapshots', job='cleanup')
        monitor.start()
        monitor.update(total=2, completed=1, current_item='tank/a', phase='listing_snapshots')
        payload = monitor.snapshot()
        self.assertEqual(payload['manufacturer'], 'CleanUpInSyncoidSnapshots')
        messages = discovery_messages(args.live_config, monitor.name)
        self.assertTrue(all(item['payload']['device']['manufacturer'] == payload['manufacturer'] for item in messages))
        aggregates = [item['payload'] for item in messages if 'json_attributes_template' in item['payload']]
        self.assertEqual(len(aggregates), 2)
        for spec in aggregates:
            attributes = self.env.from_string(spec['json_attributes_template']).render(value_json=payload)
            if isinstance(attributes, str):
                attributes = json.loads(attributes)
            self.assertEqual(attributes['completed'], 1)
            self.assertEqual(attributes['total'], 2)
            self.assertEqual(attributes['progress_percent'], 50)
            self.assertEqual(attributes['current_item'], 'tank/a')
            self.assertIn(attributes['live_preview_role'], ('status', 'last_result'))
        card = yaml.safe_load((ROOT / 'home-assistant/manufacturer-live-preview-card.yaml').read_text())
        self.assertIn("{% set manufacturer = 'CleanUpInSyncoidSnapshots' %}", card['content'])
        self.assertNotIn('sensor.job_live_cleanup_syncoid_snapshots_', card['content'])
        monitor.close()


if __name__ == '__main__':
    unittest.main()
