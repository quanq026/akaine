"""Hydrate a private kit, rebuild source payloads, reuse the existing APK builder."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import runpy
import shlex
import shutil
import struct
import subprocess
import sys
from types import SimpleNamespace
import zipfile
import zlib

import build_android_client
import build_dynamic_core

ROOT = Path(__file__).resolve().parents[1]
PROFILE = ROOT / 'patches/arcaea-7.0.255-arm64/staging-v20-source-lock.json'
CHECKOUT_SOURCES = PROFILE.with_name('staging-v20-checkout-sources.json')
PLAN = PROFILE.with_name('staging-v20-plan.json')


def digest(path):
    return build_android_client.sha256_file(Path(path))


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


def run(arguments):
    result = subprocess.run(list(map(str, arguments)), capture_output=True, timeout=180)
    if result.returncode:
        raise RuntimeError('Local build tool failed: ' + Path(arguments[0]).name)
    return result.stdout


def physical_output(path):
    path = path.absolute()
    if path.drive.upper() != 'D:' or path.exists():
        raise ValueError('Fresh physical-D output required')
    import ctypes
    buffer = ctypes.create_unicode_buffer(32768)
    if not ctypes.windll.kernel32.QueryDosDeviceW('D:', buffer, len(buffer)) or not buffer.value.startswith('\\Device\\HarddiskVolume'):
        raise ValueError('D must be a physical volume')
    raw = run(['powershell.exe', '-NoProfile', '-NonInteractive', '-Command',
        'Get-Partition -DriveLetter D | Get-Disk | Select-Object UniqueId,BusType,IsOffline,IsReadOnly | ConvertTo-Json -Compress'])
    disk = json.loads(raw)
    if (disk['UniqueId'] != '3044564198838200' or disk['BusType'] != 'USB'
            or disk['IsOffline'] or disk['IsReadOnly']):
        raise ValueError('Physical-D disk identity differs')
    for parent in (path, *path.parents):
        if parent.is_symlink() or parent.exists() and getattr(parent.stat(), 'st_file_attributes', 0) & 1024:
            raise ValueError('Output junction/symlink rejected')
    return disk


def manifest_rows(lock):
    return [*lock['monitor_compile_local_inputs'], *lock['additional_build_inputs'],
            *lock['compile_NDK_inputs'], *lock['expected_replacements'], lock['base_apk']]


def checkout_paths(lock, paths, document, root):
    if document.get('schema') != 'akaine.checkout-sources.v1':
        raise ValueError('Checkout source map schema differs')
    allowed = {row['role'] for row in manifest_rows(lock)}
    result, seen = dict(paths), set()
    for row in document['authored_sources']:
        role = row['role']
        if role not in allowed or role in seen:
            raise ValueError('Unknown or duplicate checkout source role')
        seen.add(role)
        relative = build_android_client.archive_path(row['repo_path'])
        result[role] = str(build_android_client.private_file(root, relative))
    return result


def verify(lock, paths):
    rows = manifest_rows(lock)
    roles = set()
    for row in rows:
        role = row['role']
        build_android_client.archive_path(role)
        if role in roles:
            raise ValueError('Duplicate release input role')
        roles.add(role)
        path = Path(paths[role])
        if path.is_symlink() or not path.is_file() or digest(path) != row['sha256']:
            raise ValueError('Release input hash differs: ' + role)
    return rows


def hydrate(lock, paths, destination):
    rows = verify(lock, paths)
    physical_output(destination)
    destination.mkdir(parents=True)
    hydrated = {}
    for row in rows:
        role = row['role']
        # SDK/JDK/runtime remain installed on fast W; only private project inputs
        # are hydrated. Expected payloads are controls, never compile inputs.
        if role.startswith(('android-sdk/', 'tools/java-17/')):
            hydrated[role] = paths[role]
            continue
        target = build_android_client.private_file(destination, role)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(paths[role], target)
        if digest(target) != row['sha256']:
            raise ValueError('Hydrated file differs')
        hydrated[role] = str(target)
    helper = destination / 'retained-build/broad/native/compare_core.py'
    helper.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(hydrated['retained-build/compare_core.py'], helper)
    (destination / 'local-paths.json').write_text(json.dumps({'status': 'PRIVATE_LOCAL_ONLY', 'paths': hydrated}, indent=2) + '\n')
    return hydrated


def source_api(kit, paths):
    Elf = runpy.run_path(str(kit / 'retained-build/compare_core.py'))['Elf']
    Unwind = runpy.run_path(str(kit / 'retained-build/core_unwind_map.py'))['UnwindMap']
    with zipfile.ZipFile(paths['base/v18-staging.apk']) as archive:
        elf = Elf(archive.read('lib/arm64-v8a/libcocos2dcpp.so'))
    if hashlib.sha256(elf.raw).hexdigest() != 'aba3463bcb06ca5567c1190009c2ae1f9b7ddf56d1c1503f8d5055980a1f2c1b':
        raise ValueError('Base V18 core differs')
    return SimpleNamespace(Elf=Elf, elf=elf, unwind=Unwind(elf))


def native(kit, paths, output):
    llvm = Path(paths['android-sdk/ndk/28.2.13676358/toolchains/llvm/prebuilt/windows-x86_64/bin/clang++.exe']).parent
    core = build_dynamic_core.build_core(kit, output, llvm, source_api(kit, paths))
    if digest(output / 'owned_core_pins.h') != digest(paths['semantic/owned/owned_core_pins.h']):
        raise ValueError('Regenerated native core pins differ')
    common = [llvm / 'clang++.exe', '--target=aarch64-linux-android24', '--sysroot=' + str(llvm.parent / 'sysroot'),
        '-std=c++17', '-O2', '-Wall', '-Wextra', '-Werror', '-fPIC', '-fvisibility=hidden', '-fvisibility-inlines-hidden']
    native_root = kit / 'semantic/native'
    run([*common, '-fno-exceptions', '-fno-rtti', '-I' + str(native_root), '-MD', '-MF', output / 'monitor.d',
         '-c', native_root / 'anomaly_monitor_mod.cpp', '-o', output / 'monitor.o'])
    run([*common, '-fexceptions', '-I' + str(kit / 'semantic/owned'), '-I' + str(output),
         '-MD', '-MF', output / 'owned.d', '-c', kit / 'semantic/owned/owned_pack_module.cpp', '-o', output / 'owned.o'])
    monitor = output / 'libakaineanomaly_monitor-owned-v19.so'
    run([llvm / 'clang++.exe', '--target=aarch64-linux-android24', '-shared', '-static-libstdc++',
        '-Wl,--no-undefined', '-Wl,--strip-all', '-Wl,-Map=' + str(output / 'monitor.map'), '-Wl,-z,max-page-size=16384',
        output / 'monitor.o', output / 'owned.o', '-llog', '-ldl', '-o', monitor])
    allowed = {Path(path).resolve() for path in paths.values()} | {(output / 'owned_core_pins.h').resolve()}
    for name in ('monitor.d', 'owned.d'):
        dependencies = shlex.split((output / name).read_text().replace('\\\n', ' ').split(': ', 1)[1])
        if any(Path(path).resolve() not in allowed for path in dependencies):
            raise ValueError('Compiler used an unpinned include')
    return {'lib/arm64-v8a/libcocos2dcpp.so': core, 'lib/arm64-v8a/libakaineanomaly_monitor.so': monitor}


def dex(kit, paths, output):
    builder = module('normalized_retained_dex', kit / 'retained-build/build_startup_dex.py')
    builder.JAVA = Path(paths['tools/java-17/bin/java.exe'])
    builder.RETAINED = kit / 'tools'
    builder.JAR = Path(paths['tools/jadx-1.5.6-all.jar'])
    # Java's source-file launcher uses the versioned helper, not a retained class.
    def source_tool(mode, source, target):
        run([builder.JAVA, '-cp', builder.JAR, paths['tools/RawDexTool.java'], mode, source, target])
    builder.tool = source_tool
    output.mkdir()
    result = {}
    for name in ('classes3', 'classes4'):
        before, after = output / (name + '-before'), output / (name + '-after')
        builder.tool('disassemble', Path(paths['dex/' + name + '-source.dex']), before)
        shutil.copytree(before, after)
        relative = builder.RENDERER if name == 'classes3' else builder.MONITOR
        target = after / relative
        text = target.read_text(encoding='utf-8')
        if name == 'classes3':
            start = text.index('.method ' + builder.SURFACE)
            at = text.index('    .line 85\n', start) + len('    .line 85\n')
            text = text[:at] + '    invoke-static {}, Llow/moe/AnomalyMonitor;->prepare()V\n\n' + text[at:]
        else:
            if 'prepareNative' in text:
                raise ValueError('Base DEX already has early prepare')
            text += '\n' + builder.PREPARE
        target.write_text(text, encoding='utf-8', newline='\n')
        builder.compare(before, after, name)
        target_dex = output / (name + '.dex')
        builder.tool('assemble', after, target_dex)
        raw = target_dex.read_bytes()
        if (raw[:8] != b'dex\n037\0' or raw[12:32] != hashlib.sha1(raw[32:]).digest()
                or struct.unpack_from('<I', raw, 8)[0] != zlib.adler32(raw[12:]) & 0xffffffff):
            raise ValueError('DEX header/checksum differs')
        verified = output / (name + '-verified')
        builder.tool('disassemble', target_dex, verified)
        builder.compare(before, verified, name)
        result[name + '.dex'] = target_dex
    return result


def build(lock, paths, output):
    verify(lock, paths)
    disk = physical_output(output)
    kit = Path(paths['semantic/native/anomaly_monitor_mod.cpp']).parents[2]
    if not kit.is_dir() or not (kit / 'semantic/owned/owned_pack_module.cpp').is_file():
        raise ValueError('Run hydrate into a clean private kit first')
    output.mkdir(parents=True)
    payloads = native(kit, paths, output / 'native')
    payloads.update(dex(kit, paths, output / 'dex'))
    expected = {row['role'].removeprefix('v19-r5/payload/'): row['sha256'] for row in lock['expected_replacements']}
    actual = {name: digest(path) for name, path in payloads.items()}
    if actual != expected:
        (output / 'PAYLOAD_MISMATCH.json').write_text(json.dumps({'expected': expected, 'actual': actual}, indent=2) + '\n')
        raise ValueError('Clean source payload differs; keep output for diagnosis, no APK assembled')
    plan = json.loads(PLAN.read_bytes())
    for row in plan['replacements']:
        target = output / 'kit' / row['file']
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(payloads[row['archive_path']], target)
    plan_path = output / 'plan.json'
    plan_path.write_text(json.dumps(plan, indent=2) + '\n')
    result = build_android_client.build(Path(paths['base/v18-staging.apk']), plan_path, output / 'kit', output / 'unsigned.apk')
    verify(lock, paths)
    receipt = {'status': 'CLEAN_SOURCE_PAYLOADS_MATCH_UNSIGNED_ASSEMBLY_PASS', 'payload_sha256': actual,
        'source_lock_sha256': digest(PROFILE), 'unsigned_apk_sha256': digest(output / 'unsigned.apk'),
        'checkout_sources_sha256': digest(CHECKOUT_SOURCES),
        'existing_builder_receipt': result, 'external_disk': disk, 'signed': False,
        'runtime_acceptance_reused': 'Source payload identity only; signature, install and runtime acceptance are separate gates.'}
    (output / 'BUILD_RECEIPT.json').write_text(json.dumps(receipt, indent=2) + '\n')
    return receipt


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=('verify', 'hydrate', 'build', 'all'))
    parser.add_argument('--local-paths', type=Path, required=True)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    lock = json.loads(PROFILE.read_bytes())
    paths = json.loads(args.local_paths.read_bytes())['paths']
    checkout = json.loads(CHECKOUT_SOURCES.read_bytes())
    if checkout['source_lock_sha256'] != digest(PROFILE):
        raise ValueError('Checkout sources target a different source lock')
    checkout_bound = checkout_paths(lock, paths, checkout, ROOT)
    if args.mode == 'build':
        verify(lock, checkout_bound)
    else:
        paths = checkout_bound
    if args.mode == 'verify':
        print(json.dumps({'status': 'RELEASE_INPUT_HASHES_PASS', 'roles': len(verify(lock, paths))}))
    elif args.mode == 'hydrate':
        if not args.output:
            parser.error('hydrate requires --output')
        values = hydrate(lock, paths, args.output)
        print(json.dumps({'status': 'PRIVATE_KIT_HYDRATED', 'roles': len(values), 'output': str(args.output)}))
    elif args.mode == 'build':
        if not args.output:
            parser.error('build requires --output')
        print(json.dumps(build(lock, paths, args.output)))
    else:
        if not args.output:
            parser.error('all requires --output')
        physical_output(args.output)
        args.output.mkdir(parents=True)
        hydrated = hydrate(lock, paths, args.output / 'private-kit')
        print(json.dumps(build(lock, hydrated, args.output / 'build')))
