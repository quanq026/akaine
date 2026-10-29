import base64
import contextlib
import io
import json
import unittest
import contextlib
import io
from unittest.mock import patch
from unittest.mock import patch
import akaine_stag as cli
from test_akaine_stag import FakeAdb


class MainLoopTests(unittest.TestCase):
    def test_main_unicode_json_survives_ascii_windows_stdout(self):
        value = {'ok': True, 'state': {'filter': {'query': '\u9739\u9742\u795e \U0001f3b5'}}}
        buffer = io.BytesIO()
        output = io.TextIOWrapper(buffer, encoding='ascii')
        with patch.object(cli, 'Client') as client, contextlib.redirect_stdout(output):
            client.return_value.execute.return_value = value
            self.assertEqual(cli.main(['--serial', 'emulator-5556', 'status']), 0)
        output.flush()
        self.assertEqual(json.loads(buffer.getvalue()), value)

    @staticmethod
    def settings_state(opened=True, speed=25, offset=-31, available=True):
        return {'settings': {'available': available, 'panel_open': opened, 'highspeed_int': speed,
                             'note_speed': speed / 10, 'active_offset_ms': offset},
                'settings_control': {'available': True, 'reason': None, 'open': opened,
                                     'can_open': not opened, 'can_close': opened,
                                     'can_set_note_speed': opened, 'can_set_offset': opened}}

    def test_settings_boundaries_and_canonical_wire(self):
        for setting, values in (('note-speed', [('1.0', '10'), ('2.5', '25'), ('6.5', '65'), ('3', '30')]),
                                ('offset', [('-2000', '-2000'), ('-0', '0'), ('0', '0'), ('2000', '2000')])):
            for text, expected in values:
                args = cli.make_parser().parse_args(['--serial', 'emulator-5556', 'settings', setting, text])
                self.assertEqual(args.value, expected)
                with patch.object(cli, 'Client') as client, contextlib.redirect_stdout(io.StringIO()):
                    client.return_value.execute.return_value = {'ok': True}
                    self.assertEqual(cli.main(['--serial', 'emulator-5556', 'settings', setting, text]), 0)
                    self.assertEqual(client.return_value.execute.call_args.args[:2],
                                     ('settings', ('speed:' if setting == 'note-speed' else 'offset:') + expected))
        for argument in ('status', 'open', 'close', 'speed:10', 'speed:65', 'offset:-2000', 'offset:2000', 'offset:0'):
            self.assertTrue(cli.domain_argument('settings', argument), argument)
        for argument in ('speed:9', 'speed:66', 'speed:1.0', 'speed:010', 'offset:2001', 'offset:-2001',
                         'offset:+1', 'offset:-0', 'offset:00', 'offset:1.0', 'offset:1\n', 'unknown'):
            device = FakeAdb()
            self.assertFalse(device.client().execute('settings', argument)['ok'], argument)
            self.assertFalse(device.calls)

    def test_settings_parser_rejects_invalid_and_missing_values_before_adb(self):
        bad = [['settings', 'note-speed', text] for text in
               ('0.9', '6.6', '1.05', 'NaN', 'inf', '1e0', '1.00', '+1.0', '１.０')]
        bad += [['settings', 'offset', text] for text in ('-2001', '2001', '1.5', '1e2', '+1', '01', 'inf')]
        bad += [['settings', 'note-speed'], ['settings', 'offset'], ['settings', 'anomaly-replay'],
                ['settings', 'status', 'on'], ['settings', 'open', '1'], ['settings', 'close', 'off']]
        for parts in bad:
            with patch.object(cli, 'Adb') as adb, contextlib.redirect_stdout(io.StringIO()) as output:
                self.assertEqual(cli.main(['--serial', 'emulator-5556', *parts]), 1, parts)
                self.assertEqual(json.loads(output.getvalue())['error']['code'], 'ARGUMENT_ERROR')
                adb.assert_not_called()

    def test_settings_panel_and_persisted_value_completion(self):
        for argument, state in (('status', self.settings_state()), ('open', self.settings_state()),
                                ('close', self.settings_state(False)), ('speed:25', self.settings_state()),
                                ('speed:10', self.settings_state(speed=10)), ('speed:65', self.settings_state(speed=65)),
                                ('offset:-31', self.settings_state()), ('offset:-2000', self.settings_state(offset=-2000)),
                                ('offset:2000', self.settings_state(offset=2000))):
            device = FakeAdb(); device.response_override = {'state': state}
            client = device.client(); result = client.execute('settings', argument)
            self.assertTrue(result['ok'], result)
            self.assertEqual(client.dispatched, argument != 'status')
            self.assertEqual(len(device.requests), 1)
        failures = [('open', self.settings_state(False)), ('close', self.settings_state()),
                    ('speed:26', self.settings_state()), ('offset:-30', self.settings_state()),
                    ('speed:25', self.settings_state(False)), ('speed:25', self.settings_state(available=False))]
        for control_change in ({'available': False}, {'reason': 'modal'}, {'can_set_note_speed': False}, {'open': False}):
            state = self.settings_state(); state['settings_control'].update(control_change)
            failures.append(('speed:25', state))
        for prefs_change in ({'highspeed_int': 25.0}, {'highspeed_int': True}, {'highspeed_int': None}, {'panel_open': False}):
            state = self.settings_state(); state['settings'].update(prefs_change)
            failures.append(('speed:25', state))
        for argument, state in failures:
            device = FakeAdb(); device.response_override = {'state': state}
            result = device.client().execute('settings', argument)
            self.assertFalse(result['ok'], (argument, state))
            self.assertTrue(result['error']['outcome_unknown'])
            self.assertFalse(result['error']['automatic_retry'])
            self.assertEqual(len(device.requests), 1)

    def test_settings_status_accepts_unavailable_but_rejects_bad_controls(self):
        state = self.settings_state(False, available=False)
        state['settings_control'].update(available=False, reason='wrong_scene', can_open=False)
        cli.validate_domain_response(state, 'settings', 'status')
        for change in ({'available': 1}, {'open': None}, {'can_set_offset': 0}, {'reason': 7}):
            bad = self.settings_state(); bad['settings_control'].update(change)
            with self.assertRaises(cli.CliError):
                cli.validate_domain_response(bad, 'settings', 'status')

    def test_settings_anomaly_replay_legacy_command_is_preserved(self):
        for value, expected in (('off', '0'), ('on', '1')):
            with patch.object(cli, 'Client') as client, contextlib.redirect_stdout(io.StringIO()):
                client.return_value.execute.return_value = {'ok': True}
                self.assertEqual(cli.main(['--serial', 'emulator-5556', 'settings', 'anomaly-replay', value]), 0)
                self.assertEqual(client.return_value.execute.call_args.args[:2], ('replay', expected))

    def test_unicode_queries_round_trip_and_bounded_wire(self):
        for query in ('Testify', '霹靂神', 'nhạc thử', 'a' * 128):
            argument = cli.encode_query(query)
            self.assertTrue(cli.domain_argument('filter', argument))
            state = {'filter': {'valid': True, 'open': True, 'ready': True, 'query': query,
                               'count': 1, 'sort': 1, 'group': 0, 'reverse': 0}}
            device = FakeAdb(); device.response_override = {'state': state}
            result = device.client().execute('filter', argument)
            self.assertTrue(result['ok'], result)
            self.assertEqual(len(device.requests), 1)
            self.assertLessEqual(len(' '.join(device.requests[0]).encode()), 512)

    def test_invalid_query_never_reaches_device(self):
        for query in ('', 'a' * 129, '\n', '\u0085', '\ud800'):
            with self.assertRaises(cli.CliError):
                cli.encode_query(query)
        for argument in ('query:', 'query:QQ=', 'query:QR', 'query:_w', 'query:AA', 'query:' + 'A' * 172):
            device = FakeAdb()
            result = device.client().execute('filter', argument)
            self.assertFalse(result['ok'], argument)
            self.assertFalse(device.calls)

    def test_filter_does_not_report_success_before_native_completion(self):
        valid = {'valid': True, 'open': True, 'ready': True, 'query': 'Testify', 'count': 1,
                 'sort': 1, 'group': 0, 'reverse': 0}
        for change in ({'ready': False}, {'query': 'different'}, {'open': False}):
            device = FakeAdb(); device.response_override = {'state': {'filter': {**valid, **change}}}
            result = device.client().execute('filter', cli.encode_query('Testify'))
            self.assertFalse(result['ok'])
            self.assertEqual(len(device.requests), 1)
            self.assertTrue(result['error']['outcome_unknown'])

    def test_skill_status_is_read_only_and_seal_requires_readback(self):
        value = {'available': True, 'native_skill_sealed': False, 'suppression': False, 'gameplay': {}}
        for argument, expected in (('status', True), ('seal:0', True), ('seal:1', False)):
            device = FakeAdb(); device.response_override = {'state': {'skill': value}}
            client = device.client(); result = client.execute('skill', argument)
            self.assertEqual(result['ok'], expected)
            self.assertEqual(client.dispatched, argument != 'status')

    def test_gameplay_requires_real_pause_and_scene_confirmation(self):
        nav = {'available': True, 'scene': 'gameplay', 'paused': True, 'reason': None,
               **{'can_' + name: False for name in ('back', 'continue', 'pause', 'resume', 'retry', 'quit')}}
        for action in ('status', 'pause', 'resume', 'retry', 'quit'):
            device = FakeAdb(); device.response_override = {'state': {'screen': 'gameplay', 'gameplay': True, 'navigation': nav}}
            client = device.client(); result = client.execute('gameplay', action)
            self.assertEqual(result['ok'], action in ('status', 'pause', 'retry'))
            self.assertEqual(client.dispatched, action != 'status')
            self.assertEqual(len(device.requests), 1)

    def test_after_dispatch_error_is_unknown_and_not_retried(self):
        for code in ('STATE_CHANGED_AFTER_DISPATCH', 'EXPIRED_AFTER_DISPATCH'):
            device = FakeAdb(); device.response_override = {'ok': False, 'error': {'code': code, 'message': 'fixture'}}
            result = device.client().execute('gameplay', 'pause')
            self.assertTrue(result['error']['outcome_unknown'])
            self.assertFalse(result['error']['automatic_retry'])
            self.assertEqual(len(device.requests), 1)

    def test_main_loop_parser(self):
        for parts in (['filter', 'status'], ['filter', 'query', '霹靂神'], ['skill', 'status'], ['skill', 'seal', 'off'],
                      ['gameplay', 'pause'], ['gameplay', 'resume'], ['navigation', 'continue']):
            args = cli.make_parser().parse_args(['--serial', 'emulator-5556', *parts])
            self.assertEqual(args.command, parts[0])


if __name__ == '__main__':
    unittest.main()
