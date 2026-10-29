"""Small native input/catalog fixtures; no game, crypto keys, bundle build or network."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
import zipfile
from unittest.mock import patch

import native_chart_intake as intake

import build_content_bundle as catalog_validator
AFF = b'AudioOffset:0\n-\ntiming(0,120,4);\n(100,1);\nhold(200,400,2);\narc(500,900,0,1,s,0,1,0,none,false)[arctap(700)];\n'


class NativeIntakeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / 'native'
        self.source.mkdir()
        self.payload = {'2.aff': AFF, 'base.ogg': b'OggSsynthetic audio', 'base.jpg': b'\xff\xd8synthetic jacket'}
        for name, raw in self.payload.items(): (self.source / name).write_bytes(raw)
        self.song = {'id': 'native_fixture', 'idx': 5000, 'set': 'fan_pack', 'remote_dl': True,
                     'difficulties': [{'ratingClass': 2, 'rating': 10}]}
        self.songs, self.packs, self.metadata, self.constants = (self.root / name for name in ('songlist', 'packlist', 'song_metadata.json', 'chart.json'))
        self.songs.write_text(json.dumps({'songs': [self.song]}))
        self.packs.write_text(json.dumps({'packs': [{'id': 'fan_pack'}]}))
        self.metadata.write_text(json.dumps({'native_fixture': {'files': ['2.aff', 'base.ogg'],
                    'hashes': {name: hashlib.md5(self.payload[name]).hexdigest() for name in ('2.aff', 'base.ogg')}}}))

    def run_gate(self, source=None, constants=None):
        return intake.validate(source or self.source, 'native_fixture', self.songs, self.packs,
                               self.metadata, constants, catalog_validator)

    def test_native_good_absent_constant_is_unranked_deterministic_and_inputs_unchanged(self):
        before = {p.name: p.read_bytes() for p in self.source.iterdir()}
        first, second = self.run_gate(), self.run_gate()
        self.assertEqual(first, second)
        self.assertEqual(first['status'], 'VALIDATED_NATIVE_INTAKE_NOT_GAMEPLAY_ACCEPTED')
        self.assertEqual(first['ranked_classes'], [])
        self.assertEqual(first['unranked_classes'], [2])
        self.assertFalse(first['constants_inferred_from_level'])
        self.assertFalse(first['fixed_pack_limit_applied'])
        self.assertEqual(before, {p.name: p.read_bytes() for p in self.source.iterdir()})

    def test_only_explicit_existing_constant_format_allows_ranked_class(self):
        self.constants.write_text(json.dumps({'song_id': 'native_fixture', 'charts': [{'difficulty': 2, 'chart_const': 10.1}]}))
        self.assertEqual(self.run_gate(constants=self.constants)['ranked_classes'], [2])
        self.constants.write_text(json.dumps({'song_id': 'native_fixture', 'charts': [{'difficulty': 3, 'chart_const': 10.1}]}))
        with self.assertRaises(ValueError): self.run_gate(constants=self.constants)

    def test_missing_audio_or_download_dependency_or_plaintext_hash_mismatch_rejects(self):
        (self.source / 'base.ogg').unlink()
        with self.assertRaises(ValueError): self.run_gate()
        (self.source / 'base.ogg').write_bytes(self.payload['base.ogg'])
        metadata = json.loads(self.metadata.read_bytes())
        metadata['native_fixture']['files'] = ['base.ogg']
        self.metadata.write_text(json.dumps(metadata))
        with self.assertRaisesRegex(ValueError, 'omits'): self.run_gate()
        metadata['native_fixture']['files'] = ['2.aff', 'base.ogg']
        metadata['native_fixture']['hashes']['2.aff'] = '0' * 32
        self.metadata.write_text(json.dumps(metadata))
        with self.assertRaisesRegex(ValueError, 'MD5'): self.run_gate()

    def test_unknown_extension_scenecontrol_and_custom_sample_are_quarantined_not_rewritten(self):
        (self.source / 'scenecontrol.lua').write_text('synthetic extension')
        result = self.run_gate()
        self.assertEqual(result['status'], 'QUARANTINED_NOT_PLAYABLE')
        self.assertIn('scenecontrol.lua', result['quarantine_reasons'])
        self.assertEqual((self.source / 'scenecontrol.lua').read_text(), 'synthetic extension')
        self.constants.write_text(json.dumps({'song_id': 'native_fixture', 'charts': [{'difficulty': 2, 'chart_const': 10.1}]}))
        blocked = self.run_gate(constants=self.constants)
        self.assertEqual(blocked['ranked_classes'], [])
        self.assertEqual(blocked['blocked_ranked_classes'], [2])
        self.assertIn('scenecontrol-consumer-proof-required', intake.native_aff(AFF + b'scenecontrol(100,trackhide,0,0);')['unsupported'])
        custom = AFF.replace(b',none,', b',sp_wav,')
        self.assertIn('custom-arc-sample', intake.native_aff(custom)['unsupported'])
        self.assertIn('event:effect', intake.native_aff(AFF + b'effect(1,2);')['unsupported'])

    def test_malformed_placeholder_and_unclosed_group_reject(self):
        for raw in (b'not an AFF', b'AudioOffset:0\n-\ntiming(0,120,4);', AFF.replace(b'(100,1);', b'(100,1)'),
                    AFF + b'timinggroup(){', AFF.replace(b'timing(0,120,4)', b'timing(0,NaN,4)')):
            with self.assertRaises(ValueError): intake.native_aff(raw)

    def test_existing_catalog_validator_rejects_duplicate_ID_missing_pack_and_parent_cycle(self):
        self.songs.write_text(json.dumps({'songs': [self.song, self.song]}))
        with self.assertRaises(ValueError): self.run_gate()
        self.songs.write_text(json.dumps({'songs': [self.song]}))
        self.packs.write_text(json.dumps({'packs': [{'id': 'other'}]}))
        with self.assertRaises(ValueError): self.run_gate()
        self.packs.write_text(json.dumps({'packs': [{'id': 'fan_pack', 'pack_parent': 'loop'}, {'id': 'loop', 'pack_parent': 'fan_pack'}]}))
        with self.assertRaisesRegex(ValueError, 'cycle'): self.run_gate()

    def test_dynamic_large_pack_catalog_is_not_capped_at62(self):
        self.packs.write_text(json.dumps({'packs': [{'id': 'fan_pack'}, *({'id': 'pack%d' % i} for i in range(200))]}))
        self.assertEqual(self.run_gate()['catalog_pack_count'], 201)

    def test_zip_safe_flat_intake_matches_source_hashes_and_escape_rejects(self):
        archive = self.root / 'native.zip'
        with zipfile.ZipFile(archive, 'w') as stream:
            for name, raw in reversed(list(self.payload.items())): stream.writestr(name, raw)
        folder, zipped = self.run_gate(), self.run_gate(archive)
        self.assertEqual(folder['files'], zipped['files'])
        self.assertEqual(zipped['source']['sha256'], hashlib.sha256(archive.read_bytes()).hexdigest())
        with zipfile.ZipFile(archive, 'w') as stream: stream.writestr('../outside', b'synthetic')
        with self.assertRaises(ValueError): self.run_gate(archive)

    def test_report_never_enters_source_folder_or_overwrites_existing_report(self):
        result = self.run_gate()
        with self.assertRaises(ValueError): intake.write_report(self.source / 'report.json', self.source, result)
        report = self.root / 'report.json'
        intake.write_report(report, self.source, result)
        before = report.read_bytes()
        with self.assertRaises(FileExistsError): intake.write_report(report, self.source, result)
        self.assertEqual(report.read_bytes(), before)

    def test_visual_or_noinput_only_charts_and_standalone_arctaps_reject(self):
        for body in (b'arc(0,100,0,0,s,0,0,0,none,true);', b'timinggroup(noinput){(100,1);};',
                     b'timinggroup(noinput){timinggroup(){hold(0,100,1);};};', b'arctap(100);'):
            with self.assertRaises(ValueError): intake.native_aff(b'AudioOffset:0\n-\n' + body)
        result = intake.native_aff(b'AudioOffset:0\n-\narc(0,100,0,0,s,0,0,0,none,true)[arctap(50)];')
        self.assertEqual(result['playable_note_events'], 1)
        self.assertEqual(result['status'], 'native-grammar-subset-validated')

    def test_unsupported_difficulty_overrides_quarantine_and_block_constants(self):
        self.constants.write_text(json.dumps({'song_id': 'native_fixture', 'charts': [{'difficulty': 2, 'chart_const': 10.1}]}))
        for flag in ('audioOverride', 'jacketOverride'):
            song = deepcopy(self.song)
            song['difficulties'][0][flag] = True
            self.songs.write_text(json.dumps({'songs': [song]}))
            result = self.run_gate(constants=self.constants)
            self.assertEqual(result['status'], 'QUARANTINED_NOT_PLAYABLE')
            self.assertIn('unsupported-difficulty-' + flag, result['quarantine_reasons'])
            self.assertEqual(result['ranked_classes'], [])
            self.assertEqual(result['blocked_ranked_classes'], [2])

    def test_input_reference_change_during_source_scan_cannot_bind_new_hash_to_old_check(self):
        original = intake.source_files
        def mutate(source):
            result = original(source)
            value = json.loads(self.metadata.read_bytes())
            value['native_fixture']['hashes']['2.aff'] = '0' * 32
            self.metadata.write_text(json.dumps(value))
            return result
        with patch.object(intake, 'source_files', mutate):
            with self.assertRaisesRegex(ValueError, 'changed during intake'): self.run_gate()


if __name__ == '__main__':
    unittest.main()
