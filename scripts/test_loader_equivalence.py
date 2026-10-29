"""Synthetic build orchestration; no real header access, NDK compile or APK work."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import build_loader_equivalence as profile_driver


class EquivalenceTests(unittest.TestCase):
    def test_mismatched_output_records_failure_and_never_packages(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source, compiler, crypto, header = (root / name for name in ('source.cpp', 'compiler.cmd', 'crypto.a', 'embedded_key.h'))
            header = root / 'private' / 'embedded_key.h'
            header.parent.mkdir()
            for path in (source, compiler, crypto, header): path.touch()
            profile = {'expected_loader_sha256': '0' * 64, 'opaque_header_environment_slot': 'AKAINE_PRODUCTION_KEY_HEADER'}
            def compile_stub(source_arg, header_arg, crypto_arg, output, compiler_arg):
                self.assertEqual(header_arg, header)
                output.write_bytes(b'synthetic compiled loader')
            original_open = Path.open
            def guarded_open(path, *args, **kwargs):
                if path == header: raise AssertionError('Opaque header was read')
                return original_open(path, *args, **kwargs)
            symbols = 'Java_low_moe_AkfcLoader_installHooks Java_low_moe_AkfcLoader_wipeDecrypted'
            output = root / 'output'
            with patch.object(profile_driver, 'verify', return_value=(source, compiler, crypto)), \
                    patch.object(profile_driver.build_release_profile, 'physical_output', return_value={}), \
                    patch.object(profile_driver.build_akfc_loader, 'build', side_effect=compile_stub), \
                    patch.object(profile_driver, 'tool', side_effect=(symbols, 'static dependencies')), \
                    patch.dict(profile_driver.os.environ, {'AKAINE_PRODUCTION_KEY_HEADER': str(header)}), \
                    patch.object(Path, 'open', guarded_open):
                with self.assertRaisesRegex(ValueError, 'Loader bytes differ'):
                    profile_driver.build(profile, {}, output)
            receipt = json.loads((output / 'BUILD_RECEIPT.json').read_bytes())
            self.assertEqual(receipt['status'], 'SOURCE_EQUIVALENCE_BUILD_IDENTITY_MISMATCH_STOP_BEFORE_APK')
            self.assertFalse(receipt['opaque_header_read_copied_hashed_or_logged_by_driver'])
            self.assertNotIn(str(header), json.dumps(receipt))
            self.assertFalse(receipt['APK_packaged_or_installed'])

    def test_verify_checks_only_nonsecret_inputs_and_rejects_source_drift(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source, compiler, clang, crypto = (root / name for name in ('loader.cpp', 'compiler.cmd', 'clang++.exe', 'crypto.a'))
            for path in (source, compiler, clang, crypto): path.write_bytes(b'synthetic nonsecret fixture')
            expected = hashlib.sha256(source.read_bytes()).hexdigest()
            profile = {'schema': 'akaine.loader-equivalence.v1', 'environment': 'staging', 'source': source.name,
                       'source_sha256': expected, 'compiler_driver_sha256': expected,
                       'compiler_executable_sha256': expected, 'static_crypto_archive_sha256': expected,
                       'opaque_header_environment_slot': 'AKAINE_PRODUCTION_KEY_HEADER'}
            with patch.object(profile_driver, 'ROOT', root):
                self.assertEqual(profile_driver.verify(profile, {'compiler': str(compiler), 'crypto': str(crypto)}),
                                 (source, compiler, crypto))
                source.write_bytes(b'changed')
                with self.assertRaisesRegex(ValueError, 'source differs'):
                    profile_driver.verify(profile, {'compiler': str(compiler), 'crypto': str(crypto)})


if __name__ == '__main__': unittest.main()
