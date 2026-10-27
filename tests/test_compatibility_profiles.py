"""Check supplied automation topic and manufacturer recognition across job configs."""
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from modules.config_loader import SECTION_KEYS, load_config
from modules.ha_live_preview import LivePreview
import test_manufacturer_card as cards


class ProfileTests(unittest.TestCase):
    def test_ubuntu_profile_is_complete_safe_and_matches_supplied_cleanup_topic(self):
        path = ROOT / 'config-ubuntu-zfs-import-example.json'
        cfg = json.loads(path.read_text())
        self.assertEqual(set(cfg), set(SECTION_KEYS) - {'mqtt'})
        for section, values in cfg.items():
            self.assertEqual(set(values), SECTION_KEYS[section])
        args = load_config(path, 'cleanup')
        self.assertTrue(args.dry_run)
        self.assertIsNone(args.mqtt_config)
        self.assertFalse(args.live_config.enabled)
        self.assertFalse(cfg['completion']['send_on_dry_run'])
        self.assertTrue(cfg['completion']['on_success'])
        self.assertEqual(cfg['completion']['topic'],
                         'homeassistant/CleanUpInSyncoidSnapshots/Ubuntu-ZFS-Import/status')
        self.assertEqual(args.live_config.manufacturer, 'CleanUpInSyncoidSnapshots')

    def test_enabling_completion_does_not_enable_live_or_change_the_topic(self):
        with tempfile.TemporaryDirectory() as directory:
            cfg = json.loads((ROOT / 'config-ubuntu-zfs-import-example.json').read_text())
            cfg['completion']['enabled'] = True
            path = Path(directory) / 'config.json'
            path.write_text(json.dumps(cfg))
            args = load_config(path, 'cleanup')
        self.assertEqual(args.mqtt_config['topic'], cfg['completion']['topic'])
        self.assertFalse(args.live_config.enabled)
        self.assertTrue(args.mqtt_config['on_success'])
        self.assertFalse(args.mqtt_config['send_on_dry_run'])

    @unittest.skipIf(cards.NativeEnvironment is None, 'Install requirements-test.txt for HA rendering')
    def test_both_profiles_are_found_by_manufacturer_after_entity_renaming(self):
        fixture = cards.CardTests()
        fixture.setUp()
        for index, name in enumerate(('config-example.json', 'config-ubuntu-zfs-import-example.json')):
            args = load_config(ROOT / name, 'cleanup')
            monitor = LivePreview(args.live_config, name='Custom cleanup ' + str(index), job=args.log_prefix)
            monitor.start()
            monitor.update(total=3, completed=1, current_item='tank/data')
            state = monitor.snapshot()
            fixture.add(args.live_config.device_id, name='Custom cleanup ' + str(index),
                        live=state, manufacturer=args.live_config.manufacturer, renamed=True)
            monitor.close()
        # A script-like device name must not bypass the manufacturer filter.
        fixture.add('other_script', name='CleanUpInSyncoidSnapshots',
                    live=state, manufacturer='Other script')
        text = fixture.render()
        self.assertIn('**2 job(s) discovered**', text)
        self.assertIn('Custom cleanup 0', text)
        self.assertIn('Custom cleanup 1', text)
        self.assertIn('33.3%', text)
        self.assertNotIn('**3 job(s) discovered**', text)


if __name__ == '__main__':
    unittest.main()
