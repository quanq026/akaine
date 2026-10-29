"""Actual version-gated content projections preserve scores and cloud compatibility."""
import ast
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
import unittest


SOURCE = Path(__file__).resolve().parents[1] / 'server/user.py'
KEEP = {'CLIENT_PACK_PROJECTION_APP_VERSION', 'CLIENT_UNLOCK_PROJECTION_7_0_255',
        'CLIENT_UNLOCK_COMPLETE_BY_TYPE_7_0_255', 'CLIENT_UNLOCK_MINIMUM_BY_KEY_7_0_255',
        'CLIENT_STORY_PROJECTION_7_0_255', 'TESTIFY_CLOUD_FIELDS', 'CLEAR_STATE'}
METHODS = {'apply_client_unlock_projection', 'apply_client_story_projection', 'replace_cloud_score_song_id',
           'merge_testify_cloud_rows', 'canonicalize_cloud_score_song_ids', 'project_cloud_score_song_ids'}


def projection_methods():
    nodes = [node for node in ast.parse(SOURCE.read_bytes()).body
             if isinstance(node, ast.FunctionDef) and node.name in METHODS
             or isinstance(node, ast.Assign) and any(isinstance(target, ast.Name) and target.id in KEEP for target in node.targets)]
    namespace = {}
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(SOURCE), 'exec'), namespace)
    return namespace


class ContentProjectionParityTests(unittest.TestCase):
    def setUp(self):
        self.methods = projection_methods()

    def test_arghena_each_difficulty_minimum_preserves_greater_progress_and_is_idempotent(self):
        rows = [{'unlock_key': 'arghena|%d|110' % difficulty, 'complete': value}
                for difficulty, value in enumerate((999, 300000, None))]
        rows.append({'unlock_key': 'unrelated|0|110', 'complete': 8123})
        save = SimpleNamespace(unlocklist_data=rows)
        self.methods['apply_client_unlock_projection'](save, '7.0.255')
        self.assertEqual([row['complete'] for row in rows[:4]], [200000, 300000, 200000, 8123])
        before = deepcopy(rows)
        self.methods['apply_client_unlock_projection'](save, '7.0.255')
        self.assertEqual(rows, before)

    def test_empty_projection_adds_three_arghena_minima_and_retains_other_completion_types(self):
        save = SimpleNamespace(unlocklist_data=[])
        self.methods['apply_client_unlock_projection'](save, '7.0.255')
        rows = {row['unlock_key']: row['complete'] for row in save.unlocklist_data}
        for difficulty in range(3):
            self.assertEqual(rows['arghena|%d|110' % difficulty], 200000)
        self.assertEqual(rows['arghena|0|108'], 1)
        self.assertEqual(rows['arghena|0|103'], 999)
        self.assertEqual(rows['testify|3|104'], 1)

    def test_eight_stage_story_rows_and_existing_chapter24_preserve_unrelated_data(self):
        extra = ((15, 6), (16, 6), (20, 7), (103, 1), (101, 8), (1, 9), (2, 9), (2, 3))
        save = SimpleNamespace(story_data=[{'ma': 15, 'mi': 6, 'c': False, 'r': False, 'unrelated': 'kept'},
                                          {'ma': 999, 'mi': 1, 'c': False}])
        self.methods['apply_client_story_projection'](save, '7.0.255')
        rows = {(row['ma'], row['mi']): row for row in save.story_data}
        for key in (*extra, *((24, index) for index in range(1, 11))):
            self.assertTrue(rows[key]['c'])
            self.assertTrue(rows[key]['r'])
        self.assertEqual(rows[(15, 6)]['unrelated'], 'kept')
        self.assertEqual(rows[(999, 1)], {'ma': 999, 'mi': 1, 'c': False})
        before = deepcopy(save.story_data)
        self.methods['apply_client_story_projection'](save, '7.0.255')
        self.assertEqual(save.story_data, before)

    def test_other_client_versions_and_nonlist_data_are_unchanged(self):
        for version in (None, '', '6.15.0', '7.0.254', '7.0.255.0'):
            save = SimpleNamespace(unlocklist_data=[{'unlock_key': 'arghena|0|110', 'complete': 1}],
                                   story_data=[{'ma': 15, 'mi': 6, 'c': False}])
            before = deepcopy(vars(save))
            self.methods['apply_client_unlock_projection'](save, version)
            self.methods['apply_client_story_projection'](save, version)
            self.assertEqual(vars(save), before)
        for invalid in (None, {}, 'malformed'):
            save = SimpleNamespace(unlocklist_data=invalid, story_data=invalid)
            self.methods['apply_client_unlock_projection'](save, '7.0.255')
            self.methods['apply_client_story_projection'](save, '7.0.255')
            self.assertEqual(save.unlocklist_data, invalid)
            self.assertEqual(save.story_data, invalid)

    def test_retained_testify_cloud_canonicalization_and_legacy_projection(self):
        save = SimpleNamespace(scores_data=[{'song_id': 'testify1', 'difficulty': 3, 'score': 8765432},
                                            {'song_id': 'testify', 'difficulty': 3, 'score': 9876543}],
                               clearlamps_data=[{'song_id': 'testify1', 'difficulty': 3, 'clear_type': 1}],
                               clearedsongs_data=[{'song_id': 'testify1', 'difficulty': 3, 'grade': 6}])
        self.methods['project_cloud_score_song_ids'](save, '7.0.255')
        self.assertEqual(save.scores_data, [{'song_id': 'testify', 'difficulty': 3, 'score': 9876543}])
        self.methods['project_cloud_score_song_ids'](save, '6.15.0')
        self.assertEqual(save.scores_data, [{'song_id': 'testify1', 'difficulty': 3, 'score': 9876543}])


if __name__ == '__main__':
    unittest.main()
