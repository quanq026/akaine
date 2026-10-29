import hashlib
import json
import tempfile
import unittest
import zipfile
from pathlib import Path

import build_android_client
from unittest.mock import patch


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class AndroidClientBuilderTests(unittest.TestCase):
    def test_published_native_plan_is_well_formed(self):
        plan_path = (
            Path(__file__).resolve().parents[1]
            / "patches"
            / "arcaea-7.0.255-arm64"
            / "native-plan.json"
        )
        plan = build_android_client.load_plan(plan_path)
        self.assertEqual(len(plan["binary_patches"]), 2)
        self.assertEqual(
            sum(len(row["operations"]) for row in plan["binary_patches"]),
            61,
        )
        labels = {
            operation["label"]
            for row in plan["binary_patches"]
            for operation in row["operations"]
        }
        self.assertTrue(any("production-shared-api-base" in label for label in labels))

    def test_guide_uses_current_v36_source_build(self):
        root = Path(__file__).resolve().parents[1]
        guide = (root / "docs/guide/06-build-android-client.md").read_text(
            encoding="utf-8"
        )
        self.assertIn("scripts\\build_android_client.py", guide)
        self.assertIn(build_android_client.XAPK[1], guide)
        self.assertIn("--songlist", guide)
        self.assertNotIn("production-checkpoint.md", guide)
        self.assertNotIn("--base-apk", guide)

    def test_beginner_guide_uses_verified_tools_and_stop_gates(self):
        root = Path(__file__).resolve().parents[1]
        guide = (root / "docs/guide/06-build-android-client.md").read_text(
            encoding="utf-8"
        )
        for required in (
            '$python = Join-Path $repoRoot ".venv\\Scripts\\python.exe"',
            '& $python scripts\\build_android_client.py --help',
            'Wrong APKPure package. Stop here;',
            'BUILD_RECEIPT.json',
            '--keystore',
            'APK signature verification failed',
            '$serial = Read-Host "Exact device serial shown above"',
        ):
            self.assertIn(required, guide)

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
                apk.writestr("stamp-cert-sha256", b"old-source-stamp")
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
                self.assertNotIn("stamp-cert-sha256", apk.namelist())
                self.assertIn("AndroidManifest.xml", apk.namelist())
            self.assertEqual(receipt["status"], "unsigned-built")
            self.assertEqual(receipt["expected"]["package"], "example.package")
            self.assertIn("stamp-cert-sha256", receipt["removed_signature_metadata"])

    def test_source_guard_rejects_a_change_after_compilation(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / 'helper.py'
            source.write_text('original')
            hashes = {'helper.py': digest(source)}
            with patch.object(build_android_client, 'ROOT', root):
                build_android_client.verify_sources(hashes)
                source.write_text('changed after native phase')
                with self.assertRaisesRegex(ValueError, 'Source changed'):
                    build_android_client.verify_sources(hashes)

    def test_signing_uses_java_argv_and_stdin_for_paths_aliases_and_passwords(self):
        import shutil
        from types import SimpleNamespace
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / 'operator&build'
            root.mkdir()
            (root / 'lib').mkdir()
            for name in ('zipalign.exe', 'java.exe', 'operator.p12', 'lib/apksigner.jar'):
                (root / name).write_bytes(b'test-only')
            with zipfile.ZipFile(root / 'unsigned.apk', 'w') as archive:
                archive.writestr('assets/original.png', b'original')
            def run(arguments):
                if '-f' in arguments:
                    shutil.copy2(root / 'unsigned.apk', root / 'aligned.apk')
                return b''
            def sign(arguments, **kwargs):
                self.assertEqual(arguments[:3], [str(root / 'java.exe'), '-Dfile.encoding=UTF-8', '-jar'])
                self.assertIn('owner&release', arguments)
                self.assertNotIn('test-only-store', arguments)
                self.assertEqual(kwargs['input'], 'test-only-store-việt\ntest-only-key\n'.encode())
                shutil.copy2(root / 'aligned.apk', root / 'Akaine-V36.apk')
                return SimpleNamespace(returncode=0)
            with patch.object(build_android_client, 'run_tool', side_effect=run), \
                 patch.object(build_android_client.subprocess, 'run', side_effect=sign), \
                 patch.object(build_android_client.getpass, 'getpass', side_effect=['test-only-store-việt', 'test-only-key']):
                result = build_android_client.sign_apk(root, root, root / 'operator.p12', 'owner&release', root / 'java.exe')
            self.assertEqual(result.name, 'Akaine-V36.apk')

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

    def test_accepts_guarded_source_entries_when_archive_hash_varies(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.apk"
            payload = root / "payload.bin"
            plan = root / "plan.json"
            output = root / "unsigned.apk"
            payload.write_bytes(b"new")
            with zipfile.ZipFile(source, "w") as apk:
                apk.writestr("AndroidManifest.xml", b"manifest")
                apk.writestr("classes.dex", b"old")
            manifest_hash = hashlib.sha256(b"manifest").hexdigest()
            plan.write_text(json.dumps({
                "schema": build_android_client.SCHEMA,
                "source_entries": {"AndroidManifest.xml": manifest_hash},
                "replacements": [{
                    "archive_path": "classes.dex",
                    "file": "payload.bin",
                    "sha256": digest(payload),
                }],
            }), encoding="utf-8")

            receipt = build_android_client.build(source, plan, root, output)

            self.assertEqual(receipt["status"], "unsigned-built")

    def test_applies_guarded_binary_patch(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.apk"
            plan = root / "plan.json"
            output = root / "unsigned.apk"
            native = b"before-01234567"
            patched = b"before-ABCD4567"
            with zipfile.ZipFile(source, "w") as apk:
                apk.writestr("lib/arm64-v8a/test.so", native)
            plan.write_text(json.dumps({
                "schema": build_android_client.SCHEMA,
                "source_sha256": digest(source),
                "binary_patches": [{
                    "archive_path": "lib/arm64-v8a/test.so",
                    "source_sha256": hashlib.sha256(native).hexdigest(),
                    "output_sha256": hashlib.sha256(patched).hexdigest(),
                    "operations": [{
                        "label": "test-operation",
                        "offset": 7,
                        "before": b"0123".hex(),
                        "after": b"ABCD".hex(),
                    }],
                }],
            }), encoding="utf-8")

            receipt = build_android_client.build(source, plan, root, output)

            with zipfile.ZipFile(output) as apk:
                self.assertEqual(apk.read("lib/arm64-v8a/test.so"), patched)
            self.assertEqual(
                receipt["binary_patch_labels"]["lib/arm64-v8a/test.so"],
                ["test-operation"],
            )


if __name__ == "__main__":
    unittest.main()
