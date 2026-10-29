"""Tiny synthetic full-root recipes; no native media, keys or deployment actions."""
from contextlib import ExitStack
from copy import deepcopy
import base64
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import build_prod_aurora_bundle as composer


def blob_sha(raw):
    return hashlib.sha256(raw).hexdigest()


class ProdAuroraBundleTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.stack = ExitStack()
        self.old_songlist = {'songs': [{'id': 'old', 'set': 'single', 'remote_dl': True}]}
        self.union = {'songs': self.old_songlist['songs'] + [{'id': 'aurora_new', 'set': 'single', 'remote_dl': True}]}
        data = {'songs/songlist': json.dumps(self.old_songlist).encode(), 'songs/packlist': b'{"packs":[]}',
                'songs/unlocks': b'{}', 'img/prod.jpg': b'original jacket bytes', 'char/original': b'original partner',
                'layouts/original': b'original prod sidebar', 'audio/original': b'original prod audio'}
        manifest = {'versionNumber': '7.0.255.18', 'applicationVersionNumber': '7.0.255', 'previousVersionNumber': None,
                    'removed': [], 'totalPartitions': 7, 'added': [], 'pathToHash': {},
                    'pathToDetails': {'songs/songlist': 'old-auth', 'songs/packlist': 'pack-auth', 'songs/unlocks': 'unlock-auth'},
                    'uuid': 'old', 'generatedUnixTimestamp': 1}
        self.parts = []
        for i, (name, raw) in enumerate(data.items()):
            file = self.root / f'part{i}.cb'; file.write_bytes(raw)
            sha = blob_sha(raw); encoded = base64.b64encode(bytes.fromhex(sha)).decode()
            manifest['added'].append({'path': name, 'partIndex': i, 'byteOffset': 0, 'length': len(raw), 'sha256HashBase64Encoded': encoded})
            manifest['pathToHash'][name] = encoded
            self.parts.append({'partIndex': i, 'file': str(file), 'bytes': len(raw), 'sha256': sha})
        file = self.root / 'baseline.json'; file.write_text(json.dumps(manifest)); self.manifest = manifest
        union_file = self.root / 'union.json'; union_file.write_text(json.dumps(self.union))
        original = self.root / 'original.jpg'; original.write_bytes(b'Aurora full resolution original bytes')
        self.recipe = {'schema': composer.SCHEMA, 'version': '7.0.255.25', 'alias': 'quality-full-base25',
                       'baseline': {'manifest': {'file': str(file), 'sha256': composer.digest(file)}, 'parts': self.parts},
                       'overlays': [{'path': 'songs/songlist', 'file': str(union_file), 'bytes': union_file.stat().st_size,
                                     'sha256': composer.digest(union_file), 'detail_auth': 'new-auth'}],
                       'additions': [{'path': 'songs/aurora_new/1080_base.jpg', 'kind': 'aurora_original', 'file': str(original),
                                      'bytes': original.stat().st_size, 'sha256': composer.digest(original), 'original_sha256': composer.digest(original)}]}
        self.stack.enter_context(patch.object(composer, 'BASELINE_SHA', composer.digest(file)))
        self.stack.enter_context(patch.object(composer, 'UNION_SONGLIST_SHA', composer.digest(union_file)))
        self.stack.enter_context(patch.object(composer, 'UNION_SONGLIST_AUTH', 'new-auth'))
        self.stack.enter_context(patch.object(composer.release, 'physical_output', return_value={}))
        self.bind_review()

    def tearDown(self):
        self.stack.close(); self.temp.cleanup()

    def bind_review(self):
        file = self.root / 'review.json'
        file.write_text(json.dumps({'status': 'PASS_PROD_AURORA_BUNDLE_RECIPE_REVIEW', 'findings': [],
                                    'builder_sha256': composer.digest(Path(composer.__file__)),
                                    'payload_helper_sha256': composer.digest(Path(composer.bundle.__file__)),
                                    'output_guard_sha256': composer.digest(Path(composer.release.__file__)),
                                    'recipe_sha256': composer.recipe_digest(self.recipe)}))
        self.recipe['review'] = {'file': str(file), 'sha256': composer.digest(file)}

    def test_complete_base_preserves_every_old_path_except_reviewed_catalog(self):
        output = self.root / 'output'
        receipt = composer.build(self.recipe, output)
        actual = json.loads((output / 'quality-full-base25.json').read_bytes())
        self.assertIsNone(actual['previousVersionNumber']); self.assertEqual(actual['removed'], [])
        self.assertRegex(actual['uuid'], r'^[0-9a-f]{8}$')
        self.assertEqual(set(actual['pathToHash']), set(self.manifest['pathToHash']) | {'songs/aurora_new/1080_base.jpg'})
        for name, sha in self.manifest['pathToHash'].items():
            if name != 'songs/songlist': self.assertEqual(actual['pathToHash'][name], sha)
        self.assertEqual(actual['pathToDetails']['songs/packlist'], 'pack-auth')
        self.assertTrue(receipt['activation_blocked']); self.assertEqual(receipt['APK_omissions'], 0)

    def test_missing_or_changed_baseline_part_rejected(self):
        file = Path(self.parts[0]['file']); original = file.read_bytes()
        file.write_bytes(original[:-1] + bytes([original[-1] ^ 1]))
        with self.assertRaisesRegex(ValueError, 'size or SHA256'): composer.prepare(self.recipe)
        file.unlink()
        with self.assertRaises(FileNotFoundError): composer.prepare(self.recipe)

    def test_baseline_span_hash_offset_or_omission_is_rejected(self):
        for case in ('hash', 'offset', 'omission'):
            manifest = deepcopy(self.manifest)
            if case == 'hash': manifest['added'][0]['sha256HashBase64Encoded'] = base64.b64encode(bytes(32)).decode()
            if case == 'offset': manifest['added'][0]['byteOffset'] = 1
            if case == 'omission': manifest['added'].pop()
            file = Path(self.recipe['baseline']['manifest']['file']); file.write_text(json.dumps(manifest))
            self.recipe['baseline']['manifest']['sha256'] = composer.digest(file); self.bind_review()
            with patch.object(composer, 'BASELINE_SHA', composer.digest(file)), self.assertRaises(ValueError):
                composer.prepare(self.recipe)

    def test_collision_unsafe_addition_conversion_or_old_data_overlay_rejected(self):
        pristine = deepcopy(self.recipe)
        for case in ('collision', 'casecollision', 'unsafe', 'converted', 'oldoverlay'):
            self.recipe = deepcopy(pristine)
            if case == 'collision': self.recipe['additions'][0]['path'] = 'img/prod.jpg'
            if case == 'casecollision': self.recipe['additions'][0]['path'] = 'IMG/PROD.JPG'
            if case == 'unsafe': self.recipe['additions'][0]['path'] = '../escape'
            if case == 'converted': self.recipe['additions'][0]['original_sha256'] = '0' * 64
            if case == 'oldoverlay': self.recipe['overlays'][0]['path'] = 'img/prod.jpg'
            self.bind_review()
            with self.subTest(case=case), self.assertRaises(ValueError): composer.prepare(self.recipe)

    def test_partition_boundaries_are_contiguous_and_never_omit_rows(self):
        specs = [{'path': str(i), 'bytes': n, 'sha256': '1' * 64} for i, n in enumerate((4, 6, 1))]
        with patch.object(composer, 'MAX_PART', 10):
            rows, count = composer.partition(specs)
            self.assertEqual((count, [(r['partIndex'], r['byteOffset'], r['length']) for r in rows]),
                             (2, [(0, 0, 4), (0, 4, 6), (1, 0, 1)]))
            for size in (-1, True, 11):
                with self.assertRaises(ValueError): composer.partition([{'path': 'a', 'bytes': size, 'sha256': '1' * 64}])

    def test_review_or_original_file_hash_change_rejected(self):
        self.recipe['alias'] = 'changed-after-review'
        with self.assertRaisesRegex(ValueError, 'review required'): composer.prepare(self.recipe)
        self.bind_review(); file = Path(self.recipe['additions'][0]['file']); file.write_bytes(b'altered')
        with self.assertRaisesRegex(ValueError, 'size or SHA256'): composer.prepare(self.recipe)


if __name__ == '__main__':
    unittest.main()
