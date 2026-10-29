"""Actual route/helper fixtures for both dynamic and legacy pack responses."""
import ast
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
import unittest


SOURCE = Path(__file__).resolve().parents[1] / 'server/user.py'


def route_namespace(source, dynamic, app_version, full_unlock, worlds):
    tree = ast.parse(source.read_bytes())
    namespace = {'CLIENT_PACK_PROJECTION_APP_VERSION': '7.0.255',
                 'CLIENT_PACK_PROJECTION_7_0_255': ('legacy-base', 'legacy-fan'),
                 'Config': SimpleNamespace(WORLD_SONG_FULL_UNLOCK=full_unlock),
                 'request': SimpleNamespace(headers={'AppVersion': app_version}),
                 'uses_dynamic_packs': lambda headers: dynamic,
                 'pack_ids_for_dynamic_user': lambda user, headers: ['dynamic-owned', 'dynamic-append'],
                 'client_pack_projection_for_app_version': lambda version: ('legacy-base',) if version == '7.0.255' else None,
                 'success_return': lambda result: result}
    calls = []
    class Connect:
        def __enter__(self): return 'synthetic-cursor'
        def __exit__(self, *unused): return False
    class User:
        def __init__(self, cursor, user_id):
            calls.append(('identity', cursor, user_id))
        def to_dict(self, **kwargs):
            calls.append(('serializer', kwargs))
            return {'packs': ['original-pack'], 'world_songs': worlds, 'unrelated': {'score': 9876543}}
    namespace.update(Connect=Connect, UserOnline=User)
    nodes = [deepcopy(node) for node in tree.body if isinstance(node, ast.FunctionDef)
             and node.name in ('apply_client_world_song_projection', 'user_me')]
    for node in nodes:
        node.decorator_list = []
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(source), 'exec'), namespace)
    return namespace, calls


class DieInWorldProjectionTests(unittest.TestCase):
    def test_dynamic_and_legacy_exact_app_add_only_missing_world_tokens_and_preserve_packs(self):
        for dynamic in (False, True):
            for worlds in ([], ['existing-world'], ['diein'], ['diein4', 'diein', 'existing-world']):
                with self.subTest(dynamic=dynamic, worlds=worlds):
                    original = list(worlds)
                    namespace, calls = route_namespace(SOURCE, dynamic, '7.0.255', True, worlds)
                    result = namespace['user_me'](7)
                    self.assertEqual(result['world_songs'], original + [key for key in ('diein', 'diein4') if key not in original])
                    self.assertEqual(worlds, original)
                    self.assertEqual(result['packs'], ['dynamic-owned', 'dynamic-append'] if dynamic else ['legacy-base', 'legacy-fan'])
                    self.assertEqual(result['unrelated'], {'score': 9876543})
                    self.assertEqual(sum(name == 'serializer' for name, *unused in calls), 1)

    def test_other_versions_or_disabled_full_unlock_preserve_world_list_identity(self):
        for dynamic in (False, True):
            for version, full in ((None, True), ('6.15.0', True), ('7.0.254', True), ('7.0.255.0', True), ('7.0.255', False)):
                with self.subTest(dynamic=dynamic, version=version, full=full):
                    worlds = ['existing-world']
                    namespace, calls = route_namespace(SOURCE, dynamic, version, full, worlds)
                    result = namespace['user_me'](7)
                    self.assertIs(result['world_songs'], worlds)
                    self.assertEqual(worlds, ['existing-world'])

    def test_projection_repeated_application_is_idempotent(self):
        namespace, calls = route_namespace(SOURCE, True, '7.0.255', True, ['existing-world'])
        result = namespace['user_me'](7)
        before = deepcopy(result)
        namespace['apply_client_world_song_projection'](result, '7.0.255')
        self.assertEqual(result, before)


if __name__ == '__main__':
    unittest.main()
