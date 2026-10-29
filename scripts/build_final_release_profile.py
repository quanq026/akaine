"""Rebuild the five reviewed payloads; reuse the existing local build engines."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
from types import SimpleNamespace

import assetset_identity
import build_android_client
import build_cap60_dex
import build_bundle_partial_cache
import build_dynamic_core
import build_loader_equivalence
import build_release_profile as shared
import build_reset_core
import build_integrity_core

ROOT = Path(__file__).resolve().parents[1]
PROFILE = ROOT / 'patches/arcaea-7.0.255-arm64/staging-final-source-lock.json'
CHECKOUT = PROFILE.with_name('staging-final-checkout-sources.json')
PLAN = PROFILE.with_name('staging-final-plan.json')
LOADER_PROFILE = PROFILE.with_name('staging-loader-v6-equivalence.json')


def digest(path):
    return shared.digest(path)


def bound_paths(lock, paths, root=ROOT):
    document = json.loads((root / CHECKOUT.relative_to(ROOT)).read_bytes())
    if document['source_lock_sha256'] != digest(root / PROFILE.relative_to(ROOT)):
        raise ValueError('Final checkout source map differs from its lock')
    return shared.checkout_paths(lock, paths, document, root)


def expected_payloads(lock):
    return {row['role'].removeprefix('final/payload/'): row['sha256'] for row in lock['expected_replacements']}


def loader_paths(paths):
    return {'compiler': paths['loader/compiler'], 'crypto': paths['loader/crypto']}


def verify(lock, paths):
    if lock['release'] != 'staging-final-combined' or lock['content_version'] != '7.0.255.20':
        raise ValueError('Explicit final staging profile required')
    rows = shared.verify(lock, paths)
    if digest(Path(build_integrity_core.__file__)) != digest(paths['integrity/build_integrity_core.py']):
        raise ValueError('Active integrity builder differs from pinned checkout source')
    if digest(Path(build_bundle_partial_cache.__file__)) != digest(paths['bundle-partials/build_bundle_partial_cache.py']):
        raise ValueError('Active partial-cache builder differs from pinned checkout source')
    if digest(PLAN) != lock['build_plan_sha256']:
        raise ValueError('Final replacement plan differs')
    plan = build_android_client.load_plan(PLAN)
    expected = expected_payloads(lock)
    if (len(expected) != 5 or {row['archive_path']: row['sha256'] for row in plan['replacements']} != expected
            or plan['source_sha256'] != lock['base_apk']['sha256'] or not plan['not_for_production']):
        raise ValueError('Five-payload final plan/lock contract differs')
    build_loader_equivalence.verify(json.loads(LOADER_PROFILE.read_bytes()), loader_paths(paths))
    return rows


def compile_monitor(kit, paths, output):
    llvm = Path(paths['android-sdk/ndk/28.2.13676358/toolchains/llvm/prebuilt/windows-x86_64/bin/clang++.exe']).parent
    output.mkdir()
    common = [llvm / 'clang++.exe', '--target=aarch64-linux-android24', '--sysroot=' + str(llvm.parent / 'sysroot'),
              '-std=c++17', '-O2', '-Wall', '-Wextra', '-Werror', '-fPIC', '-fvisibility=hidden', '-fvisibility-inlines-hidden']
    shared.run([*common, '-fno-exceptions', '-fno-rtti', '-I' + str(kit / 'semantic/native'), '-MD', '-MF', output / 'monitor.d',
                '-c', kit / 'semantic/native/anomaly_monitor_mod.cpp', '-o', output / 'monitor.o'])
    shared.run([*common, '-fexceptions', '-I' + str(kit / 'semantic/owned'), '-MD', '-MF', output / 'owned.d',
                '-c', kit / 'semantic/owned/owned_pack_module.cpp', '-o', output / 'owned.o'])
    target = output / 'libakaineanomaly_monitor.so'
    shared.run([llvm / 'clang++.exe', '--target=aarch64-linux-android24', '-shared', '-static-libstdc++', '-Wl,--no-undefined',
                '-Wl,--strip-all', '-Wl,-Map=' + str(output / 'monitor.map'), '-Wl,-z,max-page-size=16384',
                output / 'monitor.o', output / 'owned.o', '-llog', '-ldl', '-o', target])
    import shlex
    allowed = {Path(path).resolve() for path in paths.values()}
    for name in ('monitor.d', 'owned.d'):
        dependencies = shlex.split((output / name).read_text().replace('\\\n', ' ').split(': ', 1)[1])
        if any(Path(path).resolve() not in allowed for path in dependencies):
            raise ValueError('Final compiler used an unpinned dependency')
    return target


def build(lock, paths, output):
    verify(lock, paths)
    disk = shared.physical_output(output)
    output.mkdir(parents=True)
    kit = output / 'private-kit'
    hydrated = shared.hydrate(lock, paths, kit)
    source = shared.source_api(kit, hydrated)
    llvm = Path(hydrated['android-sdk/ndk/28.2.13676358/toolchains/llvm/prebuilt/windows-x86_64/bin/clang++.exe']).parent
    r5core = build_dynamic_core.build_core(kit, output / 'r5-core', llvm, source)
    if digest(output / 'r5-core/owned_core_pins.h') != digest(hydrated['reset-baseline/semantic/owned/owned_core_pins.h']):
        raise ValueError('Regenerated baseline owned pins differ')
    # Feed freshly rebuilt R5 bytes into the already reviewed finite Reset patch.
    import capstone
    original = r5core.read_bytes()
    reader = SimpleNamespace(raw=original, SHA=hashlib.sha256(original).hexdigest(), elf=source.Elf(original),
        read=lambda address, size: build_dynamic_core.virtual_bytes(original, address, size),
        decoder=capstone.Cs(capstone.CS_ARCH_ARM64, capstone.CS_MODE_ARM))
    core, pins, reset_receipt = build_reset_core.build(kit / 'semantic/owned/reset_gate.S', kit / 'reset-baseline',
                                                     output / 'reset-core', llvm, reader)
    core, pins, integrity_receipt = build_integrity_core.build(core, pins, kit / 'integrity/download_success_size_gate.S',
        kit / 'integrity/download_run_once_gate.S', kit / 'integrity/child_order_gate.S', output / 'integrity-core', llvm)
    for role, name in (('semantic/owned/owned_core_pins.h', 'owned_core_pins.h'),
                       ('semantic/song-v9/cli_song_pins.h', 'cli_song_pins.h')):
        if digest(pins / name) != digest(hydrated[role]):
            raise ValueError('Regenerated final private pins differ')
        shutil.copy2(pins / name, hydrated[role])
    monitor = compile_monitor(kit, hydrated, output / 'monitor')
    base_dex = shared.dex(kit, hydrated, output / 'base-dex')
    classes3, pacing_receipt = build_cap60_dex.build(base_dex['classes3.dex'], Path(hydrated['tools/java-17/bin/java.exe']),
        Path(hydrated['tools/jadx-1.5.6-all.jar']), Path(hydrated['tools/RawDexTool.java']), output / 'pacing-dex', kit / 'pacing')
    classes3, partial_cache_receipt = build_bundle_partial_cache.build(classes3,
        Path(hydrated['tools/java-17/bin/java.exe']), Path(hydrated['tools/java-17/bin/javac.exe']),
        Path(hydrated['tools/jadx-1.5.6-all.jar']), Path(hydrated['tools/RawDexTool.java']),
        Path(hydrated['tools/android-build-35/d8.jar']), output / 'bundle-partials-dex', kit / 'bundle-partials')
    loader_receipt = build_loader_equivalence.build(json.loads(LOADER_PROFILE.read_bytes()), loader_paths(paths), output / 'loader')
    payloads = {'lib/arm64-v8a/libcocos2dcpp.so': core, 'lib/arm64-v8a/libakaineanomaly_monitor.so': monitor,
                'lib/arm64-v8a/libakfcloader.so': output / 'loader/libakfcloader.so',
                'classes3.dex': classes3, 'classes4.dex': base_dex['classes4.dex']}
    actual = {name: digest(path) for name, path in payloads.items()}
    if actual != expected_payloads(lock):
        (output / 'PAYLOAD_MISMATCH.json').write_text(json.dumps({'actual': actual, 'expected': expected_payloads(lock)}, indent=2) + '\n')
        raise ValueError('Final source payload differs; stop before APK')
    # The same asset identity that is advertised must match both input and output APK.
    before_assets = assetset_identity.verify_apk(hydrated['base/v18-staging.apk'], hydrated['assetset/manifest.json'])
    if before_assets['assetset_sha256'] != lock['assetset_sha256']:
        raise ValueError('Final base asset set differs')
    plan = json.loads(PLAN.read_bytes())
    for row in plan['replacements']:
        path = output / 'payload-kit' / row['file']
        path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(payloads[row['archive_path']], path)
    built = build_android_client.build(Path(hydrated['base/v18-staging.apk']), PLAN, output / 'payload-kit', output / 'unsigned.apk')
    after_assets = assetset_identity.verify_apk(output / 'unsigned.apk', hydrated['assetset/manifest.json'])
    verify(lock, paths)
    receipt = {'status': 'FIVE_SOURCE_PAYLOADS_AND_UNSIGNED_APK_MATCH', 'payload_sha256': actual,
               'source_lock_sha256': digest(PROFILE), 'checkout_map_sha256': digest(CHECKOUT),
               'reset_core_receipt': reset_receipt, 'integrity_core_receipt': integrity_receipt, 'pacing_receipt': pacing_receipt, 'partial_cache_receipt': partial_cache_receipt,
               'loader_receipt': loader_receipt, 'builder_receipt': built, 'base_assets': before_assets, 'output_assets': after_assets,
               'unsigned_apk_sha256': digest(output / 'unsigned.apk'), 'external_disk': disk,
               'signed': False, 'device_or_server_actions': False, 'runtime_accepted': False}
    (output / 'BUILD_RECEIPT.json').write_text(json.dumps(receipt, indent=2) + '\n')
    return receipt


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=('verify', 'build'))
    parser.add_argument('--local-paths', type=Path, required=True)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    try:
        lock = json.loads(PROFILE.read_bytes())
        paths = bound_paths(lock, json.loads(args.local_paths.read_bytes())['paths'])
        if args.mode == 'verify':
            print(json.dumps({'status': 'FINAL_SOURCE_PRIVATE_INPUTS_AND_PLAN_VERIFIED', 'roles': len(verify(lock, paths)),
                              'opaque_header_accessed': False}))
        else:
            if args.output is None: parser.error('Build requires a fresh physical-D output')
            print(json.dumps(build(lock, paths, args.output)))
    except Exception:
        raise SystemExit('Final source build stopped; private compiler diagnostics suppressed') from None
