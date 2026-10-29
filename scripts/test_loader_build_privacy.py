"""Mock compiler diagnostics only; never opens a real key header or compiles."""
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import build_akfc_loader as builder


class BuildPrivacyTests(unittest.TestCase):
    def test_compiler_failure_never_discloses_diagnostics_or_command(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            paths = [root / name for name in ('compiler.cmd', 'source.cpp', 'crypto.a', 'embedded_key.h')]
            for path in paths: path.touch()
            compiler, source, crypto, header = paths
            result = subprocess.CompletedProcess([], 1, b'PRIVATE_INCLUDE_LINE', b'PRIVATE_INCLUDE_LINE')
            with patch.object(builder.subprocess, 'run', return_value=result) as run:
                with self.assertRaisesRegex(RuntimeError, '^Loader compiler failed; private diagnostics suppressed$') as error:
                    builder.build(source, header, crypto, root / 'output.so', compiler)
                self.assertNotIn('PRIVATE', str(error.exception))
                self.assertTrue(run.call_args.kwargs['capture_output'])
                self.assertEqual(run.call_args.kwargs['timeout'], 180)
                command = run.call_args.args[0]
                self.assertIn('-Wl,--no-undefined', command)
                self.assertIn('-Werror', command)

    def test_timeout_is_replaced_with_generic_error_without_command(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            paths = [root / name for name in ('compiler.cmd', 'source.cpp', 'crypto.a', 'embedded_key.h')]
            for path in paths: path.touch()
            compiler, source, crypto, header = paths
            with patch.object(builder.subprocess, 'run', side_effect=subprocess.TimeoutExpired('PRIVATE_COMMAND', 180)):
                with self.assertRaisesRegex(RuntimeError, 'private diagnostics suppressed') as error:
                    builder.build(source, header, crypto, root / 'output.so', compiler)
                self.assertNotIn('PRIVATE_COMMAND', str(error.exception))


if __name__ == '__main__': unittest.main()
