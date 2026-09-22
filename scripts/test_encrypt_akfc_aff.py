import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "encrypt_akfc_aff.py"
sys.path.insert(0, str(ROOT / "server"))

from core.akfc import AffIdentity, decrypt_container, parse_container, unwrap_dek  # noqa: E402


class EncryptAkfcAffTests(unittest.TestCase):
    def test_cli_encrypts_for_the_runtime_identity_and_writes_a_receipt(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            private_key = rsa.generate_private_key(public_exponent=65537, key_size=3072)
            public_key = root / "public.pem"
            source = root / "2.aff"
            output = root / "encrypted" / "2.aff"
            receipt = root / "receipt.json"
            plaintext = b"AudioOffset:0\n-\ntiming(0,120.00,4.00);\n"
            source.write_bytes(plaintext)
            public_key.write_bytes(private_key.public_key().public_bytes(
                serialization.Encoding.PEM,
                serialization.PublicFormat.SubjectPublicKeyInfo,
            ))

            result = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "--source",
                    str(source),
                    "--public-key",
                    str(public_key),
                    "--song-id",
                    "example_song",
                    "--file-name",
                    "2.aff",
                    "--output",
                    str(output),
                    "--receipt",
                    str(receipt),
                ],
                text=True,
                capture_output=True,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            container = output.read_bytes()
            self.assertEqual(container[:4], b"AKFC")
            identity = AffIdentity("fan-sec-v1", "example_song", "2.aff", 1)
            parsed = parse_container(container, identity)
            plaintext_actual = decrypt_container(
                container,
                unwrap_dek(private_key, parsed.wrapped_key),
                identity,
            )
            self.assertEqual(plaintext_actual, plaintext)
            report = json.loads(receipt.read_text(encoding="utf-8"))
            self.assertEqual(report["status"], "verified")
            self.assertEqual(report["identity"]["song_id"], "example_song")
            self.assertEqual(report["identity"]["file_name"], "2.aff")

    def test_cli_refuses_to_overwrite_an_existing_output(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            private_key = rsa.generate_private_key(public_exponent=65537, key_size=3072)
            public_key = root / "public.pem"
            source = root / "2.aff"
            output = root / "2.akfc"
            source.write_text("AudioOffset:0\n-\n", encoding="utf-8")
            output.write_bytes(b"keep")
            public_key.write_bytes(private_key.public_key().public_bytes(
                serialization.Encoding.PEM,
                serialization.PublicFormat.SubjectPublicKeyInfo,
            ))

            result = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "--source",
                    str(source),
                    "--public-key",
                    str(public_key),
                    "--song-id",
                    "example_song",
                    "--file-name",
                    "2.aff",
                    "--output",
                    str(output),
                ],
                text=True,
                capture_output=True,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(output.read_bytes(), b"keep")


if __name__ == "__main__":
    unittest.main(verbosity=2)
