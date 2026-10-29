"""Pure path/hash guards for the clean local build driver; no actual build."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

import build_release_profile as driver


class ReleaseProfileTests(unittest.TestCase):
    def lock(self, rows):
        return {'monitor_compile_local_inputs': rows, 'additional_build_inputs': [],
                'compile_NDK_inputs': [], 'expected_replacements': [], 'base_apk':
                {'role': 'base/v18-staging.apk', 'sha256': '0' * 64}}

    def test_wrong_hash_and_missing_role_fail_before_build(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'payload'
            path.write_bytes(b'synthetic')
            lock = self.lock([{'role': 'semantic/native/example.h', 'sha256': '0' * 64}])
            with self.assertRaisesRegex(ValueError, 'hash differs'):
                driver.verify(lock, {'semantic/native/example.h': str(path)})
            with self.assertRaises(KeyError):
                driver.verify(lock, {})

    def test_duplicate_or_escape_role_rejected(self):
        for name in ('../escape', '/absolute'):
            with self.assertRaises(ValueError):
                driver.verify(self.lock([{'role': name, 'sha256': '0' * 64}]), {})
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'payload'
            path.write_bytes(b'synthetic')
            row = {'role': 'semantic/native/example.h', 'sha256': driver.digest(path)}
            with self.assertRaisesRegex(ValueError, 'Duplicate'):
                driver.verify(self.lock([row, row]), {row['role']: str(path)})

    def test_profile_reuses_existing_four_payload_plan(self):
        plan = driver.build_android_client.load_plan(driver.PLAN)
        lock = json.loads(driver.PROFILE.read_bytes())
        self.assertEqual(plan['source_sha256'], lock['base_apk']['sha256'])
        self.assertEqual(len(plan['replacements']), 4)
        self.assertTrue(plan['not_for_production'])
        self.assertEqual(plan['environment'], 'staging')
        self.assertEqual({row['archive_path']: row['sha256'] for row in plan['replacements']},
            {row['role'].removeprefix('v19-r5/payload/'): row['sha256'] for row in lock['expected_replacements']})

    def test_v20_changes_only_reviewed_sources_and_monitor_control(self):
        current = json.loads(driver.PROFILE.read_bytes())
        old = json.loads(driver.PROFILE.with_name('staging-v19-r5-source-lock.json').read_bytes())
        self.assertEqual(current['release'], 'staging-v20')
        self.assertEqual(current['base_apk'], old['base_apk'])
        before = {row['role']: row['sha256'] for row in driver.manifest_rows(old)}
        after = {row['role']: row['sha256'] for row in driver.manifest_rows(current)}
        self.assertEqual(before.keys(), after.keys())
        self.assertEqual({role for role in before if before[role] != after[role]}, {
            'semantic/native/anomaly_monitor_mod.cpp', 'semantic/native/cli_ui_native.h',
            'semantic/native/mod_category_bridge.h', 'semantic/native/sampler_read_probe.h',
            'semantic/native/staging_cli_bridge.h',
            'v19-r5/payload/lib/arm64-v8a/libakaineanomaly_monitor.so'})
        checkout = json.loads(driver.CHECKOUT_SOURCES.read_bytes())
        self.assertEqual(checkout['source_lock_sha256'], driver.digest(driver.PROFILE))

    def test_checkout_source_overrides_private_map_and_missing_checkout_rejects(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = root / 'runtime/example.h'
            source.parent.mkdir()
            source.write_bytes(b'checkout')
            role = 'semantic/native/example.h'
            document = {'schema': 'akaine.checkout-sources.v1', 'authored_sources':
                        [{'role': role, 'repo_path': 'runtime/example.h'}]}
            lock = self.lock([{'role': role, 'sha256': driver.digest(source)}])
            paths = driver.checkout_paths(lock, {role: 'ignored-private-copy'}, document, root)
            self.assertEqual(paths[role], str(source.resolve()))
            self.assertNotIn('base/v18-staging.apk', paths)
            source.unlink()
            with self.assertRaisesRegex(ValueError, 'hash differs'):
                driver.verify(lock, paths)

    def test_checkout_source_unknown_duplicate_or_escape_rejected(self):
        role = 'semantic/native/example.h'
        lock = self.lock([{'role': role, 'sha256': '0' * 64}])
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            for rows in (
                [{'role': 'unknown', 'repo_path': 'example.h'}],
                [{'role': role, 'repo_path': '../outside.h'}],
                [{'role': role, 'repo_path': '/absolute.h'}],
                [{'role': role, 'repo_path': 'example.h'}] * 2,
            ):
                with self.assertRaises(ValueError):
                    driver.checkout_paths(lock, {}, {'schema': 'akaine.checkout-sources.v1',
                                                    'authored_sources': rows}, root)


if __name__ == '__main__':
    unittest.main()
