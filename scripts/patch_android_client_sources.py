"""Patch the Apktool-decoded Arcaea 7.0.255 managed client sources."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path


def replace_exact(text: str, old: str, new: str, count: int, label: str) -> str:
    actual = text.count(old)
    if actual != count:
        raise ValueError(f"{label}: expected {count} matches, found {actual}")
    return text.replace(old, new)


def patch_file(path: Path, replacements: list[tuple[str, str, int, str]]) -> dict:
    original = path.read_text(encoding="utf-8")
    patched = original
    for old, new, count, label in replacements:
        patched = replace_exact(patched, old, new, count, label)
    path.write_text(patched, encoding="utf-8", newline="\n")
    return {
        "path": path.as_posix(),
        "before_sha256": hashlib.sha256(original.encode()).hexdigest(),
        "after_sha256": hashlib.sha256(patched.encode()).hexdigest(),
    }


def patch(decoded: Path, patch_root: Path) -> dict:
    decoded = decoded.resolve()
    patch_root = patch_root.resolve()
    manifest = decoded / "AndroidManifest.xml"
    strings = decoded / "res" / "values" / "strings.xml"
    app_activity = decoded / "smali" / "low" / "moe" / "AppActivity.smali"
    build_config = decoded / "smali" / "moe" / "low" / "arcdev" / "BuildConfig.smali"
    for path in (manifest, strings, app_activity, build_config):
        if not path.is_file():
            raise FileNotFoundError(path)

    changes = [
        patch_file(manifest, [
            ('package="moe.low.arc"', 'package="akai.arc.lmao"', 1, "manifest package"),
            ("moe.low.arc.", "akai.arc.lmao.", 7, "manifest package authorities"),
            ('android:host="cct.moe.low.arc"', 'android:host="cct.akai.arc.lmao"', 1, "Facebook callback host"),
            ('android:scheme="@string/fb_login_protocol_scheme"', 'android:scheme="fb664034082680649"', 1, "Facebook callback scheme"),
        ]),
        patch_file(strings, [
            ('<string name="app_name">Arcaea</string>', '<string name="app_name">AkaineXD</string>', 1, "application label"),
        ]),
        patch_file(build_config, [
            ('APPLICATION_ID:Ljava/lang/String; = "moe.low.arc"', 'APPLICATION_ID:Ljava/lang/String; = "akai.arc.lmao"', 1, "BuildConfig application ID"),
        ]),
        patch_file(app_activity, [
            ('const-string v2, "moe.low.arc.provider"', 'const-string v2, "akai.arc.lmao.provider"', 1, "share FileProvider authority"),
            (
                '    invoke-virtual {v0, p0, v1}, Lcom/getkeepsafe/relinker/ReLinkerInstance;->loadLibrary(Landroid/content/Context;Ljava/lang/String;)V\n    :try_end_0',
                '    invoke-virtual {v0, p0, v1}, Lcom/getkeepsafe/relinker/ReLinkerInstance;->loadLibrary(Landroid/content/Context;Ljava/lang/String;)V\n\n    invoke-static {}, Llow/moe/AkfcLoader;->init()V\n    :try_end_0',
                1,
                "AKFC initialization",
            ),
            (
                '.method protected onDestroy()V\n    .locals 0\n\n',
                '.method protected onDestroy()V\n    .locals 0\n\n    invoke-static {}, Llow/moe/AkfcLoader;->wipeDecrypted()V\n\n',
                1,
                "AKFC cleanup",
            ),
        ]),
    ]

    loader_source = patch_root / "smali" / "low" / "moe" / "AkfcLoader.smali"
    loader_target = decoded / "smali" / "low" / "moe" / "AkfcLoader.smali"
    if loader_target.exists():
        raise FileExistsError(loader_target)
    loader_target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(loader_source, loader_target)
    changes.append({
        "path": loader_target.as_posix(),
        "before_sha256": None,
        "after_sha256": hashlib.sha256(loader_target.read_bytes()).hexdigest(),
    })
    return {"status": "patched", "changes": changes}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--decoded", type=Path, required=True)
    parser.add_argument(
        "--patch-root",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "patches" / "arcaea-7.0.255-arm64",
    )
    parser.add_argument("--receipt", type=Path)
    args = parser.parse_args()
    result = patch(args.decoded, args.patch_root)
    if args.receipt:
        args.receipt.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
