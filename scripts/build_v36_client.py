"""Build V36 from the verified V9 APK and public source, without a developer path map."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import shlex
import shutil
import zipfile

import build_akfc_loader
import build_android_client
import build_cap60_dex
import build_client_support as tools
import build_prod_rebase_dex
import build_production_bundle_partial_cache


ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "patches/arcaea-7.0.255-arm64/runtime"
BASE_SHA = "f14c5ab0871440dec7ecf2107d32d6e2cad745abc82047d03b49db9dbac3f545"
CORE_SHA = "1097f9e03939ae0cd47fc958bbb95ed241f61cf1f44eb7c2ef71406ea3367bbe"


def hydrate_sources(destination):
    document = json.loads((RUNTIME / "sources.json").read_bytes())
    if document.get("schema") != "akaine.v36.sources.v1":
        raise ValueError("V36 source manifest differs")
    seen, pinned = set(), {}
    for row in document["sources"]:
        role = build_android_client.archive_path(row["role"])
        source = build_android_client.private_file(ROOT, row["source"])
        if role in seen or source.is_symlink() or not source.is_file():
            raise ValueError("Duplicate or unavailable V36 source")
        seen.add(role)
        target = build_android_client.private_file(destination, role)
        if target.exists():
            raise ValueError("Runtime source destination is not fresh")
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        pinned[row["source"]] = tools.digest(source)
    return pinned


def compile_monitor(kit, llvm, output):
    output.mkdir()
    common = [llvm / "clang++.exe", "--target=aarch64-linux-android24",
              "--sysroot=" + str(llvm.parent / "sysroot"), "-std=c++17", "-O2", "-Wall", "-Wextra",
              "-Werror", "-fPIC", "-fvisibility=hidden", "-fvisibility-inlines-hidden"]
    for name, source, includes, exceptions in (
        ("monitor", kit / "semantic/native/anomaly_monitor_mod.cpp", [kit / "semantic/native"], False),
        ("owned", kit / "semantic/owned/owned_pack_module.cpp", [kit / "semantic/owned"], True),
    ):
        tools.run([*common, "-fexceptions" if exceptions else "-fno-exceptions",
                   *([] if exceptions else ["-fno-rtti"]), *("-I" + str(path) for path in includes),
                   "-MMD", "-MF", output / (name + ".d"), "-c", source, "-o", output / (name + ".o")])
        dependencies = shlex.split((output / (name + ".d")).read_text().replace("\\\n", " ").split(": ", 1)[1])
        for value in dependencies:
            Path(value).resolve().relative_to(kit.resolve())
    target = output / "libakaineanomaly_monitor.so"
    tools.run([llvm / "clang++.exe", "--target=aarch64-linux-android24", "-shared", "-static-libstdc++",
               "-Wl,--no-undefined", "-Wl,--strip-all", "-Wl,-z,max-page-size=16384",
               output / "monitor.o", output / "owned.o", "-llog", "-ldl", "-o", target])
    return target


def verify_loader(loader, llvm):
    symbols = tools.run([llvm / "llvm-readelf.exe", "--dyn-syms", "--wide", loader]).decode()
    dynamic = tools.run([llvm / "llvm-readelf.exe", "-d", loader]).decode()
    if (any(name not in symbols for name in ("Java_low_moe_AkfcLoader_installHooks", "Java_low_moe_AkfcLoader_wipeDecrypted"))
            or "Java_low_moe_AkfcLoader_decryptFile" in symbols
            or any(" UND " in line and ("akfc_" in line or "EVP_" in line) for line in symbols.splitlines())
            or "libcrypto.so" in dynamic or "libc++_shared.so" in dynamic):
        raise ValueError("Loader JNI/static-crypto contract differs")


def verify_unchanged_members(base, output, replacements):
    with zipfile.ZipFile(base) as before, zipfile.ZipFile(output) as after:
        old = {row.filename for row in before.infolist() if not row.is_dir()
               and not build_android_client.is_v1_signature(row.filename)}
        new = {row.filename for row in after.infolist() if not row.is_dir()}
        if new != old | set(replacements):
            raise ValueError("APK member set changed outside the declared payloads")
        for name in old - set(replacements):
            with before.open(name) as left, after.open(name) as right:
                if build_android_client.sha256_stream(left) != build_android_client.sha256_stream(right):
                    raise ValueError("Undeclared APK member changed")


def build(args):
    import build_v36_runtime
    base, output, header = args.base_apk.resolve(), args.output.absolute(), args.key_header.absolute()
    if tools.digest(base) != BASE_SHA:
        raise ValueError("Exact V9 APK required; this is not a fresh-XAPK build")
    tools.fresh_output(output)
    try:
        output.resolve().relative_to(ROOT.resolve())
    except ValueError:
        pass
    else:
        raise ValueError("Build output must remain outside the source checkout")
    if header.name != "embedded_key.h" or header.is_symlink() or not header.is_file():
        raise ValueError("External opaque embedded_key.h is required")
    try:
        header.resolve().relative_to(ROOT.resolve())
    except ValueError:
        pass
    else:
        raise ValueError("Key header must remain outside Git")
    if (ROOT / "patches/arcaea-7.0.255-arm64/native/embedded_key.h").exists():
        raise ValueError("Source-local key header would shadow the external reference")
    llvm = args.ndk / "toolchains/llvm/prebuilt/windows-x86_64/bin"
    javac = args.java.with_name("javac.exe")
    for path in (args.java, javac, args.jadx, args.d8, args.crypto, args.songlist, llvm / "clang++.exe"):
        if path.is_symlink() or not path.is_file():
            raise ValueError("A required build input is unavailable")
    output.mkdir(parents=True)
    kit = output / "runtime"
    sources = hydrate_sources(kit)
    core, pins, native = build_v36_runtime.build(base, kit, output / "native", llvm, args.songlist)
    if tools.digest(core) != CORE_SHA:
        raise ValueError("V36 native output differs from the guarded source build")
    monitor = compile_monitor(kit, llvm, output / "monitor")
    normalized, normalization = build_prod_rebase_dex.build(base, args.java, args.jadx,
        kit / "tools/RawDexTool.java", output / "dex-normalization")
    startup = tools.module("v36_startup", kit / "retained-build/build_startup_dex.py")
    prepared, startup_receipt = startup.build(normalized, args.java, args.jadx,
        kit / "tools/RawDexTool.java", output / "dex-startup")
    classes3, pacing = build_cap60_dex.build(prepared["classes3.dex"], args.java, args.jadx,
        kit / "tools/RawDexTool.java", output / "dex-pacing", kit / "pacing")
    classes3, cache = build_production_bundle_partial_cache.build(classes3, args.java, javac, args.jadx,
        kit / "tools/RawDexTool.java", args.d8, output / "dex-cache", kit / "bundle-partials")
    loader = output / "loader/libakfcloader.so"
    build_akfc_loader.build(ROOT / "patches/arcaea-7.0.255-arm64/native/akfc_loader.cpp",
        header, args.crypto, loader, llvm / "aarch64-linux-android24-clang++.cmd")
    verify_loader(loader, llvm)
    payloads = {"lib/arm64-v8a/libcocos2dcpp.so": core, "lib/arm64-v8a/libakaineanomaly_monitor.so": monitor,
                "lib/arm64-v8a/libakfcloader.so": loader, "classes3.dex": classes3, "classes4.dex": prepared["classes4.dex"]}
    replacements = []
    for name, path in payloads.items():
        target = output / "payloads" / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target)
        replacements.append({"archive_path": name, "file": "payloads/" + name, "sha256": tools.digest(target)})
    plan = {"schema": build_android_client.SCHEMA, "source_sha256": BASE_SHA, "content_version": "7.0.255.25",
            "replacements": replacements, "binary_patches": []}
    plan_path = output / "BUILD_PLAN.json"
    plan_path.write_text(json.dumps(plan, indent=2) + "\n", encoding="utf-8")
    assembled = build_android_client.build(base, plan_path, output, output / "unsigned.apk")
    verify_unchanged_members(base, output / "unsigned.apk", payloads)
    if any(tools.digest(ROOT / path) != value for path, value in sources.items()) or tools.digest(base) != BASE_SHA:
        raise ValueError("Source input changed during build")
    receipt = {"schema": "akaine.v36.build.v1", "status": "V36_SOURCE_BUILD_STATIC_CHECKS_PASS", "signed": False,
               "base_apk_sha256": BASE_SHA, "payload_sha256": {name: tools.digest(path) for name, path in payloads.items()},
               "runtime_sources": sources, "native": native, "dex_normalization": normalization,
               "startup": startup_receipt, "pacing": pacing, "partial_cache": cache, "assembly": assembled,
               "opaque_key_header_read_copied_hashed_or_logged_by_driver": False, "undeclared_apk_members_unchanged": True,
               "device_or_server_actions": False, "runtime_accepted": False}
    (output / "BUILD_RECEIPT.json").write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    return {"status": receipt["status"], "unsigned_apk": str(output / "unsigned.apk"), "runtime_accepted": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("base-apk", "songlist", "ndk", "java", "jadx", "d8", "crypto", "key-header", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    try:
        print(json.dumps(build(args)))
    except Exception:
        raise SystemExit("V36 build stopped. Inputs are unchanged; private compiler diagnostics were suppressed.") from None


if __name__ == "__main__":
    main()
