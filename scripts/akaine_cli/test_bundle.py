import contextlib
import io
import unittest
from unittest.mock import patch

import akaine_stag as cli
from test_akaine_stag import FakeAdb


class BundleTests(unittest.TestCase):
    @staticmethod
    def state(phase='confirmation'):
        return {'bundle': {'available': True, 'phase': phase,
                           'can_confirm': phase == 'confirmation',
                           'pending_versions': ['7.0.255.16'],
                           'pending_bytes': 3430782740, 'reason': None}}

    def test_commands_and_read_only_status(self):
        for action in ('status', 'confirm'):
            with patch.object(cli, 'Client') as client, contextlib.redirect_stdout(io.StringIO()):
                client.return_value.execute.return_value = {'ok': True}
                self.assertEqual(cli.main(['--serial', 'emulator-5556', 'bundle', action]), 0)
                self.assertEqual(client.return_value.execute.call_args.args[:2], ('bundle', action))
            device = FakeAdb()
            device.response_override = {'state': self.state('confirmation' if action == 'status' else 'downloading')}
            client = device.client()
            self.assertTrue(client.execute('bundle', action)['ok'])
            self.assertEqual(client.dispatched, action == 'confirm')
            self.assertEqual(len(device.requests), 1)

    def test_unconfirmed_update_is_not_success_or_retried(self):
        for phase in ('confirmation', 'unavailable', 'failed'):
            device = FakeAdb()
            device.response_override = {'state': self.state(phase)}
            result = device.client().execute('bundle', 'confirm')
            self.assertFalse(result['ok'])
            self.assertTrue(result['error']['outcome_unknown'])
            self.assertFalse(result['error']['automatic_retry'])
            self.assertEqual(len(device.requests), 1)

    def test_status_validates_bounded_public_fields(self):
        for change in ({'available': 1}, {'can_confirm': 1}, {'phase': 'complete'},
                       {'pending_bytes': True}, {'pending_bytes': -1},
                       {'pending_versions': ['https://example.test/private']},
                       {'pending_versions': ['7.0.255.16'] * 17}, {'reason': 1},
                       {'phase': 'downloading', 'can_confirm': True}):
            state = self.state()
            state['bundle'].update(change)
            with self.assertRaises(cli.CliError):
                cli.validate_domain_response(state, 'bundle', 'status')
        unavailable = {'bundle': {'available': False, 'phase': 'unavailable', 'can_confirm': False,
                                  'pending_versions': [], 'pending_bytes': None, 'reason': 'wrong_scene'}}
        cli.validate_domain_response(unavailable, 'bundle', 'status')

    def test_unknown_action_rejected_before_device(self):
        device = FakeAdb()
        self.assertFalse(device.client().execute('bundle', 'overwrite-cache')['ok'])
        self.assertFalse(device.calls)


if __name__ == '__main__':
    unittest.main()
