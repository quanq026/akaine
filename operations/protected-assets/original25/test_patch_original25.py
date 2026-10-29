import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

from patch_original25 import patch

HERE = Path(__file__).resolve().parent


class Original25Tests(unittest.TestCase):
    def test_worker_signatures_and_storage_routes(self):
        source = (HERE.parent / 'accepted-20261023/worker.accepted.mjs').read_bytes()
        rows = json.loads((HERE / 'audio-replacements.json').read_bytes())
        with self.assertRaises(ValueError):
            patch(source + b'\n', rows)
        with self.assertRaises(ValueError):
            patch(source, rows[:-1])
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / 'worker.mjs'
            target.write_bytes(patch(source, rows))
            self.assertEqual(hashlib.sha256(target.read_bytes()).hexdigest(),
                             'f617e04a99dae6c4654d1794591840209638a502e85ba8b67356121199bf13e2')
            result = subprocess.run(['node', str(HERE / 'test_worker.mjs'), str(target)],
                                    capture_output=True, text=True, check=True)
            self.assertIn('PASS: 50 replacements', result.stdout)


if __name__ == '__main__':
    unittest.main()
