"""Catalog parent graph validation; no bundle bytes or output are written."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

spec = importlib.util.spec_from_file_location('cycle_candidate_builder', Path(__file__).with_name('build_content_bundle.py'))
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)


class CatalogParentCycles(unittest.TestCase):
    def validate(self, packs):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            songlist, packlist = root / 'songlist', root / 'packlist'
            songlist.write_text(json.dumps({'songs': [{'id': 'existing', 'set': packs[0]['id']}]}))
            packlist.write_text(json.dumps({'packs': packs}))
            builder.validate_catalog(root, {}, {'songs/songlist': songlist, 'songs/packlist': packlist})

    def test_self_parent_and_multi_node_cycle_reject(self):
        for packs in ([{'id': 'a', 'pack_parent': 'a'}],
                      [{'id': 'a', 'pack_parent': 'b'}, {'id': 'b', 'pack_parent': 'a'}],
                      [{'id': 'root'}, {'id': 'a', 'pack_parent': 'b'},
                       {'id': 'b', 'pack_parent': 'c'}, {'id': 'c', 'pack_parent': 'a'}]):
            with self.subTest(packs=packs), self.assertRaisesRegex(ValueError, 'pack-parent-cycle'):
                self.validate(packs)

    def test_valid_shared_parent_and_deep_hierarchy_accept(self):
        self.validate([{'id': 'root'}, {'id': 'a', 'pack_parent': 'root'}, {'id': 'b', 'pack_parent': 'root'}])
        self.validate([{'id': 'p0'}] + [{'id': 'p%d' % i, 'pack_parent': 'p%d' % (i - 1)} for i in range(1, 4096)])

    def test_missing_parent_still_rejects(self):
        with self.assertRaisesRegex(ValueError, 'pack-parent-missing'):
            self.validate([{'id': 'a', 'pack_parent': 'missing'}])


if __name__ == '__main__':
    unittest.main()
