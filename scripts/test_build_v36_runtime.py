import hashlib
import json
from pathlib import Path
import tempfile
import unittest

import build_v36_runtime as runtime


class RuntimeSourceTests(unittest.TestCase):
    def test_header_layout_uses_derived_bytes_and_fails_on_a_changed_pin(self):
        raw = b'ELF-fixture'
        header = {'path': 'semantic/example.h', 'template': [
            'inline constexpr unsigned char EXAMPLE[] = {@@EXAMPLE@@};'],
            'pins': [{'symbol': 'EXAMPLE', 'file_offset': 0, 'bytes': 3,
                      'sha256': hashlib.sha256(raw[:3]).hexdigest()}]}
        self.assertEqual(runtime.render_header(header, raw),
                         'inline constexpr unsigned char EXAMPLE[] = {0x45,0x4c,0x46};\n')
        with self.assertRaisesRegex(ValueError, 'byte guard'):
            runtime.render_header(header, b'bad-fixture')
        for path in ('../example.h', '/semantic/example.h', 'semantic/../example.h', 'semantic\\example.h'):
            with self.assertRaises(ValueError):
                runtime.safe_relative(path)

    def test_catalogue_is_explicit_sorted_and_cpp_escaped(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / 'songlist'
            path.write_text(json.dumps({'songs': [{'id': 'z', 'set': 'mod'},
                {'id': 'a"b', 'set': 'base'}]}), encoding='utf-8')
            header, count = runtime.catalogue_header(path)
            self.assertEqual(count, 2)
            self.assertIn('{"a\\"b","base"}', header)
            self.assertLess(header.index('a\\"b'), header.index('{"z"'))
            for rows in ([], [{'id': 'x', 'set': 'base'}, {'id': 'x', 'set': 'mod'}],
                         [{'id': 'x'}], [{'id': 'bad\0id', 'set': 'base'}]):
                path.write_text(json.dumps({'songs': rows}), encoding='utf-8')
                with self.assertRaises(ValueError):
                    runtime.catalogue_header(path)

    def test_runtime_layout_contains_no_frozen_instruction_byte_arrays(self):
        layout = runtime.load_layout()
        self.assertEqual(len(layout['headers']), 26)
        self.assertEqual(sum(len(header['pins']) for header in layout['headers']), 475)
        for header in layout['headers']:
            self.assertNotRegex('\n'.join(header['template']), r'unsigned char\s+\w+\[\]\s*=\s*\{\s*0x')


if __name__ == '__main__':
    unittest.main()
