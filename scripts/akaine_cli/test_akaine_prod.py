"""Production bridge identity and response guards, using the existing fake device."""
import json
import unittest

import akaine_prod as prod
import akaine_stag as staging
from test_akaine_stag import FakeAdb


class ProductionClientTests(unittest.TestCase):
    def device(self):
        device = FakeAdb()
        device.metadata['environment'] = 'production'
        device.files['bridge.json'] = json.dumps(device.metadata).encode()
        device.response_environment = 'production'
        return device

    def client(self, device):
        return prod.Client(prod.Adb('fixture-adb', 'emulator-5556', device.run), 10,
                           device.clock, device.clock.sleep)

    def test_production_metadata_and_response_succeed(self):
        device = self.device()
        result = self.client(device).execute('status')
        self.assertTrue(result['ok'])
        self.assertEqual(result['environment'], 'production')
        self.assertFalse(device.locked)

    def test_staging_metadata_rejected_before_lock_or_request(self):
        device = FakeAdb()
        result = self.client(device).execute('category', '8')
        self.assertEqual(result['error']['code'], 'NOT_PRODUCTION')
        self.assertFalse(device.locked)
        self.assertFalse(device.requests)

    def test_staging_response_rejected_without_retry(self):
        device = self.device()
        device.response_environment = 'staging'
        result = self.client(device).execute('category', '8')
        self.assertEqual(result['error']['code'], 'PROTOCOL_ERROR')
        self.assertTrue(result['error']['outcome_unknown'])
        self.assertEqual(len(device.requests), 1)

    def test_original_staging_client_still_rejects_production(self):
        device = self.device()
        result = staging.Client(staging.Adb('fixture-adb', 'emulator-5556', device.run),
                                10, device.clock, device.clock.sleep).execute('status')
        self.assertEqual(result['error']['code'], 'NOT_STAGING')
        self.assertFalse(device.requests)

    def test_production_source_changes_only_environment_labels(self):
        from pathlib import Path
        source = Path(staging.__file__).read_bytes()
        self.assertEqual(Path(prod.__file__).read_bytes(), source.replace(b'staging', b'production').replace(b'NOT_STAGING', b'NOT_PRODUCTION'))


if __name__ == '__main__':
    unittest.main()
