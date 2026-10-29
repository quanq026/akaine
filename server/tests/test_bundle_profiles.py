"""Actual parser/serializer/route AST fixtures; temporary tiny files, no network."""
import ast
from copy import deepcopy
from functools import lru_cache
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile
from time import time
from types import SimpleNamespace
import unittest

HERE = Path(__file__).resolve().parents[1]
APP, CAP, OTHER_CAP = '7.0.255', 'a' * 64, 'b' * 64


class NoData(Exception):
    def __init__(self, message, status=None):
        super().__init__(message)
        self.status = status


def load_classes(config, folder):
    parsed = ast.parse((HERE / 'core/bundle.py').read_bytes())
    classes = [node for node in parsed.body if isinstance(node, ast.ClassDef)
               and node.name in ('ContentBundle', 'BundleParser', 'BundleDownload')]
    namespace = {'json': json, 'os': os, 're': re, 'lru_cache': lru_cache, 'time': time,
                 'Config': config, 'NoData': NoData, 'NoAccess': NoData, 'RateLimit': NoData,
                 'ArcLimiter': lambda *unused: None,
                 'url_for': lambda *unused, **kwargs: 'https://fixture.invalid/token/' + kwargs['token'],
                 'Constant': SimpleNamespace(CONTENT_BUNDLE_FOLDER_PATH=str(folder),
                     BUNDLE_DOWNLOAD_TIMES_LIMIT=1, BUNDLE_DOWNLOAD_LINK_PREFIX='https://fixture.invalid/bundles/')}
    exec(compile(ast.Module(body=classes, type_ignores=[]), '<actual-profile-candidate-classes>', 'exec'), namespace)
    return namespace


def manifest(version, previous=None, app=APP, parts=1):
    return {'versionNumber': version, 'previousVersionNumber': previous, 'applicationVersionNumber': app,
            'uuid': version + ('root' if previous is None else previous), 'totalPartitions': parts,
            'added': [{'path': 'fixture' + str(index), 'partIndex': index, 'byteOffset': 0, 'length': index + 3}
                      for index in range(parts)], 'removed': [], 'pathToHash': {}, 'pathToDetails': {}}


