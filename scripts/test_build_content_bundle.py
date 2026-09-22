import base64
import hashlib
import hmac
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BUILDER = ROOT / "scripts" / "build_content_bundle.py"


def digest(data: bytes) -> str:
    return base64.b64encode(hashlib.sha256(data).digest()).decode("ascii")


class ContentBundleBuilderTests(unittest.TestCase):
    def make_source(self, root: Path, *, song_set: str = "base") -> tuple[Path, bytes]:
        source = root / "source"
        source.mkdir()
        key = b"test-detail-key"
        payloads = {
            "songs/packlist": json.dumps({"packs": [{"id": "base"}]}).encode(),
            "songs/songlist": json.dumps(
                {"songs": [{"id": "song", "idx": 1, "set": song_set}]}
            ).encode(),
            "misc/file.bin": b"unchanged",
        }
        rows = []
        path_hashes = {}
        details = {}
        parts = [bytearray(), bytearray()]
        for index, (path, data) in enumerate(payloads.items()):
            part_index = min(index, 1)
            offset = len(parts[part_index])
            parts[part_index].extend(data)
            encoded = digest(data)
            rows.append(
                {
                    "path": path,
                    "byteOffset": offset,
                    "length": len(data),
                    "partIndex": part_index,
                    "sha256HashBase64Encoded": encoded,
                }
            )
            path_hashes[path] = encoded
            if path.startswith("songs/"):
                details[path] = base64.b64encode(
                    hmac.new(key, data, hashlib.sha256).digest()
                ).decode("ascii")
        manifest = {
            "added": rows,
            "applicationVersionNumber": "7.0.255",
            "generatedUnixTimestamp": 1,
            "pathToDetails": details,
            "pathToHash": path_hashes,
            "previousVersionNumber": None,
            "removed": [],
            "totalPartitions": 2,
            "uuid": "source00",
            "versionNumber": "7.0.255.1",
        }
        (source / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
        for index, data in enumerate(parts):
            (source / f"source_{index}.cb").write_bytes(data)
        (root / "detail.key").write_bytes(key)
        return source, key

    def run_builder(self, root: Path, source: Path) -> subprocess.CompletedProcess[str]:
        overlay = root / "overlay"
        (overlay / "songs").mkdir(parents=True)
        (overlay / "songs" / "songlist").write_text(
            json.dumps({"songs": [{"id": "song", "idx": 1, "set": "base"}]}),
            encoding="utf-8",
        )
        (overlay / "new.bin").write_bytes(b"new")
        return subprocess.run(
            [
                sys.executable,
                str(BUILDER),
                "--source",
                str(source),
                "--overlay",
                str(overlay),
                "--output",
                str(root / "output"),
                "--alias",
                "guide-test",
                "--version",
                "7.0.255.2",
                "--detail-key-file",
                str(root / "detail.key"),
                "--max-part-bytes",
                "1024",
            ],
            text=True,
            capture_output=True,
        )

    def test_builds_verified_full_root_and_preserves_source_partition_count(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source, _ = self.make_source(root)
            result = self.run_builder(root, source)

            self.assertEqual(result.returncode, 0, result.stderr)
            output = root / "output"
            manifest = json.loads((output / "guide-test.json").read_text())
            ready = json.loads((output / "ready-manifest.json").read_text())
            self.assertEqual(manifest["applicationVersionNumber"], "7.0.255")
            self.assertEqual(manifest["versionNumber"], "7.0.255.2")
            self.assertIsNone(manifest["previousVersionNumber"])
            self.assertEqual(manifest["totalPartitions"], 2)
            self.assertEqual({row["path"] for row in manifest["added"]}, {
                "songs/packlist", "songs/songlist", "misc/file.bin", "new.bin"
            })
            self.assertEqual(ready["status"], "ready")
            self.assertTrue(ready["artifact_verified"])

    def test_rejects_a_song_that_references_a_missing_pack(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source, _ = self.make_source(root)
            overlay = root / "overlay"
            (overlay / "songs").mkdir(parents=True)
            (overlay / "songs" / "songlist").write_text(
                json.dumps({"songs": [{"id": "song", "idx": 1, "set": "deleted-pack"}]}),
                encoding="utf-8",
            )
            result = subprocess.run(
                [
                    sys.executable,
                    str(BUILDER),
                    "--source",
                    str(source),
                    "--overlay",
                    str(overlay),
                    "--output",
                    str(root / "output"),
                    "--alias",
                    "guide-test",
                    "--version",
                    "7.0.255.2",
                    "--detail-key-file",
                    str(root / "detail.key"),
                ],
                text=True,
                capture_output=True,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("song-pack-missing:song:deleted-pack", result.stdout)
            self.assertFalse((root / "output").exists())


if __name__ == "__main__":
    unittest.main(verbosity=2)
