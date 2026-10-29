"""Production V36 source, routing and pre-assembly gates; no compiler actions."""
import copy
import json
from pathlib import Path
import re
import unittest
from unittest.mock import patch
import zipfile

import build_production_news_core as core
import build_production_news_release as release
import build_production_bundle_partial_cache as partial

FROZEN = Path('D:/AkaineBuilds/prod-rebase-20261025/rebased-clean-build-news-v36-r2')


class ProductionSourceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with zipfile.ZipFile(FROZEN / 'private-kit/base/prod-v9.apk') as archive:
            cls.prod = archive.read(core.original.CORE_ENTRY)
        cls.stage = (FROZEN / 'core/news/libcocos2dcpp.so').read_bytes()

    def test_both_routing_layers_match_authentic_production(self):
        raw, proof = core.production_routes(self.prod, self.stage)
        self.assertEqual(core.original.sha(raw), core.OUTPUT_SHA)
        self.assertEqual(proof['changed_bytes'], 61)
        for address, size in core.ROUTE_PINS:
            a, b = core.original.file_offset(self.prod, address, size), core.original.file_offset(raw, address, size)
            self.assertEqual(raw[b:b + size], self.prod[a:a + size])
        self.assertTrue(proof['all_other_fresh_V36_bytes_identical'])

    def test_foreign_root_and_changed_V36_bytes_fail_closed(self):
        for prod, stage in ((self.prod + b'x', self.stage), (self.prod, self.stage + b'x')):
            with self.assertRaises(ValueError):
                core.production_routes(prod, stage)

    def test_generated_CLI_pins_cover_both_layers_and_keep_action_pins(self):
        source = (FROZEN / 'private-kit/semantic/native/cli_pins.h').read_text('utf-8')
        result = core.cli_route_pins(source, self.prod)
        self.assertEqual(result[result.index('inline constexpr unsigned char CLI_CALLBACK'):],
                         source[source.index('inline constexpr unsigned char CLI_CALLBACK'):])
        for index, (address, size) in enumerate(core.ROUTE_PINS):
            match = re.search(rf'CLI_ROUTE_{index}\[\] = \{{([^}}]+)\}}', result)
            data = bytes(int(value, 16) for value in match[1].split(','))
            at = core.original.file_offset(self.prod, address, size)
            self.assertEqual(data, self.prod[at:at + size])
        self.assertEqual(core.cli_route_pins(result, self.prod), result)

    def test_production_bridge_changes_only_environment_and_log_labels(self):
        root = release.ROOT / 'patches/arcaea-7.0.255-arm64/runtime/semantic/native'
        stage = (root / 'staging_cli_bridge.h').read_bytes()
        expected = stage.replace(b'\\\"environment\\\":\\\"staging\\\"', b'\\\"environment\\\":\\\"production\\\"')
        expected = expected.replace(b'The semantic bridge is available only in the isolated staging monitor.', b'The semantic bridge requires the production profile monitor.')
        expected = expected.replace(b'staging_cli_init status=', b'production_cli_init status=')
        self.assertEqual((root / 'production_cli_bridge.h').read_bytes(), expected)
        self.assertEqual(expected.count(b'\\\"environment\\\":\\\"production\\\"'), 2)

    def test_unaccepted_candidate_cannot_reach_any_build_tool_or_APK(self):
        with patch.object(release, 'verify') as verify:
            with self.assertRaisesRegex(ValueError, 'cannot assemble'):
                release.build({}, {}, Path('unused'), candidate=True, assemble=True)
            verify.assert_not_called()

    def test_staging_and_pending_profiles_rejected_by_sealed_verifier(self):
        for status in ('staging', release.PENDING):
            lock = dict(release=release.RELEASE, status=status, application_version='7.0.255',
                        content_version='7.0.255.25', base_apk={'role': release.BASE_ROLE, 'sha256': core.PROD_APK_SHA})
            with self.assertRaisesRegex(ValueError, 'matching acceptance state'):
                release.verify(lock, {})

    def test_cache_requires_boolean_candidate_or_sealed_output_hash(self):
        args = [Path('unused')] * 8
        for candidate in (False, 1, 'yes'):
            with self.subTest(candidate=candidate), self.assertRaisesRegex(ValueError, 'sealed production DEX hash'):
                partial.build(*args, candidate=candidate)
        with patch.object(partial.shared, 'digest', return_value='0' * 64):
            with self.assertRaisesRegex(ValueError, 'Pinned partial-cache input'):
                partial.build(*args, candidate=True)


if __name__ == '__main__':
    unittest.main()
