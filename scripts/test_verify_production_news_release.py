"""Synthetic signed production receipt checks; no signing, compiler or device actions."""
import copy
from pathlib import Path
import unittest
from unittest.mock import patch

import test_prod_rebase_release as fixtures
import verify_production_news_release as verifier


def receipts():
    lock, _, expected, ordinary, dex, loader = fixtures.fixtures()
    lock.update(release=verifier.release.RELEASE, status=verifier.release.SEALED, content_version='7.0.255.25')
    expected['lib/arm64-v8a/libcocos2dcpp.so'] = verifier.release.core.OUTPUT_SHA
    for row in lock['expected_replacements']:
        row['sha256'] = expected[row['role'].removeprefix('final/payload/')]
    ordinary.update(core_sha256=verifier.release.core.STAGING_NEWS_SHA)
    ordinary['accounting']['final_core_sha256'] = verifier.release.core.STAGING_NEWS_SHA
    core = dict(status='PROD_V9_ROOTED_PRODUCTION_V36_CORE_REBUILT_AND_ACCOUNTED',
                prod_APK_sha256=verifier.release.core.PROD_APK_SHA, core_sha256=verifier.release.core.OUTPUT_SHA,
                accepted_final_SO_used_as_build_input=False, fresh_V36_source_provenance=ordinary,
                production_route_accounting=dict(changed_bytes=61,
                    visible_and_encrypted_shared_routes_match_authentic_production=True,
                    all_other_fresh_V36_bytes_identical=True, route_spans=[
                        dict(runtime_VA=hex(address), bytes=size, original_sha256=before,
                             staging_sha256=verifier.release.core.original.sha(stage))
                        for address, size, before, stage in verifier.release.core.original.ROUTES]))
    build = dict(status='FIVE_SOURCE_PAYLOADS_AND_UNSIGNED_APK_MATCH', release=lock['release'],
                 prod_APK_sha256=verifier.release.core.PROD_APK_SHA, source_lock_sha256='c' * 64,
                 checkout_map_sha256='d' * 64, payload_sha256=expected, unsigned_apk_sha256='e' * 64,
                 APK_assembled=True, signed=False, core_provenance=core, DEX_provenance=dex, loader_receipt=loader,
                 base_assets={'assetset_sha256': lock['assetset_sha256']}, output_assets={'assetset_sha256': lock['assetset_sha256']},
                 partial_cache_receipt=dict(status='AUTHORED_PRODUCTION_PARTIAL_CACHE_DEX_EXACT_REPRODUCTION_PASS',
                    candidate_only=False, sealed_expected_sha256=expected['classes3.dex'], classes3_sha256=expected['classes3.dex'],
                    new_helper_compiled_from_Java=True, compile_adapters_excluded=True,
                    all_reassembled_instruction_and_exception_coverage_equivalent=True))
    artifact = dict(environment='production', package='akai.arc.lmao', payloads=expected,
                    signer_sha256=lock['signing']['signer_certificate_sha256'], assembly={'output_sha256': 'e' * 64},
                    post_sign_assetset_verified={'assetset_sha256': lock['assetset_sha256']})
    return lock, build, artifact


class ProductionSignedReceiptTests(unittest.TestCase):
    def validate(self, lock, build, artifact):
        return verifier.validate_receipts(lock, build, artifact, 'c' * 64, 'd' * 64)

    def test_sealed_production_receipts_match(self):
        lock, build, artifact = receipts()
        expected, signer = self.validate(lock, build, artifact)
        self.assertEqual(expected, build['payload_sha256'])
        self.assertEqual(signer, lock['signing']['signer_certificate_sha256'])

    def test_staging_environment_and_candidate_profiles_fail_closed(self):
        for target, field, value in (('artifact', 'environment', 'staging'), ('artifact', 'package', 'other'),
                ('lock', 'status', verifier.release.PENDING), ('lock', 'application_version', '7.0.254'),
                ('lock', 'content_version', '7.0.255.20'), ('build', 'APK_assembled', False),
                ('build', 'status', 'UNACCEPTED_CANDIDATE_FIVE_SOURCE_PAYLOADS'), ('build', 'signed', True),
                ('build', 'release', 'staging-prod-v9-rebase'), ('build', 'source_lock_sha256', '0' * 64)):
            lock, build, artifact = receipts()
            {'lock': lock, 'build': build, 'artifact': artifact}[target][field] = value
            with self.subTest(target=target, field=field), self.assertRaises(ValueError):
                self.validate(lock, build, artifact)

    def test_missing_encrypted_route_and_foreign_binary_provenance_rejected(self):
        for failure in ('encrypted', 'route_hash', 'foreign_binary', 'ordinary_accounting', 'candidate_cache', 'cache_hash'):
            lock, build, artifact = receipts()
            proof = build['core_provenance']
            if failure == 'encrypted': proof['production_route_accounting']['route_spans'].pop()
            if failure == 'route_hash': proof['production_route_accounting']['route_spans'][0]['original_sha256'] = '0' * 64
            if failure == 'foreign_binary': proof['accepted_final_SO_used_as_build_input'] = True
            if failure == 'ordinary_accounting': proof['fresh_V36_source_provenance']['accounting'] = {}
            if failure == 'candidate_cache': build['partial_cache_receipt']['candidate_only'] = True
            if failure == 'cache_hash': build['partial_cache_receipt']['classes3_sha256'] = '0' * 64
            with self.subTest(failure=failure), self.assertRaises(ValueError): self.validate(lock, build, artifact)

    def test_artifact_signer_unsigned_build_and_assets_must_match(self):
        for field in ('signer_sha256', 'payloads', 'assembly', 'post_sign_assetset_verified'):
            lock, build, artifact = receipts()
            artifact[field] = {} if field != 'signer_sha256' else '0' * 64
            with self.subTest(field=field), self.assertRaises(ValueError): self.validate(lock, build, artifact)
        lock, build, artifact = receipts()
        build['output_assets'] = {}
        with self.assertRaises(ValueError): self.validate(lock, build, artifact)

    def test_verifier_must_itself_be_pinned(self):
        with patch.object(verifier.release.engine.shared, 'manifest_rows', return_value=[]):
            with self.assertRaisesRegex(ValueError, 'not a pinned production source'):
                verifier.pinned_verifier_inputs({}, {})


if __name__ == '__main__':
    unittest.main()
