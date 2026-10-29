"""Compile the exact materialization/cache source against nonsecret file fixtures."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SOURCE = Path(os.environ.get('AKAINE_AKFC_SOURCE', ROOT / 'patches/arcaea-7.0.255-arm64/native/akfc_loader.cpp'))


class RetryCacheTests(unittest.TestCase):
    def test_actual_cache_retry_short_write_close_failure(self):
        compiler = shutil.which(os.environ.get('CXX', 'g++'))
        if not compiler:
            self.skipTest('Existing host C++ compiler required')
        text = SOURCE.read_text(encoding='utf-8')
        start = text.index('struct MemfdEntry {')
        section = text[start:text.index('// Wipe —', start)]
        prelude = ('#include <string>\n#include <vector>\n#include <map>\n#include <stdint.h>\n'
                   '#include <stdio.h>\n#include <stdlib.h>\n#include <unistd.h>\n#include <sys/stat.h>\n'
                   '#include <pthread.h>\n#define LOGI(...) ((void)0)\n#define LOGE(...) ((void)0)\n'
                   'static FILE* (*real_fopen)(const char*, const char*) = nullptr;\n')
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / 'actual_cache_function.inc').write_text(prelude + section, encoding='utf-8')
            binary = root / 'test-cache'
            result = subprocess.run([compiler, '-std=c++17', '-Wall', '-Wextra', '-Werror', '-Wno-unused-function',
                '-pthread', '-I' + str(root), str(Path(__file__).with_suffix('.cpp')), '-o', str(binary)],
                capture_output=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            result = subprocess.run([str(binary)], capture_output=True, timeout=10)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn(b'PASS 27 cache checks', result.stdout)


if __name__ == '__main__': unittest.main()
