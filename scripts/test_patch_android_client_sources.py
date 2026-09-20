import tempfile
import unittest
from pathlib import Path

import patch_android_client_sources


class ManagedSourcePatchTests(unittest.TestCase):
    def test_patches_version_locked_managed_sources(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "res/values").mkdir(parents=True)
            (root / "smali/low/moe").mkdir(parents=True)
            (root / "smali/moe/low/arcdev").mkdir(parents=True)
            (root / "AndroidManifest.xml").write_text(
                '<manifest package="moe.low.arc">'
                + "".join(f'<provider android:name="moe.low.arc.{i}"/>' for i in range(7))
                + '<data android:host="cct.moe.low.arc" android:scheme="@string/fb_login_protocol_scheme"/>'
                + "</manifest>",
                encoding="utf-8",
            )
            (root / "res/values/strings.xml").write_text(
                '<string name="app_name">Arcaea</string>', encoding="utf-8"
            )
            (root / "smali/moe/low/arcdev/BuildConfig.smali").write_text(
                'APPLICATION_ID:Ljava/lang/String; = "moe.low.arc"', encoding="utf-8"
            )
            (root / "smali/low/moe/AppActivity.smali").write_text(
                'const-string v2, "moe.low.arc.provider"\n'
                '    invoke-virtual {v0, p0, v1}, Lcom/getkeepsafe/relinker/ReLinkerInstance;->loadLibrary(Landroid/content/Context;Ljava/lang/String;)V\n'
                '    :try_end_0\n'
                '.method protected onDestroy()V\n    .locals 0\n\n',
                encoding="utf-8",
            )
            patch_root = Path(__file__).resolve().parents[1] / "patches/arcaea-7.0.255-arm64"

            result = patch_android_client_sources.patch(root, patch_root)

            self.assertEqual(result["status"], "patched")
            self.assertIn("akai.arc.lmao", (root / "AndroidManifest.xml").read_text())
            self.assertIn("AkaineXD", (root / "res/values/strings.xml").read_text())
            self.assertTrue((root / "smali/low/moe/AkfcLoader.smali").is_file())
            activity = (root / "smali/low/moe/AppActivity.smali").read_text()
            self.assertIn("AkfcLoader;->init", activity)
            self.assertIn("AkfcLoader;->wipeDecrypted", activity)


if __name__ == "__main__":
    unittest.main()
