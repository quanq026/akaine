import json
import unittest

import worker_catalog_patch as patcher


class PatchTests(unittest.TestCase):
    def setUp(self):
        self.before = {'old_song': ['2.aff', 'base.ogg']}
        self.source = '// keep byte prefix\n' + patcher.MARKER + json.dumps(self.before) + ';\n// keep routing and bindings behavior\n'
        self.additions = {'aurora_example': ['0.aff', '2.aff', 'base.ogg', 'video_1080.mp4', 'effect.wav']}

    def test_additive_literal_only_and_owned_rollback(self):
        candidate, receipt = patcher.patch(self.source, self.additions)
        prefix, data, suffix = patcher.split(candidate)
        self.assertEqual(data, {**self.before, **self.additions})
        self.assertEqual(prefix, patcher.split(self.source)[0])
        self.assertEqual(suffix, patcher.split(self.source)[2])
        restored = patcher.rollback(candidate, self.additions, receipt['added_ids'])
        self.assertEqual(patcher.split(restored)[1], self.before)

    def test_collision_and_unsafe_inputs_rejected(self):
        for additions in ({'old_song': ['base.ogg']}, {'aurora_x': ['../2.aff', 'base.ogg']},
                          {'aurora_x': ['base.ogg', 'base.ogg']}, {'aurora_x': ['5.aff', 'base.ogg']},
                          {'aurora_x': ['2.aff']}, {}):
            with self.assertRaises(ValueError):
                patcher.patch(self.source, additions)
        with self.assertRaises(ValueError):
            patcher.patch(self.source.replace('old_song', 'aurora_example'), self.additions)

    def test_rollback_preserves_concurrent_unrelated_entry(self):
        candidate, receipt = patcher.patch(self.source, self.additions)
        prefix, data, suffix = patcher.split(candidate)
        data['another_new_song'] = ['base.ogg']
        current = prefix + json.dumps(data) + suffix
        result = patcher.split(patcher.rollback(current, self.additions, receipt['added_ids']))[1]
        self.assertEqual(result, {**self.before, 'another_new_song': ['base.ogg']})
        data['aurora_example'].append('3.aff')
        with self.assertRaisesRegex(ValueError, 'owned_entry_changed'):
            patcher.rollback(prefix + json.dumps(data) + suffix, self.additions, receipt['added_ids'])

    def test_ambiguous_or_duplicate_static_assignment_rejected(self):
        for source in (self.source + self.source, self.source.replace('old_song', 'old_song\":[],\"old_song')):
            with self.assertRaises(ValueError):
                patcher.patch(source, self.additions)


if __name__ == '__main__':
    unittest.main()
