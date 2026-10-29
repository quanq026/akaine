"""Synthetic production-root orchestration gates; no private input or compiler calls."""
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

import build_prod_rebase_release as release
import verify_prod_rebase_release as verifier


def fixtures():
    expected = {name: hashlib.sha256(name.encode()).hexdigest() for name in release.PAYLOAD_NAMES}
    lock = {'release': 'staging-prod-v9-rebase', 'application_version': '7.0.255', 'content_version': '7.0.255.20',
            'base_apk': {'role': release.BASE_ROLE, 'sha256': release.build_prod_rebase_core.PROD_APK_SHA},
            'expected_replacements': [{'role': 'final/payload/' + name, 'sha256': pin} for name, pin in expected.items()],
            'assetset_sha256': 'b' * 64, 'signing': {'signer_certificate_sha256': 'a' * 64}}
    plan = {'schema': 'akaine.client-build.v1', 'environment': 'staging', 'not_for_production': True,
            'source_sha256': release.build_prod_rebase_core.PROD_APK_SHA, 'content_version': lock['content_version'],
            'replacements': [{'archive_path': name, 'file': 'final/payload/' + name, 'sha256': pin} for name, pin in expected.items()],
            'binary_patches': []}
    core = {'status': 'PROD_V9_ROOTED_STAGING_CORE_REBUILT_AND_EVERY_BYTE_ACCOUNTED',
            'prod_APK_sha256': release.build_prod_rebase_core.PROD_APK_SHA,
            'core_sha256': expected['lib/arm64-v8a/libcocos2dcpp.so'],
            'compiled_from_prod_input_and_authored_gates': True, 'accepted_final_SO_used_as_build_input': False,
            'accounting': {'prod_input_sha256': release.build_prod_rebase_core.PROD_CORE_SHA,
                          'normalized_input_sha256': release.build_prod_rebase_core.STAGING_INPUT_SHA,
                          'final_core_sha256': expected['lib/arm64-v8a/libcocos2dcpp.so'],
                          'every_output_byte_reconstructed_from_prod_and_declared_changes': True,
                          'all_unlisted_production_input_bytes_preserved': True}}
    dex = {'status': 'PROD_V9_ROOTED_CLASSES3_EXACT_SINGLE_METHOD_NORMALIZATION_VERIFIED',
           'prod_APK_sha256': release.build_prod_rebase_dex.PROD_APK_SHA,
           'prod_classes3_sha256': release.build_prod_rebase_dex.PROD_DEX3_SHA,
           'classes3_sha256': release.build_prod_rebase_dex.STAGING_DEX3_SHA,
           'classes4_sha256': release.build_prod_rebase_dex.DEX4_SHA, 'classes4_copied_exact_from_production': True,
           'foreign_or_accepted_final_DEX_used_as_build_input': False,
           'comparison': {'classes': 725, 'unchanged_classes': 724, 'all_other_methods_class_metadata_and_classes_identical': True}}
    loader = {'status': 'EXACT_ACCEPTED_LOADER_REBUILT', 'loader_sha256': expected['lib/arm64-v8a/libakfcloader.so'],
              'opaque_header_read_copied_hashed_or_logged_by_driver': False}
    return lock, plan, expected, core, dex, loader