class BundleProfileTests(unittest.TestCase):
    def test_actual_config_loader_recognizes_default_off_profile_settings(self):
        tree = ast.parse((HERE / 'core/config_manager.py').read_bytes())
        namespace = {}
        exec(compile(ast.Module(body=[node for node in tree.body if isinstance(node, ast.ClassDef)], type_ignores=[]),
                     '<actual-Config-and-ConfigManager>', 'exec'), namespace)
        config = namespace['Config']
        self.assertFalse(config.BUNDLE_ASSETSET_PROFILES_ENABLED)
        self.assertEqual(config.BUNDLE_ASSETSET_PROFILE_DEVICES, [])
        self.assertEqual(config.BUNDLE_ASSETSET_PROFILES, {})
        namespace['ConfigManager'].load(SimpleNamespace(BUNDLE_ASSETSET_PROFILES_ENABLED=True,
                                                        BUNDLE_ASSETSET_PROFILES={APP: {'fixture': True}}))
        self.assertTrue(config.BUNDLE_ASSETSET_PROFILES_ENABLED)
        self.assertEqual(config.BUNDLE_ASSETSET_PROFILES, {APP: {'fixture': True}})

    def test_combined_config_preserves_secure_defaults_and_independent_dynamic_controls(self):
        namespace = {}
        exec(compile(ast.parse((HERE / 'core/config_manager.py').read_bytes()), '<combined-Config>', 'exec'), namespace)
        config = namespace['Config']
        for name in ('USERNAME', 'PASSWORD', 'SECRET_KEY', 'LINKPLAY_AUTHENTICATION', 'LINKPLAY_TCP_SECRET_KEY'):
            self.assertEqual(getattr(config, name), '')
        self.assertFalse(config.INSECURE_LOCAL_OAUTH_COMPAT_ENABLED)
        self.assertFalse(config.DYNAMIC_PACKS_ENABLED)
        self.assertFalse(config.DYNAMIC_PACKS_NATIVE_ACCEPTED)
        self.assertFalse(config.DYNAMIC_PACKS_FULL_CATALOG)
        namespace['ConfigManager'].load(SimpleNamespace(BUNDLE_ASSETSET_PROFILES_ENABLED=True))
        self.assertFalse(config.DYNAMIC_PACKS_ENABLED)
        namespace['ConfigManager'].load(SimpleNamespace(DYNAMIC_PACKS_ENABLED=True))
        self.assertTrue(config.BUNDLE_ASSETSET_PROFILES_ENABLED)
        self.assertEqual(config.BUNDLE_ASSETSET_PROFILE_DEVICES, [])

    def test_repo_no_store_hook_and_app_version_download_prefix_are_preserved(self):
        functions = {node.name: deepcopy(node) for node in ast.parse((HERE / 'server/others.py').read_bytes()).body
                     if isinstance(node, ast.FunctionDef)}
        for node in functions.values():
            node.decorator_list = []
        request = SimpleNamespace(endpoint='others.game_content_bundle', headers={'AppVersion': APP},
                                  args=SimpleNamespace(getlist=lambda key: ['fixture-song'], get=lambda key, default: default))
        response = SimpleNamespace(headers={})
        namespace = {'request': request}
        exec(compile(ast.Module(body=[functions['no_store_content_bundle']], type_ignores=[]), '<actual-no-store>', 'exec'), namespace)
        self.assertIs(namespace['no_store_content_bundle'](response), response)
        self.assertEqual(response.headers, {'Cache-Control': 'private, no-store'})
        request.endpoint = 'others.game_info'
        self.assertEqual(namespace['no_store_content_bundle'](SimpleNamespace(headers={})).headers, {})
        calls = []
        class Connection:
            def __enter__(self): return 'fixture-cursor'
            def __exit__(self, *unused): return False
        class Download:
            is_limited = False
            urls = {'fixture-song': 'synthetic-download-result'}
            def __init__(self, cursor, user, app_version): calls.append((cursor, user, app_version))
            def add_songs(self): pass
        namespace.update({'Connect': lambda **unused: Connection(), 'UserOnline': lambda cursor, user_id: ('user', user_id),
                          'DownloadList': Download, 'json': json, 'RateLimit': NoData, 'success_return': lambda value: value})
        exec(compile(ast.Module(body=[functions['download_song']], type_ignores=[]), '<actual-download-route>', 'exec'), namespace)
        self.assertEqual(namespace['download_song'](7), Download.urls)
        self.assertEqual(calls, [('fixture-cursor', ('user', 7), APP)])

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.folder = Path(self.temporary.name)
        self.config = SimpleNamespace(BUNDLE_STRICT_MODE=False, BUNDLE_DOWNLOAD_LINK_PREFIX='https://fixture.invalid/bundles/',
            BUNDLE_ASSETSET_PROFILES_ENABLED=False, BUNDLE_ASSETSET_PROFILE_DEVICES=None, BUNDLE_ASSETSET_PROFILES={APP: {
                'full': {'target': APP + '.22', 'manifests': ['full22.json']},
                CAP: {'target': APP + '.21', 'migration_from': [APP + '.20'],
                      'manifests': ['thin21.json', 'thin20to21.json']}}})
        for name, data in [('legacy20', manifest(APP + '.20')), ('full22', manifest(APP + '.22', parts=2)),
                           ('thin21', manifest(APP + '.21')), ('thin20to21', manifest(APP + '.21', APP + '.20'))]:
            (self.folder / (name + '.json')).write_text(json.dumps(data))
        self.namespace = load_classes(self.config, self.folder)
        self.Parser = self.namespace['BundleParser']
        self.Parser()

    def tearDown(self):
        self.temporary.cleanup()

    def test_device_scope_canary_does_not_upgrade_other_devices(self):
        self.config.BUNDLE_ASSETSET_PROFILES_ENABLED = True
        self.config.BUNDLE_ASSETSET_PROFILE_DEVICES = ['qa-device']
        self.Parser.get_bundles.cache_clear()
        for device in (None, '', 'other-device'):
            self.assertEqual([x.version for x in self.Parser.get_bundles(APP, APP + '.19', device, CAP)], [APP + '.20'])
            self.assertEqual(self.Parser.get_bundles(APP, APP + '.21', device, None), [])
        self.assertEqual([x.version for x in self.Parser.get_bundles(APP, APP + '.20', 'qa-device', CAP)], [APP + '.21'])
        self.assertEqual([x.version for x in self.Parser.get_bundles(APP, APP + '.21', 'qa-device', None)], [APP + '.22'])
        self.config.BUNDLE_ASSETSET_PROFILE_DEVICES = []
        self.Parser.get_bundles.cache_clear()
        self.assertEqual([x.version for x in self.Parser.get_bundles(APP, APP + '.19', 'qa-device', CAP)], [APP + '.20'])

    def test_invalid_operator_device_scope_rejects(self):
        for value in ('all', True, [None], [''], ['bad\nID'], ['a' * 257]):
            self.config.BUNDLE_ASSETSET_PROFILE_DEVICES = value
            with self.assertRaises(ValueError): self.Parser().re_init()

    def test_default_off_retains_legacy_and_registered_profiles_do_not_autoactivate(self):
        for capability in (None, '', CAP, OTHER_CAP):
            rows = self.Parser.get_bundles(APP, APP + '.19', None, capability)
            self.assertEqual([row.version for row in rows], [APP + '.20'])
        self.assertEqual(self.Parser.get_bundles(APP, APP + '.20', None, CAP), [])
        self.assertEqual(len(self.Parser.version_tuple_bundles), 1)
        self.assertEqual(len(self.Parser.profile_edges), 3)
        download = self.namespace['BundleDownload'](None)
        for invalid in ('x' * 4096, CAP.upper(), None, '', CAP + ',x'):
            download.set_client_info(APP, '0.0.0', None, invalid)
            self.assertIsNone(download.assetset)

    def test_versions_zero_19_20_21_22_23_for_exact_unknown_and_missing_capability(self):
        self.config.BUNDLE_ASSETSET_PROFILES_ENABLED = True
        self.Parser.get_bundles.cache_clear()
        for capability in (CAP, None, '', OTHER_CAP, CAP.upper(), 'full', 'a' * 63, CAP + ',x'):
            target = 21 if capability == CAP else 22
            for version in (0, 19, 20, 21, 22, 23):
                current = '0.0.0' if not version else APP + '.' + str(version)
                with self.subTest(capability=capability, current=current):
                    rows = self.Parser.get_bundles(APP, current, None, capability)
                    self.assertEqual([row.version for row in rows], [APP + '.' + str(target)] if version < target else [])
                    if rows:
                        self.assertIn('thin' if capability == CAP else 'full', rows[0].json_path)
                        expected_prev = APP + '.20' if capability == CAP and version == 20 else '0.0.0'
                        self.assertEqual(rows[0].prev_version, expected_prev)

    def test_no_cross_profile_delta_and_same_numeric_edge_namespaces_are_distinct(self):
        self.config.BUNDLE_ASSETSET_PROFILES_ENABLED = True
        self.Parser.get_bundles.cache_clear()
        full = self.Parser.get_bundles(APP, APP + '.20', None, None)
        thin = self.Parser.get_bundles(APP, APP + '.20', None, CAP)
        self.assertEqual(full[0].prev_version, '0.0.0')
        self.assertEqual(thin[0].prev_version, APP + '.20')
        # Another exact asset set may have the same21 root without colliding.
        self.config.BUNDLE_ASSETSET_PROFILES[APP][OTHER_CAP] = {'target': APP + '.21', 'manifests': ['other21.json']}
        (self.folder / 'other21.json').write_text(json.dumps(manifest(APP + '.21')))
        self.Parser().re_init()
        self.assertEqual(self.Parser.get_bundles(APP, '0.0.0', None, OTHER_CAP)[0].json_path, 'other21.json')
        self.assertEqual(self.Parser.get_bundles(APP, '0.0.0', None, CAP)[0].json_path, 'thin21.json')

    def test_exact_capability_lost_at_thin21_recovers_full22_and_never_downgrades(self):
        self.config.BUNDLE_ASSETSET_PROFILES_ENABLED = True
        self.Parser.get_bundles.cache_clear()
        self.assertEqual(self.Parser.get_bundles(APP, APP + '.21', None, None)[0].json_path, 'full22.json')
        self.assertEqual(self.Parser.get_bundles(APP, APP + '.22', None, CAP), [])

    def test_missing_manifest_dependency_cycle_duplicate_and_wrong_app_reject(self):
        cases = []
        bad = manifest(APP + '.21', APP + '.19')
        cases.append(('thin20to21.json', bad))
        cases.append(('thin20to21.json', manifest(APP + '.21', APP + '.21')))
        cases.append(('thin20to21.json', manifest(APP + '.20', APP + '.21')))
        cases.append(('thin20to21.json', manifest(APP + '.21')))
        cases.append(('thin21.json', manifest(APP + '.21', app='7.0.254')))
        for name, value in cases:
            path = self.folder / name
            original = path.read_bytes()
            path.write_text(json.dumps(value))
            with self.subTest(name=name, previous=value['previousVersionNumber']):
                with self.assertRaises(ValueError): self.Parser().re_init()
            path.write_bytes(original)
            self.Parser().re_init()
        path = self.folder / 'thin21.json'
        path.rename(path.with_suffix('.disabled'))
        with self.assertRaises(ValueError): self.Parser().re_init()

    def test_configuration_rejects_shared_target_and_unsafe_allowlist(self):
        original = deepcopy(self.config.BUNDLE_ASSETSET_PROFILES)
        self.config.BUNDLE_ASSETSET_PROFILES[APP]['full']['target'] = APP + '.21'
        with self.assertRaises(ValueError): self.Parser.profile_manifest_specs()
        for name in ('../escape.json', '/absolute.json', 'C:/absolute.json', 'unsafe\\file.json'):
            self.config.BUNDLE_ASSETSET_PROFILES = deepcopy(original)
            self.config.BUNDLE_ASSETSET_PROFILES[APP][CAP]['manifests'] = [name]
            with self.assertRaises(ValueError): self.Parser.profile_manifest_specs()

    def test_enabled_profiles_reject_legacy_control_conflicts_and_invalid_full_target(self):
        self.config.BUNDLE_ASSETSET_PROFILES_ENABLED = True
        for name, value in (('BUNDLE_STRICT_MODE', True), ('FRESH_INSTALL_ONLY_BUNDLE_VERSION', APP + '.20'),
                            ('FRESH_INSTALL_DEVICE_BUNDLE_OVERRIDES', {'fixture-device': APP + '.20'})):
            original = getattr(self.config, name, None)
            setattr(self.config, name, value)
            with self.subTest(control=name):
                with self.assertRaisesRegex(ValueError, 'conflict'): self.Parser.profile_manifest_specs()
            setattr(self.config, name, original)
        for invalid in (None, 22, 'bad', '7.0.255', [], APP + '.x'):
            self.config.BUNDLE_ASSETSET_PROFILES[APP]['full']['target'] = invalid
            with self.subTest(target=invalid):
                with self.assertRaisesRegex(ValueError, 'Full profile version'): self.Parser.profile_manifest_specs()

    def test_actual_serializer_single_and_multipart_shape_and_manifest_bytes_unchanged(self):
        self.config.BUNDLE_ASSETSET_PROFILES_ENABLED = True
        self.Parser.get_bundles.cache_clear()
        before = {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in self.folder.glob('*.json')}
        Download = self.namespace['BundleDownload']
        for capability, expected_parts in ((CAP, 1), (None, 2)):
            download = Download(None)
            download.set_client_info(APP, '0.0.0', None, capability)
            row = download.get_bundle_list()[0]
            self.assertEqual('bundleParts' in row, expected_parts > 1)
            self.assertTrue(row['bundleUrl'].endswith('.cb'))
            self.assertEqual(row['bundleSize'], sum(range(3, 3 + expected_parts)))
            if expected_parts > 1:
                self.assertEqual(len(row['bundleParts']), expected_parts)
                self.assertEqual(row['bundleParts'][0]['url'], row['bundleUrl'])
        after = {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in self.folder.glob('*.json')}
        self.assertEqual(before, after)

    def test_profile_manifest_versions_reject_noncanonical_numeric_identity(self):
        path = self.folder / 'thin20to21.json'
        original = path.read_bytes()
        for field in ('versionNumber', 'previousVersionNumber'):
            for invalid in ('7.0.255', '0.0.0', '7.0.255.021', '7.00.255.21', '7.0.255.-1', '7.0.255.+21',
                            '7.0.255.21.0', '\u0667.0.255.21', '', 21, [], None):
                if field == 'previousVersionNumber' and invalid is None:
                    continue  # JSON null is the native full-root sentinel.
                document = manifest(APP + '.21', APP + '.20')
                document[field] = invalid
                path.write_text(json.dumps(document))
                with self.subTest(field=field, invalid=invalid):
                    with self.assertRaisesRegex(ValueError, 'canonical numeric'):
                        self.Parser().re_init()
                path.write_bytes(original)
                self.Parser().re_init()

    def test_only_null_previous_is_a_full_root(self):
        path = self.folder / 'thin21.json'
        original = path.read_bytes()
        document = json.loads(original)
        self.assertIsNone(document['previousVersionNumber'])
        for previous in ('0.0.0', '0.0.0.0'):
            document['previousVersionNumber'] = previous
            path.write_text(json.dumps(document))
            with self.subTest(previous=previous):
                with self.assertRaises(ValueError): self.Parser().re_init()
            path.write_bytes(original)
            self.Parser().re_init()

    def test_profile_config_targets_and_anchors_reject_numeric_aliases(self):
        original = deepcopy(self.config.BUNDLE_ASSETSET_PROFILES)
        for invalid in ('7.0.255.021', '7.00.255.21', '7.0.255', '\u0667.0.255.21'):
            for profile in ('full', CAP):
                self.config.BUNDLE_ASSETSET_PROFILES = deepcopy(original)
                self.config.BUNDLE_ASSETSET_PROFILES[APP][profile]['target'] = invalid
                with self.subTest(profile=profile, target=invalid):
                    with self.assertRaises(ValueError): self.Parser.profile_manifest_specs()
            self.config.BUNDLE_ASSETSET_PROFILES = deepcopy(original)
            self.config.BUNDLE_ASSETSET_PROFILES[APP][CAP]['migration_from'] = [invalid]
            with self.subTest(anchor=invalid):
                with self.assertRaisesRegex(ValueError, 'anchor'): self.Parser.profile_manifest_specs()

    def test_actual_route_forwards_asset_header_without_advertising_native_capability(self):
        function = next(node for node in ast.parse((HERE / 'server/others.py').read_bytes()).body
                        if isinstance(node, ast.FunctionDef) and node.name == 'game_content_bundle')
        function.decorator_list = []
        calls = []
        logs = []
        class Connection:
            def __enter__(self): return None
            def __exit__(self, *unused): return False
        class Download:
            def __init__(self, connection): pass
            def set_client_info(self, *values):
                calls.append(values)
                self.assetset = values[-1] if isinstance(values[-1], str) and re.fullmatch("[0-9a-f]{64}", values[-1]) else None
            def get_bundle_list(self): return []
        namespace = {'request': SimpleNamespace(headers={'AppVersion': APP, 'ContentBundle': APP + '.20', 'Akaine-Assets': CAP}),
                     'Connect': lambda **unused: Connection(), 'BundleDownload': Download,
                     'current_app': SimpleNamespace(logger=SimpleNamespace(info=lambda *values: logs.append(values))), 'success_return': lambda value: value}
        exec(compile(ast.Module(body=[function], type_ignores=[]), '<actual-candidate-route>', 'exec'), namespace)
        self.assertEqual(namespace['game_content_bundle'](), {'orderedResults': []})
        self.assertEqual(calls, [(APP, APP + '.20', None, CAP)])
        self.assertEqual(logs[0][-1], CAP)
        namespace['request'].headers['Akaine-Assets'] = 'invalid\nheader'
        namespace['game_content_bundle']()
        self.assertEqual(logs[-1][-1], 'none')


if __name__ == '__main__':
    unittest.main()
