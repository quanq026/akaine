"""Focused source and trust-boundary checks for the public 7.1 build."""
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest

import build_android_client as client

ROOT = Path(__file__).resolve().parents[1]
engine = client.load_patch_module('engine71_tests', client.PATCH / 'build.py')
native = engine.engine('native')
managed = engine.engine('managed')
sys.path.insert(0, str(ROOT / 'scripts/akaine_cli'))
import akaine
import catalogue


class CurrentPatchTests(unittest.TestCase):
    def test_shared_sources_are_locked_and_generated_only_outside_repo(self):
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder) / 'sources'
            hashes = engine.prepare_sources(output)
            self.assertEqual(len(hashes), 49)
            self.assertEqual(json.loads((output / 'SOURCE_INPUTS.json').read_bytes()), hashes)
            self.assertTrue((output / 'tools/StockManagedBuild.py').is_file())
            self.assertTrue((output / 'tools/StockResources.py').is_file())
            self.assertEqual(len(engine.source_hashes()), 66)
            with self.assertRaisesRegex(ValueError, 'Fresh external'):
                engine.prepare_sources(output)
        with self.assertRaisesRegex(ValueError, 'Fresh external'):
            engine.prepare_sources(ROOT / 'generated-runtime')
        for name in ('../outside', '/absolute', 'C:/absolute', 'a\\b'):
            with self.assertRaisesRegex(ValueError, 'Unsafe'):
                engine.relative(name)

    def test_wrong_native_provider_and_managed_preimages_fail_closed(self):
        for raw in (b'', b'not the supported native library'):
            with self.assertRaises(ValueError):
                engine.engine('provider').build(raw)
        with self.assertRaises(ValueError):
            managed.cache_source('unreviewed Java source', ())
        baseline = client.load_patch_module('baseline_managed_test', engine.BASELINE / 'smali/build.py')
        for text in ('absent', 'fixture fixture'):
            with self.assertRaises(ValueError):
                baseline.replace_once(text, 'fixture', 'changed')
        profile = json.loads((client.PATCH / 'production-profile.json').read_bytes())
        with self.assertRaisesRegex(ValueError, 'profile'):
            native.identity(dict(profile, package='akai.arc.lmao.staging'))

    def test_cli_selects_version_from_live_bridge_identity(self):
        metadata = {'protocol': 1, 'environment': 'production', 'package': 'akai.arc.lmao',
                    'pid': 123, 'session': 'a' * 32, 'commands': ['status']}
        self.assertEqual(akaine.validate_identity(metadata, '123')['application_version'], '7.0.255')
        metadata['application_version'] = '7.1.0'
        self.assertEqual(akaine.validate_identity(metadata, '123')['application_version'], '7.1.0')
        for value in (None, '7.1.1', '7.0.260', 7):
            with self.assertRaises(akaine.CliError):
                akaine.validate_identity(dict(metadata, application_version=value), '123')
        with self.assertRaises(akaine.CliError):
            akaine.validate_identity(metadata, '124')
        self.assertTrue(akaine.UI_TOKEN.fullmatch('partner_hint_continue.' + 'a' * 16))

    def test_cli_bundle_contract_rejects_other_versions_and_noncanonical_suffixes(self):
        pattern = catalogue.bundle_version_pattern('akai.arc.lmao', '7.1.0')
        import re
        for version in ('7.1.0.1', '7.1.0.999999999'):
            self.assertTrue(re.fullmatch(pattern, version))
        for version in ('7.0.255.28', '7.1.0.0', '7.1.0.01', '7.1.0.1000000000', '7.1.0.1\n'):
            self.assertFalse(re.fullmatch(pattern, version))


if __name__ == '__main__':
    unittest.main()