class ProdRebaseReleaseTests(unittest.TestCase):
    def test_all_undeclared_production_members_preserved(self):
        with tempfile.TemporaryDirectory() as folder:
            base, apk = Path(folder) / 'base.apk', Path(folder) / 'candidate.apk'
            original = {'classes.dex': b'old public entry', 'assets/fixture': b'original resource',
                        'monitor.so': b'old monitor', 'META-INF/OLD.SF': b'old signature'}
            with zipfile.ZipFile(base, 'w') as archive:
                for name, value in original.items(): archive.writestr(name, value)
            for case in ('valid', 'altered', 'added', 'removed'):
                current = {**original, 'monitor.so': b'new monitor', 'META-INF/NEW.SF': b'new signature'}
                if case == 'altered': current['classes.dex'] = b'unreviewed code'
                if case == 'added': current['assets/extra'] = b'unreviewed resource'
                if case == 'removed': del current['assets/fixture']
                with zipfile.ZipFile(apk, 'w') as archive:
                    for name, value in current.items(): archive.writestr(name, value)
                if case == 'valid':
                    self.assertEqual(verifier.preserved_production_members(base, apk, {'monitor.so': 'reviewed'}), 2)
                else:
                    with self.subTest(case=case), self.assertRaises(ValueError):
                        verifier.preserved_production_members(base, apk, {'monitor.so': 'reviewed'})

    def test_exact_five_distinct_payload_plan_and_authentic_base(self):
        lock, plan, expected, *_ = fixtures()
        self.assertEqual(release.expected_payloads(lock), expected)
        release.verify_plan(lock, plan)
        for change in ('duplicate', 'foreign_base', 'unreviewed_patch', 'wrong_content', 'production'):
            other = copy.deepcopy(plan)
            if change == 'duplicate': other['replacements'].append(other['replacements'][0])
            if change == 'foreign_base': other['source_sha256'] = 'c' * 64
            if change == 'unreviewed_patch': other['binary_patches'] = [{'target': 'classes.dex'}]
            if change == 'wrong_content': other['content_version'] = '7.0.255.18'
            if change == 'production': other['not_for_production'] = False
            with self.subTest(change=change), self.assertRaises(ValueError): release.verify_plan(lock, other)
        lock['expected_replacements'].append(lock['expected_replacements'][0])
        with self.assertRaises(ValueError): release.expected_payloads(lock)

    def test_provenance_rejects_accepted_foreign_binary_or_missing_accounting(self):
        _, _, expected, core, dex, loader = fixtures()
        release.validate_provenance(core, dex, loader, expected)
        for name, key, value in (('core', 'accepted_final_SO_used_as_build_input', True),
                                  ('core', 'accounting', {}), ('core', 'prod_APK_sha256', 'c' * 64),
                                  ('dex', 'foreign_or_accepted_final_DEX_used_as_build_input', True),
                                  ('dex', 'comparison', {}), ('dex', 'classes3_sha256', 'd' * 64),
                                  ('loader', 'opaque_header_read_copied_hashed_or_logged_by_driver', True)):
            values = {'core': copy.deepcopy(core), 'dex': copy.deepcopy(dex), 'loader': copy.deepcopy(loader)}
            values[name][key] = value
            with self.subTest(name=name, key=key), self.assertRaises(ValueError):
                release.validate_provenance(values['core'], values['dex'], values['loader'], expected)

    def test_active_builder_requires_exact_bound_source_file(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'builder.py'; path.write_bytes(b'authored')
            lock = {'rows': [{'role': 'builder', 'sha256': hashlib.sha256(b'authored').hexdigest()}]}
            with patch.object(release.shared, 'manifest_rows', return_value=lock['rows']):
                with self.assertRaisesRegex(ValueError, 'not a pinned release input'):
                    release.verify_active_inputs(lock, {'builder': str(path)})

    def test_signed_receipt_requires_new_profile_and_prod_provenance(self):
        lock, _, expected, core, dex, loader = fixtures()
        build = {'status': 'FIVE_SOURCE_PAYLOADS_AND_UNSIGNED_APK_MATCH', 'release': lock['release'],
                 'prod_APK_sha256': release.build_prod_rebase_core.PROD_APK_SHA,
                 'source_lock_sha256': 'c' * 64, 'checkout_map_sha256': 'd' * 64,
                 'payload_sha256': expected, 'unsigned_apk_sha256': 'e' * 64,
                 'core_provenance': core, 'DEX_provenance': dex, 'loader_receipt': loader,
                 'base_assets': {'assetset_sha256': 'b' * 64}, 'output_assets': {'assetset_sha256': 'b' * 64}}
        artifact = {'environment': 'staging', 'package': 'akai.arc.lmao', 'payloads': expected,
                    'signer_sha256': 'a' * 64, 'assembly': {'output_sha256': 'e' * 64},
                    'post_sign_assetset_verified': {'assetset_sha256': 'b' * 64}}
        self.assertEqual(verifier.validate_receipts(lock, build, artifact, 'c' * 64, 'd' * 64)[0], expected)
        for field, bad in (('release', 'staging-final-combined'), ('prod_APK_sha256', 'f' * 64),
                           ('source_lock_sha256', 'f' * 64), ('core_provenance', {})):
            other = {**build, field: bad}
            with self.subTest(field=field), self.assertRaises(ValueError):
                verifier.validate_receipts(lock, other, artifact, 'c' * 64, 'd' * 64)

    def test_generated_prod_dex_inputs_and_payload_mismatch_stop_before_assembly(self):
        lock, plan, _, core_receipt, dex_receipt, loader = fixtures()
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); output = root / 'output'; kit = output / 'private-kit'
            plan_path = root / 'plan.json'; plan_path.write_text(json.dumps(plan))
            raw_inputs = {}
            for name in ('base', 'java', 'jar', 'rawdex', 'javac', 'd8', 'assets', 'clang'):
                path = root / name; path.write_bytes(name.encode()); raw_inputs[name] = str(path)
            paths = {release.BASE_ROLE: raw_inputs['base'], 'tools/java-17/bin/java.exe': raw_inputs['java'],
                'tools/jadx-1.5.6-all.jar': raw_inputs['jar'], 'tools/RawDexTool.java': raw_inputs['rawdex'],
                'tools/java-17/bin/javac.exe': raw_inputs['javac'], 'tools/android-build-35/d8.jar': raw_inputs['d8'],
                'assetset/manifest.json': raw_inputs['assets'],
                'android-sdk/ndk/28.2.13676358/toolchains/llvm/prebuilt/windows-x86_64/bin/clang++.exe': raw_inputs['clang'],
                'loader/compiler': raw_inputs['clang'], 'loader/crypto': raw_inputs['assets']}
            generated = {name: root / ('normalized-' + name) for name in ('classes3.dex', 'classes4.dex')}
            for path in generated.values(): path.write_bytes(b'generated from prod')
            core = root / 'core.so'; core.write_bytes(b'core')
            monitor = root / 'monitor.so'; monitor.write_bytes(b'monitor')
            pins = root / 'pins'; pins.mkdir()
            for name in ('owned_core_pins.h', 'cli_song_pins.h'):
                path = pins / name; path.write_bytes(b'pinned')
                role = 'semantic/owned/' + name if name.startswith('owned') else 'semantic/song-v9/' + name
                private_pin = root / ('hydrated-' + name); private_pin.write_bytes(b'pinned')
                paths[role] = str(private_pin)
            def hydrate(*unused): kit.mkdir(); return dict(paths)
            def startup(hydrated_kit, values, target):
                self.assertEqual(values['dex/classes3-source.dex'], str(generated['classes3.dex']))
                self.assertEqual(values['dex/classes4-source.dex'], str(generated['classes4.dex']))
                return generated
            def loader_build(*unused):
                target = output / 'loader'; target.mkdir(); (target / 'libakfcloader.so').write_bytes(b'loader')
                return loader
            profile = root / 'profile.json'; profile.write_bytes(b'profile')
            loader_profile = root / 'loader.json'; loader_profile.write_text('{}')
            with patch.object(release, 'verify'), patch.object(release, 'PROFILE', profile), \
                    patch.object(release, 'CHECKOUT', profile), patch.object(release, 'PLAN', plan_path), \
                    patch.object(release, 'LOADER_PROFILE', loader_profile), \
                    patch.object(release.shared, 'physical_output', return_value={}), \
                    patch.object(release.shared, 'hydrate', side_effect=hydrate), \
                    patch.object(release.build_prod_rebase_core, 'build', return_value=(core, pins, core_receipt)), \
                    patch.object(release.final, 'compile_monitor', return_value=monitor), \
                    patch.object(release.build_prod_rebase_dex, 'build', return_value=(generated, dex_receipt)), \
                    patch.object(release.shared, 'dex', side_effect=startup), \
                    patch.object(release.build_cap60_dex, 'build', return_value=(generated['classes3.dex'], {})), \
                    patch.object(release.build_bundle_partial_cache, 'build', return_value=(generated['classes3.dex'], {})), \
                    patch.object(release.build_loader_equivalence, 'build', side_effect=loader_build), \
                    patch.object(release.build_android_client, 'build') as assembly:
                with self.assertRaisesRegex(ValueError, 'stop before APK'): release.build(lock, paths, output)
                assembly.assert_not_called()
                self.assertFalse((output / 'unsigned.apk').exists())
                self.assertTrue((output / 'PAYLOAD_MISMATCH.json').exists())


if __name__ == '__main__':
    unittest.main()
