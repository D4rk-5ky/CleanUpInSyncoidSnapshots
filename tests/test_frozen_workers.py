"""Real frozen worker routing against a local fake MQTT broker; no cleanup."""
from dataclasses import asdict
import json
from pathlib import Path
import socket
import subprocess
import sys
import threading
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from modules.ha_live_preview import LiveConfig, LivePreview, discovery_messages
from modules.mqtt_status import MQTTConfig, build_report

BINARY = ROOT / 'dist/CleanUpInSyncoidSnapshots'


def packet(connection):
    def take(count):
        data = b''
        while len(data) < count:
            chunk = connection.recv(count - len(data))
            if not chunk:
                raise EOFError('MQTT connection closed mid-packet')
            data += chunk
        return data
    header = take(1)[0]
    size, multiplier = 0, 1
    for _ in range(4):
        value = take(1)[0]
        size += (value & 127) * multiplier
        if value < 128:
            return header, take(size)
        multiplier *= 128
    raise ValueError('Invalid packet size')


@unittest.skipUnless(BINARY.is_file(), 'build the optional frozen executable first')
class FrozenWorkerTests(unittest.TestCase):
    def exchange(self, flag, make_request):
        listener = socket.socket()
        listener.bind(('127.0.0.1', 0))
        listener.listen(1)
        listener.settimeout(8)
        received, errors = [], []
        def serve():
            try:
                with listener, listener.accept()[0] as connection:
                    connection.settimeout(8)
                    header, _ = packet(connection)
                    assert header == 0x10
                    connection.sendall(b'\x20\x02\x00\x00')
                    while True:
                        header, data = packet(connection)
                        if header == 0xe0:
                            return
                        assert header & 0xf0 == 0x30
                        size = int.from_bytes(data[:2], 'big')
                        topic, rest = data[2:2 + size].decode(), data[2 + size:]
                        qos = (header >> 1) & 3
                        mid, payload = (rest[:2], rest[2:]) if qos else (b'', rest)
                        received.append({'topic': topic, 'payload': json.loads(payload),
                                         'retain': bool(header & 1), 'qos': qos})
                        if qos == 1:
                            connection.sendall(b'\x40\x02' + mid)
            except Exception as exc:
                errors.append(str(exc))
        worker = threading.Thread(target=serve, daemon=True)
        worker.start()
        request = make_request(listener.getsockname()[1])
        result = subprocess.run([str(BINARY), flag], input=json.dumps(request),
                                text=True, capture_output=True, timeout=12)
        worker.join(9)
        self.assertFalse(worker.is_alive())
        self.assertEqual(errors, [])
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, '')
        self.assertNotIn('test-password', result.stderr)
        return received

    def test_frozen_completion_worker_publishes_valid_nonretained_report(self):
        report = build_report(name='CleanUpInSyncoidSnapshots', job='cleanup', exit_code=1,
                              error_message='Example failure', stderr_text='Example ZFS stderr')
        def request(port):
            config = MQTTConfig(enabled=True, host='127.0.0.1', port=port, qos=1,
                                username='test-user', password='test-password', topic='tests/cleanup/status')
            return {'config': asdict(config), 'report': report}
        received = self.exchange('--mqtt-status-worker', request)
        self.assertEqual(len(received), 1)
        self.assertFalse(received[0]['retain'])
        self.assertEqual(received[0]['payload'], report)

    def test_frozen_live_worker_publishes_discovery_state_and_result(self):
        def request(port):
            config = LiveConfig(enabled=True, host='127.0.0.1', port=port, device_id='cleanup_test',
                                username='test-user', password='test-password')
            monitor = LivePreview(LiveConfig(), name='CleanUpInSyncoidSnapshots', job='cleanup')
            monitor.start()
            monitor.update(total=1, completed=1)
            monitor.record_dataset('success', source='tank/data')
            monitor.finish(0)
            state = monitor.snapshot()
            messages = discovery_messages(config, 'CleanUpInSyncoidSnapshots', '0.0.16')
            messages.extend([
                {'topic': config.state_topic, 'payload': state, 'qos': 1, 'retain': False},
                {'topic': config.result_topic, 'payload': state, 'qos': 1, 'retain': True},
            ])
            return {'config': asdict(config), 'messages': messages}
        received = self.exchange('--ha-live-preview-worker', request)
        self.assertEqual(len(received), 16)
        self.assertTrue(all(item['retain'] for item in received[:14]))
        self.assertFalse(received[-2]['retain'])
        self.assertTrue(received[-1]['retain'])
        self.assertEqual(received[-1]['payload']['status'], 'success')
        self.assertEqual(received[-1]['payload']['successful_dataset_count'], 1)

    def test_invalid_private_requests_exit_before_cleanup(self):
        for flag in ('--mqtt-status-worker', '--ha-live-preview-worker'):
            result = subprocess.run([str(BINARY), flag], input='{}', text=True,
                                    capture_output=True, timeout=8)
            self.assertEqual(result.returncode, 1)
            self.assertEqual(result.stdout, '')
            self.assertEqual(result.stderr, '')


if __name__ == '__main__':
    unittest.main()
