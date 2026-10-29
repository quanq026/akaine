import base64
import hashlib
import json
import subprocess
import unittest

import catalogue as cat


def fixtures():
    songs = {'songs': [
        {'id': 'alpha', 'title_localized': {'en': 'Alpha', 'ja': '霹靂神'}, 'artist': 'Example', 'set': 'base', 'side': 0,
         'difficulties': [{'ratingClass': 2, 'rating': 9, 'ratingPlus': True}, {'ratingClass': 4, 'rating': 10}]},
        {'id': 'beta', 'title_localized': {'en': 'Beta'}, 'artist': 'Other', 'set': 'fan', 'side': 1,
         'difficulties': [{'ratingClass': 3, 'rating': 11}]}]}
    packs = {'packs': [{'id': 'base', 'name_localized': {'en': 'Base'}, 'section': 'arcaea'},
                       {'id': 'fan', 'name_localized': {'en': 'Fan Charts'}, 'section': 'variety'}]}
    files = {'songs': json.dumps(songs, ensure_ascii=False).encode(), 'packs': json.dumps(packs).encode()}
    meta = {'applicationVersionNumber': '7.0.255', 'versionNumber': '7.0.255.13', 'pathToHash': {
        'songs/songlist': base64.b64encode(hashlib.sha256(files['songs']).digest()).decode(),
        'songs/packlist': base64.b64encode(hashlib.sha256(files['packs']).digest()).decode()}}
    files['meta'] = json.dumps(meta).encode()
    return files


class Deadline:
    def remaining(self):
        return 10


class FakeAdb:
    def __init__(self):
        self.files = fixtures()
        self.calls = []
        self.meta_reads = 0
        self.change_meta = False

    def shell(self, script, deadline):
        self.calls.append(('guard', script))
        assert 'test ! -L ' in script and 'test -f ' in script
        return subprocess.CompletedProcess([], 0, b'', b'')

    def call(self, args, timeout):
        self.calls.append(('raw', args))
        assert args[:5] == ['exec-out', 'run-as', 'akai.arc.lmao', 'head', '-c']
        key = next(key for key, (path, _) in cat.FILES.items() if path == args[-1])
        data = self.files[key]
        if key == 'meta':
            self.meta_reads += 1
            if self.change_meta and self.meta_reads > 1:
                data += b'\n'
        return subprocess.CompletedProcess([], 0, data[:int(args[-2])], b'')


class CatalogueTests(unittest.TestCase):
    def setUp(self):
        self.device = FakeAdb()
        self.catalogue = cat.load(self.device, Deadline())

    def test_raw_bytes_hashes_verified_and_provenance_returned(self):
        result = cat.query(self.catalogue, 'songs', {})
        self.assertEqual(result['total'], 2)
        self.assertFalse(result['selection_changed'])
        self.assertFalse(result['ownership_verified'])
        self.assertEqual(result['catalogue_version'], '7.0.255.13')
        self.assertEqual(result['verified_hashes']['songs/songlist'], hashlib.sha256(self.device.files['songs']).hexdigest())

    def test_casefold_unicode_and_artist_queries(self):
        for query in ('ＡＬＰＨＡ', '霹靂', 'example'):
            self.assertEqual(cat.query(self.catalogue, 'songs', {'query': query})['results'][0]['id'], 'alpha')

    def test_combined_filters_apply_to_the_same_chart(self):
        self.assertEqual(cat.query(self.catalogue, 'songs', {'difficulty': 'ftr', 'level': '9+', 'pack': 'base', 'side': 0})['total'], 1)
        self.assertEqual(cat.query(self.catalogue, 'songs', {'difficulty': 'ftr', 'level': '10'})['total'], 0)

    def test_exact_info_and_pack_counts(self):
        self.assertEqual(cat.query(self.catalogue, 'songs', {'id': 'beta'})['results'][0]['difficulties'][0]['difficulty'], 'byd')
        packs = cat.query(self.catalogue, 'packs', {'query': 'fan'})
        self.assertEqual(packs['results'][0]['song_count'], 1)

    def test_native_negative_rating_sentinels_are_preserved_without_clamping(self):
        song = {'difficulties': [{'ratingClass': number, 'rating': rating}
                                for number, rating in enumerate((-1, -2, -3))]}
        self.assertEqual([row['level'] for row in cat.charts(song)], ['-1', '-2', '-3'])
        song['difficulties'][2]['ratingPlus'] = True
        self.assertEqual(cat.charts(song)[2]['level'], '-3+')

    def test_b9f4fe0a_source_levels_do_not_break_exact_or_broad_queries(self):
        song = {'id': 'aurora_b9f4fe0a', 'set': 'fan', 'difficulties': [
            {'ratingClass': 0, 'rating': -1, 'ratingPlus': False},
            {'ratingClass': 1, 'rating': -1, 'ratingPlus': False},
            {'ratingClass': 2, 'rating': 9, 'ratingPlus': False}]}
        self.catalogue['songs'].append(song)
        exact = cat.query(self.catalogue, 'songs', {'id': song['id']})
        self.assertEqual([row['level'] for row in exact['results'][0]['difficulties']], ['-1', '-1', '9'])
        self.assertEqual(cat.query(self.catalogue, 'songs', {})['total'], 3)
        self.assertEqual(cat.query(self.catalogue, 'songs', {'id': song['id'], 'difficulty': 'ftr', 'level': '9'})['total'], 1)

    def test_rating_outside_native_sentinels_or_display_range_rejected(self):
        for rating in (-4, 13, 100, -2147483648, 2147483647, True, False, None, '-1', 9.0):
            with self.subTest(rating=rating), self.assertRaisesRegex(ValueError, 'Invalid chart level'):
                cat.charts({'difficulties': [{'ratingClass': 2, 'rating': rating}]})

    def test_sort_and_pagination_are_stable(self):
        result = cat.query(self.catalogue, 'songs', {'limit': 1, 'offset': 1, 'sort': 'title'})
        self.assertEqual(result['total'], 2)
        self.assertEqual(result['results'][0]['id'], 'beta')

    def test_invalid_inputs_and_missing_ids_fail(self):
        for options in ({'limit': 0}, {'limit': 101}, {'offset': -1}, {'difficulty': 'xyz'}, {'level': '10++'},
                        {'side': 3}, {'pack': 'missing'}, {'query': '\n'}, {'sort': 'bad'}, {'id': '../bad'}, {'id': 'missing'}):
            with self.subTest(options=options), self.assertRaises(ValueError):
                cat.query(self.catalogue, 'songs', options)

    def test_appended_shell_newline_fails_content_digest(self):
        self.device.files['songs'] += b'\n'
        with self.assertRaisesRegex(ValueError, 'bytes do not match'):
            cat.load(self.device, Deadline())

    def test_changed_manifest_fails_query(self):
        self.device.meta_reads = 0
        self.device.change_meta = True
        with self.assertRaisesRegex(ValueError, 'changed during'):
            cat.load(self.device, Deadline())

    def test_invalid_document_shape_and_duplicate_ids_rejected(self):
        for value in ([], {'songs': [{'id': 'same'}, {'id': 'same'}]}):
            self.device.files['songs'] = json.dumps(value).encode()
            meta = json.loads(self.device.files['meta'])
            meta['pathToHash']['songs/songlist'] = base64.b64encode(hashlib.sha256(self.device.files['songs']).digest()).decode()
            self.device.files['meta'] = json.dumps(meta).encode()
            with self.assertRaises(ValueError):
                cat.load(self.device, Deadline())


if __name__ == '__main__':
    unittest.main()
