"""Small synthetic receipt/ZIP/signature tests; never opens the real APK or keys."""
import copy
import hashlib
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch
import zipfile

import verify_final_release as verifier


class FinalVerifierTests(unittest.TestCase):
    def fixtures(self):
        payloads = {'fixture-' + str(i): hashlib.sha256(bytes([i])).hexdigest() for i in range(5)}
        lock = {'expected_replacements': [{'role': 'final/payload/' + name, 'sha256': value} for name, value in payloads.items()],
                'signing': {'signer_certificate_sha256': 'a' * 64}, 'assetset_sha256': 'b' * 64}
        build = {'status': 'FIVE_SOURCE_PAYLOADS_AND_UNSIGNED_APK_MATCH', 'source_lock_sha256': 'c' * 64,
                 'checkout_map_sha256': 'd' * 64, 'payload_sha256': payloads, 'unsigned_apk_sha256': 'e' * 64}
        artifact = {'environment': 'staging', 'package': 'akai.arc.lmao', 'payloads': payloads, 'signer_sha256': 'a' * 64,
                    'assembly': {'output_sha256': 'e' * 64}, 'post_sign_assetset_verified': {'assetset_sha256': 'b' * 64}}
        return lock, build, artifact

    def test_source_build_artifact_receipt_binding(self):
        lock, build, artifact = self.fixtures()
        self.assertEqual(verifier.validate_receipts(lock, build, artifact, 'c' * 64, 'd' * 64), (build['payload_sha256'], 'a' * 64))
        for target, key, value in ((build, 'source_lock_sha256', '0' * 64), (build, 'payload_sha256', {}),
                                   (artifact, 'environment', 'production'), (artifact, 'signer_sha256', '0' * 64)):
            original = target[key]; target[key] = value
            with self.assertRaises(ValueError): verifier.validate_receipts(lock, build, artifact, 'c' * 64, 'd' * 64)
            target[key] = original

    def test_actual_zip_payload_and_numeric_signature_gate(self):
        lock, build, artifact = self.fixtures()
        with tempfile.TemporaryDirectory() as folder:
            apk = Path(folder) / 'fixture.apk'
            with zipfile.ZipFile(apk, 'w') as archive:
                for i in range(5): archive.writestr('fixture-' + str(i), bytes([i]))
            artifact.update(apk_sha256=hashlib.sha256(apk.read_bytes()).hexdigest(), bytes=apk.stat().st_size)
            text = b'Verified using v2 scheme (APK Signature Scheme v2): true\nSigner #1 certificate SHA-256 digest: ' + b'a' * 64 + b'\n'
            assets = {'assetset_sha256': 'b' * 64, 'asset_count': 1}
            with patch.object(verifier.subprocess, 'run', return_value=subprocess.CompletedProcess([], 0, text, b'')), \
                    patch.object(verifier.assetset_identity, 'verify_apk', return_value=assets):
                result = verifier.signed_artifact(apk, artifact, build['payload_sha256'], 'a' * 64, 'java', 'signer.jar', 'manifest')
                self.assertEqual(result['payloads_verified'], 5)
                with self.assertRaises(ValueError):
                    verifier.signed_artifact(apk, artifact, build['payload_sha256'], 'f' * 64, 'java', 'signer.jar', 'manifest')
                bad = dict(build['payload_sha256']); bad['fixture-0'] = '0' * 64
                with self.assertRaisesRegex(ValueError, 'source payload'):
                    verifier.signed_artifact(apk, artifact, bad, 'a' * 64, 'java', 'signer.jar', 'manifest')
                assets['assetset_sha256'] = '0' * 64
                with self.assertRaisesRegex(ValueError, 'asset capability'):
                    verifier.signed_artifact(apk, artifact, build['payload_sha256'], 'a' * 64, 'java', 'signer.jar', 'manifest')

    def test_missing_both_or_malformed_unsigned_identity_fails_closed(self):
        lock, build, artifact = self.fixtures()
        build.pop('unsigned_apk_sha256')
        artifact['assembly'].pop('output_sha256')
        with self.assertRaisesRegex(ValueError, 'Build receipt'):
            verifier.validate_receipts(lock, build, artifact, 'c' * 64, 'd' * 64)
        for invalid in ('', 'E' * 64, 'e' * 63, 'not-a-hash', 0, None):
            build['unsigned_apk_sha256'] = invalid
            artifact['assembly']['output_sha256'] = invalid
            with self.subTest(value=invalid):
                with self.assertRaisesRegex(ValueError, 'Build receipt'):
                    verifier.validate_receipts(lock, build, artifact, 'c' * 64, 'd' * 64)

    def test_loader_compile_uses_original_pinned_ndk_driver_mapping(self):
        import ast
        tree = ast.parse(Path(verifier.final.__file__).read_bytes())
        function = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == 'build')
        call = next(node for node in ast.walk(function) if isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Attribute) and node.func.attr == 'build'
                    and isinstance(node.func.value, ast.Name) and node.func.value.id == 'build_loader_equivalence')
        self.assertEqual(ast.dump(call.args[1]), "Call(func=Name(id='loader_paths', ctx=Load()), args=[Name(id='paths', ctx=Load())], keywords=[])")
        self.assertEqual(verifier.final.loader_paths({'loader/compiler': 'NDK/bin/compiler.cmd', 'loader/crypto': 'crypto.a'}),
                         {'compiler': 'NDK/bin/compiler.cmd', 'crypto': 'crypto.a'})


if __name__ == '__main__': unittest.main()
