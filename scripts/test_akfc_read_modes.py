"""Compile the actual loader hook against retained synthetic host stubs."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SOURCE = Path(os.environ.get('AKAINE_AKFC_SOURCE', ROOT / 'patches/arcaea-7.0.255-arm64/native/akfc_loader.cpp'))


class AkfcReadModes(unittest.TestCase):
    def test_actual_hook_read_modes_and_failures(self):
        compiler = shutil.which(os.environ.get('CXX', 'g++'))
        if not compiler:
            self.skipTest('Installed host C++ compiler required; no dependency is installed by this test')
        source = SOURCE.read_text(encoding='utf-8')
        start = source.index('static FILE* hooked_fopen(')
        hook = source[start:source.index('// Real open function pointer', start)]
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / 'actual_read_hook.inc').write_text(hook, encoding='utf-8')
            binary = root / 'test-read-modes'
            result = subprocess.run([compiler, '-std=c++17', '-Wall', '-Wextra', '-Werror', '-Wno-unused-function',
                '-I' + str(root), str(Path(__file__).with_suffix('.cpp')), '-o', str(binary)],
                capture_output=True, text=True, timeout=60)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            result = subprocess.run([str(binary)], capture_output=True, text=True, timeout=15)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn('PASS', result.stdout)


if __name__ == '__main__':
    unittest.main()
