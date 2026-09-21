import os
import sys
import tempfile
import unittest
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "server"))
from core.akfc import (  # noqa: E402
    AffIdentity,
    assemble_container,
    decrypt_container,
    encrypt_aff,
    unwrap_dek,
    wrap_dek,
)
import generate_akfc_key_header  # noqa: E402
import build_akfc_loader  # noqa: E402
import build_boringssl_android  # noqa: E402


class AKFCSourceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.private_key = rsa.generate_private_key(public_exponent=65537, key_size=3072)

    def test_container_round_trip(self):
        identity = AffIdentity("fan-sec-v1", "example", "2.aff", 1)
        plaintext = b"AudioOffset:0\n-\ntiming(0,120.00,4.00);\n"
        dek = os.urandom(32)
        encrypted = encrypt_aff(plaintext, dek, identity, nonce=os.urandom(12))
        wrapped = wrap_dek(self.private_key.public_key(), dek)
        container = assemble_container(encrypted, wrapped)
        actual = decrypt_container(
            container,
            unwrap_dek(self.private_key, wrapped),
            identity,
        )
        self.assertEqual(actual, plaintext)

    def test_key_header_contains_no_pem_text(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            private_key_path = root / "private.pem"
            header = root / "embedded_key.h"
            private_key_path.write_bytes(self.private_key.private_bytes(
                serialization.Encoding.PEM,
                serialization.PrivateFormat.PKCS8,
                serialization.NoEncryption(),
            ))
            generate_akfc_key_header.generate(private_key_path, header)
            source = header.read_text(encoding="utf-8")
            self.assertIn("EMBEDDED_KEY_DATA", source)
            self.assertNotIn("PRIVATE KEY", source)

    def test_loader_source_has_release_hardening(self):
        source = (
            ROOT
            / "patches/arcaea-7.0.255-arm64/native/akfc_loader.cpp"
        ).read_text(encoding="utf-8")
        self.assertNotIn("Java_low_moe_AkfcLoader_decryptFile", source)
        self.assertIn("Java_low_moe_AkfcLoader_installHooks", source)
        self.assertIn("Java_low_moe_AkfcLoader_wipeDecrypted", source)
        self.assertIn("#define LOGI(...) ((void)0)", source)

    def test_loader_uses_prefixed_static_crypto(self):
        guide = (ROOT / "docs/guide/06-build-android-client.md").read_text(
            encoding="utf-8"
        )
        self.assertIn("--crypto", guide)
        self.assertIn("build_boringssl_android.py", guide)
        self.assertNotIn("Copy-Item $crypto", guide)
        self.assertEqual(len(build_boringssl_android.REVISION), 40)
        source = (
            ROOT / "patches/arcaea-7.0.255-arm64/native/akfc_loader.cpp"
        ).read_text(encoding="utf-8")
        self.assertIn("p_EVP_AEAD_CTX_open = akfc_EVP_AEAD_CTX_open", source)
        self.assertNotIn('dlopen("libcrypto.so"', source)


if __name__ == "__main__":
    unittest.main()
