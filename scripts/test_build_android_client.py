import hashlib
import json
import tempfile
import unittest
import zipfile
from pathlib import Path

import build_android_client


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class AndroidClientBuilderTests(unittest.TestCase):
    def test_replaces_payload_and_removes_old_v1_signature(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.apk"
            payload = root / "payload.bin"
            plan = root / "plan.json"
            output = root / "unsigned.apk"
            payload.write_bytes(b"patched-native")
            with zipfile.ZipFile(source, "w") as apk:
                apk.writestr("AndroidManifest.xml", b"manifest")
                apk.writestr("lib/arm64-v8a/libcocos2dcpp.so", b"old-native")
                apk.writestr("META-INF/OLD.SF", b"old-signature")
            plan.write_text(json.dumps({
                "schema": build_android_client.SCHEMA,
                "source_sha256": digest(source),
                "required_entries": ["AndroidManifest.xml"],
                "replacements": [{
                    "archive_path": "lib/arm64-v8a/libcocos2dcpp.so",
                    "file": "payload.bin",
                    "sha256": digest(payload),
                }],
                "expected": {"package": "example.package"},
            }), encoding="utf-8")

            receipt = build_android_client.build(source, plan, root, output)

            with zipfile.ZipFile(output) as apk:
                self.assertEqual(apk.read("lib/arm64-v8a/libcocos2dcpp.so"), b"patched-native")
                self.assertNotIn("META-INF/OLD.SF", apk.namelist())
                self.assertIn("AndroidManifest.xml", apk.namelist())
            self.assertEqual(receipt["status"], "unsigned-built")
            self.assertEqual(receipt["expected"]["package"], "example.package")

    def test_rejects_wrong_source_hash(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.apk"
            payload = root / "payload.bin"
            plan = root / "plan.json"
            source.write_bytes(b"not-an-apk")
            payload.write_bytes(b"replacement")
            plan.write_text(json.dumps({
                "schema": build_android_client.SCHEMA,
                "source_sha256": "0" * 64,
                "replacements": [{
                    "archive_path": "classes.dex",
                    "file": "payload.bin",
                    "sha256": digest(payload),
                }],
            }), encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "source APK hash mismatch"):
                build_android_client.build(source, plan, root, root / "out.apk")


if __name__ == "__main__":
    unittest.main()
