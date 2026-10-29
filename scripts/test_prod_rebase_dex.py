"""Finite production DEX normalization rejects wrong provenance and extra changes."""
from pathlib import Path
import tempfile
import unittest

import build_prod_rebase_dex as rebase


class ProdRebaseDexTests(unittest.TestCase):
    def setUp(self):
        self.before = (rebase.PATCH / 'baseline_setAnimationInterval.smali').read_text().rstrip()
        self.after = (rebase.PATCH / 'setAnimationInterval.smali').read_text().rstrip()
        self.old = {f'fixture/Class{i}.smali': '.class public Lfixture/Class;\n' for i in range(724)}
        self.old[rebase.RENDERER] = '.class public LRenderer;\n\n' + self.before + '\n\n.method public other()V\n    return-void\n.end method\n'
        self.new = dict(self.old)
        self.new[rebase.RENDERER] = rebase.normalize_renderer(self.old[rebase.RENDERER], self.before, self.after)

    def test_valid_exact_method_only_change_preserves_all_other_class_and_method_bytes(self):
        proof = rebase.compare_classes(self.old, self.new, self.before, self.after)
        self.assertEqual(proof['unchanged_classes'], 724)
        self.assertTrue(proof['all_other_methods_class_metadata_and_classes_identical'])

    def test_wrong_or_repeated_method_preimage_rejected(self):
        for text in (self.old[rebase.RENDERER].replace('.registers 3', '.registers 4'), self.new[rebase.RENDERER],
                     self.old[rebase.RENDERER] + '\n' + self.before):
            with self.assertRaisesRegex(ValueError, 'method preimage'):
                rebase.normalize_renderer(text, self.before, self.after)

    def test_modified_replacement_rejected(self):
        with self.assertRaisesRegex(ValueError, 'Authored interval patch'):
            rebase.normalize_renderer(self.old[rebase.RENDERER], self.before, self.after.replace('0xfe502a', '0xfe502b'))

    def test_unrelated_class_method_or_metadata_change_rejected(self):
        for name, suffix in (('fixture/Class1.smali', '\n# changed\n'), (rebase.RENDERER, '\n.field new:I\n')):
            changed = dict(self.new); changed[name] += suffix
            with self.assertRaises(ValueError):
                rebase.compare_classes(self.old, changed, self.before, self.after)
        changed = dict(self.new)
        changed[rebase.RENDERER] = changed[rebase.RENDERER].replace('.method public other()V', '.method public renamed()V')
        with self.assertRaisesRegex(ValueError, 'Another renderer method or metadata'):
            rebase.compare_classes(self.old, changed, self.before, self.after)

    def test_added_or_removed_class_rejected(self):
        changed = dict(self.new); changed['extra.smali'] = '.class LExtra;'
        with self.assertRaisesRegex(ValueError, 'class set'):
            rebase.compare_classes(self.old, changed, self.before, self.after)

    def test_wrong_production_members_and_APK_fail_before_output(self):
        with self.assertRaisesRegex(ValueError, 'Authentic production DEX members'):
            rebase.validate_members(b'wrong DEX3', b'wrong DEX4')
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); apk = root / 'unknown.apk'; apk.write_bytes(b'unknown')
            with self.assertRaisesRegex(ValueError, 'Authentic production V9 whole APK'):
                rebase.build(apk, root / 'java', root / 'jar', root / 'RawDexTool.java', root / 'output')
            self.assertFalse((root / 'output').exists())


if __name__ == '__main__':
    unittest.main()
