"""Small regression checks for the portable V36 assembly boundary."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

import build_client_support
import build_v36_client


class V36BuildTests(unittest.TestCase):
    def test_fresh_output_is_portable_and_never_reuses_an_existing_directory(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "build"
            self.assertTrue(build_client_support.fresh_output(path)["fresh"])
            path.mkdir()
            with self.assertRaises(ValueError):
                build_client_support.fresh_output(path)

    def test_assembly_preserves_assets_and_every_undeclared_apk_member(self):
        with tempfile.TemporaryDirectory() as temporary:
            base, output = [Path(temporary) / name for name in ("base.apk", "output.apk")]
            with zipfile.ZipFile(base, "w") as archive:
                archive.writestr("assets/original.jpg", b"original-quality")
                archive.writestr("AndroidManifest.xml", b"manifest")
                archive.writestr("classes3.dex", b"old")
                archive.writestr("META-INF/CERT.RSA", b"old-signature")
            def write(asset):
                with zipfile.ZipFile(output, "w") as archive:
                    archive.writestr("assets/original.jpg", asset)
                    archive.writestr("AndroidManifest.xml", b"manifest")
                    archive.writestr("classes3.dex", b"new")
            write(b"original-quality")
            build_v36_client.verify_unchanged_members(base, output, {"classes3.dex"})
            write(b"reduced-quality")
            with self.assertRaisesRegex(ValueError, "Undeclared"):
                build_v36_client.verify_unchanged_members(base, output, {"classes3.dex"})

    def test_hydration_rejects_traversal_and_duplicate_roles(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            runtime, kit = root / "runtime", root / "kit"
            runtime.mkdir()
            (root / "source.h").write_text("fixture")
            row = {"role": "../escape", "source": "source.h"}
            with patch.object(build_v36_client, "ROOT", root), patch.object(build_v36_client, "RUNTIME", runtime):
                (runtime / "sources.json").write_text(json.dumps({"schema": "akaine.v36.sources.v1", "sources": [row]}))
                with self.assertRaises(ValueError):
                    build_v36_client.hydrate_sources(kit)
                row["role"] = "safe/source.h"
                (runtime / "sources.json").write_text(json.dumps({"schema": "akaine.v36.sources.v1", "sources": [row, row]}))
                with self.assertRaises(ValueError):
                    build_v36_client.hydrate_sources(kit)


if __name__ == "__main__":
    unittest.main()
