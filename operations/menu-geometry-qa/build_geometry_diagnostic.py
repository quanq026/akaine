"""Four QA-only V34 geometry probes. Default preparation never compiles or installs."""
import argparse
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import shutil
import struct
import subprocess
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
BASE = Path('D:/AkaineBuilds/prod-rebase-20261025/rebased-clean-build-v34')
KIT = BASE / 'private-kit'
REPO = BASE.parent / 'source'
CORE = BASE / 'payload-kit/final/payload/lib/arm64-v8a/libcocos2dcpp.so'
MONITOR = BASE / 'monitor/libakaineanomaly_monitor.so'
LOCK = REPO / 'patches/arcaea-7.0.255-arm64/prod-rebase-source-lock.json'
LLVM = Path('W:/Not at home/drives/E/_organized/platform/android/Sdk/ndk/28.2.13676358/toolchains/llvm/prebuilt/windows-x86_64/bin')
SDK = LLVM.parents[6]
API_LIB = LLVM.parent / 'sysroot/usr/lib/aarch64-linux-android/24'
POINTS = ((1, 0, 0x16463cc), (1, 1, 0x1646508), (2, 0, 0xcf706c), (2, 1, 0xcf7320))
PREIMAGES = ('e923b96d', 'c0035fd6', 'ffc302d1', 'c0035fd6')
PINS = {
    CORE: '299f271b3b0bb8a656ba02be6fd6327f90b1a0fe2fe11d1e670ae51ccfdae42d',
    MONITOR: '2628c50fd07f0743bc50536e211e7e33e488bf01a1a06729ad3d4b02eea92539',
    LOCK: 'e718fa150d1723fd81d91feedbdaf2ee1a18fb136cde951421baeac8b3052e55',
    ROOT / 'work/emu-finish-20261025/menu/build_inner_rebuild_diagnostic.py': '5e240c9fb80404aca28652b7c9ef76870a06ed6350235a36541715a35ab914be',
    ROOT / 'work/emu-finish-20261025/menu/test_native_gates.py': '2c2be2355d7900588592b9d4ba96e652422722caac7d7d7832ba7113c7d588f8',
    ROOT / 'work/big-update-20261024/review_cli_perf_binary.py': '273a1a5a68067f075ef783e469ac779c23580d62a036d04ec6413cc2916fef3e',
    REPO / 'scripts/build_release_profile.py': '74219e88af6784b008e6c3c8fe1446f41ce2ce3238d8c02c8d0694928536e343',
    LLVM / 'llvm-nm.exe': '90236526ebb24c232e59ec573675e32a92190b3346cf3a342c8b0eb5ad0f8203',
    API_LIB / 'liblog.so': 'ae592b3e8aced4ab769a9d94b5444093ea0968dc1491f5245909c4966af4d57d',
    API_LIB / 'libdl.so': 'be8fd669d4afe85483da999e7d56ea5e01a9d01d8315b402a70e3bac858cf6a3',
    API_LIB / 'libm.so': 'b566f9cdbbba24b4c6cb9e207beb4b6e8259776ac1305944afa6c8eae3aefc91',
    API_LIB / 'libc.so': '3751ff3d8b61db86ca69d8ae5c646c8346750e83433fe1abd17885c48b47efea',
}


def digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def require(value, message):
    if not value:
        raise ValueError(message)


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def inputs():
    for path, expected in PINS.items():
        require(path.is_file() and not path.is_symlink() and digest(path) == expected, 'Frozen diagnostic input differs: ' + path.name)
    lock = json.loads(LOCK.read_bytes())
    rows = [*lock['monitor_compile_local_inputs'], *lock['additional_build_inputs'], *lock['compile_NDK_inputs']]
    semantic = {row['role']: row for row in rows if row['role'].startswith('semantic/')}
    found = {path.relative_to(KIT).as_posix() for path in (KIT / 'semantic').rglob('*') if path.is_file()}
    require(len(semantic) == 72 and found == set(semantic), 'Frozen V34 semantic inventory differs')
    for name, row in semantic.items():
        require(not (KIT / name).is_symlink() and digest(KIT / name) == row['sha256'], 'Frozen V34 semantic source differs')
    helper = load('geometry_existing_ELF', ROOT / 'work/big-update-20261024/review_cli_perf_binary.py')
    engine = load('geometry_existing_gate_generator', ROOT / 'work/emu-finish-20261025/menu/build_inner_rebuild_diagnostic.py')
    raw = CORE.read_bytes(); elf = helper.Elf(raw)
    for point, expected in zip(POINTS, PREIMAGES):
        require(elf.virtual_bytes(point[2], 4).hex() == expected, 'Exact diagnostic hook preimage differs')
    rx = [(i, row) for i, row in enumerate(elf.ph) if row[0] == 1 and row[1] == 5 and row[3] == 0]
    require(len(rx) == 1 and rx[0][1][2] == 0 and rx[0][1][5] == rx[0][1][6] == 0x1a7e5e4, 'Exact V34 RX layout differs')
    require(min(row[3] & ~0x3fff for row in elf.ph if row[0] == 1 and row[3] > 0) == 0x1a80000, 'Mapped-page cave boundary differs')
    return rows, semantic, helper, engine, raw, elf, rx[0][0]


def prepare():
    rows, semantic, helper, engine, raw, elf, rx_index = inputs()
    assembly = engine.assembly(POINTS, elf)
    target = HERE / 'menu_gates.S'
    if target.exists():
        require(target.read_bytes() == assembly.encode(), 'Prepared gate source differs')
    else:
        target.write_text(assembly, encoding='utf-8', newline='\n')
    result = {'status': 'QA_GEOMETRY_SOURCE_PREPARED_NOT_COMPILED', 'diagnostic_only': True,
        'builder_sha256': digest(Path(__file__)), 'header_sha256': digest(HERE / 'menu_geometry_trace.h'),
        'assembly_sha256': digest(target), 'fixture_sha256': digest(HERE / 'test_geometry_aggregate.cpp'),
        'JNI_interval_helper_sha256': digest(HERE / 'geometry_interval_jni.h'),
        'input_pins': {str(path): value for path, value in PINS.items()},
        'frozen_semantic_inputs': [{'role': name, 'sha256': row['sha256']} for name, row in sorted(semantic.items())],
        'points': [{'id': event, 'kind': kind, 'RVA': hex(at), 'preimage': before} for (event, kind, at), before in zip(POINTS, PREIMAGES)],
        'cave_start': '0x1a7e5f0', 'maximum_cave_end_exclusive': '0x1a80000', 'expected_gate_bytes': 1276,
        'NO_FDE_INSIDE_PROBE_CAVE': True, 'exceptions_may_bypass_RET_and_invalidate_window': True,
        'source_profile_APK_loader_devices_or_network_modified': False}
    (HERE / 'PREPARATION.json').write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8', newline='\n')
    return result


def run(arguments):
    value = subprocess.run(list(map(str, arguments)), capture_output=True, timeout=180)
    require(value.returncode == 0, 'Diagnostic tool failed; inspect nonsecret QA sources')
    return value.stdout.decode(errors='replace')


def machine_cases(hooks, gate, cave):
    import capstone
    fixture = load('geometry_existing_symbolic_CPU', ROOT / 'work/emu-finish-20261025/menu/test_native_gates.py')
    decoder = capstone.Cs(capstone.CS_ARCH_ARM64, capstone.CS_MODE_ARM)
    code = {instruction.address: instruction for instruction in decoder.disasm(gate, cave)}
    count = 0
    for hook in hooks:
        original = next(decoder.disasm(bytes.fromhex(hook['before']), hook['address']))
        for version, ready, pointer in ((0, 0, 0), (1, 0, 0x10000000), (1, 1, 0), (1, 1, 0x10000000)):
            for seed in range(5):
                cpu = fixture.CPU(seed)
                for address, value in ((0x1c031c0, version), (0x1c031c8, ready), (0x1c03208, pointer)):
                    cpu.write(address, 8, value)
                expected = copy.deepcopy(cpu); expected.step(original, hook['id'], hook['kind']); cpu.pc = hook['gate']
                for unused in range(200):
                    if cpu.pc not in code: break
                    cpu.step(code[cpu.pc], hook['id'], hook['kind'])
                else: raise ValueError('Unbounded emitted diagnostic gate')
                require(cpu.r == expected.r and cpu.pc == expected.pc, 'Emitted gate changes original machine state')
                require(all(cpu.memory.get(at) == byte for at, byte in expected.memory.items()), 'Displaced native store differs')
                require(len(cpu.calls) == int(version == 1 and ready == 1 and bool(pointer)), 'Mailbox fallback differs')
                count += 1
    require(count == 80, 'Exact four-gate symbolic case count differs')
    return count


def build(output, review_path, review_sha):
    prepared = prepare()
    require(digest(review_path) == review_sha, 'Independent diagnostic source review hash differs')
    review = json.loads(review_path.read_bytes())
    require(review.get('status') == 'PASS_QA_GEOMETRY_DIAGNOSTIC_SOURCE_REVIEW' and review.get('findings') == []
        and review.get('preparation_sha256') == digest(HERE / 'PREPARATION.json')
        and review.get('NO_FDE_INSIDE_PROBE_CAVE_accepted_for_QA_emulator_only') is True,
        'Exact independent source review with QA-only unwind limitation required')
    rows, semantic, helper, engine, raw, elf, rx_index = inputs()
    sys.path.insert(0, str(REPO / 'scripts'))
    guard = load('geometry_existing_physical_output_guard', REPO / 'scripts/build_release_profile.py')
    disk = guard.physical_output(output); output.mkdir(parents=True)
    source_identities = {path: (path.stat().st_size, path.stat().st_mtime_ns, digest(path)) for path in [*PINS, review_path,
        HERE / 'PREPARATION.json', HERE / 'menu_gates.S', HERE / 'menu_geometry_trace.h', HERE / 'geometry_interval_jni.h',
        HERE / 'test_geometry_aggregate.cpp', Path(__file__),
        *(KIT / name for name in semantic)]}
    pinned = {row['role']: row['sha256'] for row in rows}
    sdk_inputs = {SDK / row['role'].removeprefix('android-sdk/'): row['sha256']
                  for row in rows if row['role'].startswith('android-sdk/')}
    sdk_inputs.update({path: pin for path, pin in PINS.items() if path.is_relative_to(SDK)})
    require(all(path.is_file() and not path.is_symlink() and digest(path) == pin for path, pin in sdk_inputs.items()),
        'Frozen SDK compiler, header, startup or library input differs')
    def tool(name):
        path = LLVM / name; role = 'android-sdk/' + path.relative_to(SDK).as_posix()
        expected = pinned.get(role, PINS.get(path))
        require(expected and digest(path) == expected, 'Pinned diagnostic NDK tool differs: ' + name)
        return path
    cave = 0x1a7e5f0
    run([tool('clang.exe'), '--target=aarch64-linux-android24', '-c', HERE / 'menu_gates.S', '-o', output / 'gates.o'])
    symbols = [f'--defsym=menu_resume_{i}={at + 4:#x}' for i, (event, kind, at) in enumerate(POINTS) if kind != 1]
    run([tool('ld.lld.exe'), '--entry=menu_gate_0', f'--section-start=.menu_trace={cave:#x}',
         '--defsym=menu_mailbox=0x1c031c0', *symbols, output / 'gates.o', '-o', output / 'gates.elf'])
    run([tool('llvm-objcopy.exe'), '-O', 'binary', '--only-section=.menu_trace', output / 'gates.elf', output / 'gates.bin'])
    gate = (output / 'gates.bin').read_bytes(); end = cave + len(gate)
    require(len(gate) == 1276 and end < 0x1a80000 and raw[cave:end] == bytes(len(gate)), 'Exact cave capacity or zero preimage differs')
    names = run([tool('llvm-nm.exe'), '-n', output / 'gates.elf'])
    addresses = {name: int(value, 16) for value, kind, name in re.findall(r'^(\w+)\s+(\w)\s+(\w+)$', names, re.M)}
    patched = bytearray(raw); ph_at = elf.header[5] + rx_index * elf.header[9] + 32
    struct.pack_into('<QQ', patched, ph_at, end, end); patched[cave:end] = gate
    changes = [(ph_at, ph_at + 16), (cave, end)]; hooks = []
    for i, (event, kind, at) in enumerate(POINTS):
        target = addresses[f'menu_gate_{i}']; before = elf.virtual_bytes(at, 4)
        patched[at:at + 4] = engine.branch(at, target); changes.append((at, at + 4))
        hooks.append(dict(id=event, kind=kind, address=at, gate=target, before=before.hex(), after=bytes(patched[at:at + 4]).hex()))
    cursor = 0
    for first, last in sorted(changes):
        require(cursor <= first and patched[cursor:first] == raw[cursor:first], 'Unlisted core change')
        cursor = last
    require(patched[cursor:] == raw[cursor:], 'Unlisted trailing core change')
    cases = machine_cases(hooks, gate, cave)
    candidate = helper.Elf(bytes(patched)); core_target = output / 'libcocos2dcpp-QA-GEOMETRY-NO-FDE.so'; core_target.write_bytes(patched)
    shutil.copytree(KIT / 'semantic', output / 'semantic'); native = output / 'semantic/native'
    require(all(digest(output / name) == row['sha256'] for name, row in semantic.items()), 'Copied frozen semantic source differs')
    shutil.copy2(HERE / 'menu_geometry_trace.h', native / 'menu_geometry_trace.h')
    shutil.copy2(HERE / 'geometry_interval_jni.h', native / 'geometry_interval_jni.h')
    for relative, marker, replacement in (
        ('native/anomaly_monitor_mod.cpp', '#include "perf_aggregate.h"', '#include "perf_aggregate.h"\n#include "menu_geometry_trace.h"'),
        ('native/staging_cli_bridge.h', '    result.ready = true;', '    result.ready = true;\n    if (!strcmp(result.klass, "15SongSelectScene")) menu_geometry::arm();'),
        ('native/anomaly_monitor_mod.cpp', 'extern "C" JNIEXPORT void JNICALL Java_low_moe_AnomalyMonitor_frameNative(JNIEnv*, jclass) {\n    frame();',
         '#include "geometry_interval_jni.h"\nextern "C" JNIEXPORT void JNICALL Java_low_moe_AnomalyMonitor_frameNative(JNIEnv* env, jclass) {\n    menu_geometry_jni::capture(env);\n    frame();'),
        ('owned/owned_pack_module.cpp', '        hooks_ready.store(true, std::memory_order_release);',
         '        mailbox->reserved[0] = reinterpret_cast<uintptr_t>(&menu_geometry::event);\n        hooks_ready.store(true, std::memory_order_release);')):
        path = output / 'semantic' / relative; text = path.read_text(); require(text.count(marker) == 1, 'Exact QA overlay marker differs')
        text = text.replace(marker, replacement, 1)
        if relative.startswith('owned/'): text = '#include "../native/menu_geometry_trace.h"\n' + text
        path.write_text(text, encoding='utf-8', newline='\n')
    changed_pins = []
    for path in sorted((output / 'semantic').rglob('*.h')):
        original_text = path.read_text(); text = original_text
        arrays = {m[1]: m for m in re.finditer(r'(?:inline constexpr |constexpr |static constexpr )?unsigned char\s+(\w+)\[\]\s*=\s*\{([^}]+)\}', text)}
        replacements = {}
        for address, name in re.findall(r'\{\s*(0x[0-9a-fA-F]+)\s*,\s*(\w+)\s*,\s*sizeof\(\2\)\s*\}', text):
            if name not in arrays: continue
            match = arrays[name]; blob = bytes(int(x, 16) for x in re.findall(r'0x([0-9a-fA-F]+)', match[2])); address = int(address, 16)
            require(elf.virtual_bytes(address, len(blob)) == blob, 'Frozen core pin differs')
            updated = candidate.virtual_bytes(address, len(blob))
            if updated != blob: replacements[name] = updated; changed_pins.append(dict(file=path.relative_to(output).as_posix(), name=name))
        for name, blob in replacements.items():
            old = arrays[name][0]; text = text.replace(old, old[:old.index('{') + 1] + ','.join(hex(x) for x in blob) + '}', 1)
        if path.name == 'owned_core_pins.h':
            require(text.count('OWNED_RX_END = 0x1a7e5e4;') == 1, 'Frozen owned RX pin differs')
            text = text.replace('OWNED_RX_END = 0x1a7e5e4;', f'OWNED_RX_END = {end:#x};')
            extra = [(cave, gate), (ph_at, bytes(patched[ph_at:ph_at + 16]))] + [(h['address'], bytes.fromhex(h['after'])) for h in hooks]
            defs = '\n'.join(f'inline constexpr unsigned char geometry_pin_{i}[] = {{' + ','.join(hex(x) for x in blob) + '};' for i, (address, blob) in enumerate(extra))
            text = text.replace('struct OwnedPin {', defs + '\nstruct OwnedPin {', 1)
            text = text.replace('inline constexpr OwnedPin OWNED_CORE_PINS[] = {', 'inline constexpr OwnedPin OWNED_CORE_PINS[] = {\n' +
                '\n'.join(f'{{{address:#x},geometry_pin_{i},sizeof(geometry_pin_{i})}},' for i, (address, blob) in enumerate(extra)), 1)
        if text != original_text: path.write_text(text, encoding='utf-8', newline='\n')
    qa_inputs = {path.resolve(): digest(path) for path in (output / 'semantic').rglob('*') if path.is_file()}
    common = [tool('clang++.exe'), '--target=aarch64-linux-android24', '--sysroot=' + str(LLVM.parent / 'sysroot'),
        '-std=c++17', '-O2', '-Wall', '-Wextra', '-Werror', '-fPIC', '-fvisibility=hidden', '-fvisibility-inlines-hidden']
    run([*common, '-fno-exceptions', '-fno-rtti', '-I' + str(native), '-MD', '-MF', output / 'monitor.d', '-c', native / 'anomaly_monitor_mod.cpp', '-o', output / 'monitor.o'])
    run([*common, '-fexceptions', '-I' + str(output / 'semantic/owned'), '-MD', '-MF', output / 'owned.d', '-c', output / 'semantic/owned/owned_pack_module.cpp', '-o', output / 'owned.o'])
    monitor_target = output / 'libakaineanomaly_monitor-QA-GEOMETRY-NO-FDE.so'
    link_trace = run([tool('clang++.exe'), '--target=aarch64-linux-android24', '-shared', '-static-libstdc++', '-Wl,--no-undefined', '-Wl,--strip-all', '-Wl,--trace',
        '-Wl,-Map=' + str(output / 'monitor.map'), '-Wl,-z,max-page-size=16384', output / 'monitor.o', output / 'owned.o', '-llog', '-ldl', '-o', monitor_target])
    local_objects = {(output / name).resolve(): digest(output / name) for name in ('monitor.o', 'owned.o')}
    sdk_resolved = {path.resolve(): pin for path, pin in sdk_inputs.items()}
    link_inputs = {}
    for line in link_trace.splitlines():
        name = line.strip().split('(', 1)[0]
        if not name: continue
        path = Path(name).resolve()
        if str(path) in link_inputs: continue
        expected = local_objects.get(path, sdk_resolved.get(path))
        require(expected and path.is_file() and digest(path) == expected, 'Unpinned actual linker input')
        link_inputs[str(path)] = expected
    require(set(local_objects) <= {Path(path) for path in link_inputs} and len(link_inputs) >= 5, 'Linker trace closure is incomplete')
    dependencies = []
    for unit in ('monitor.d', 'owned.d'):
        for path in helper.parse_deps((output / unit).read_text()):
            path = Path(path)
            if path.resolve().is_relative_to(output.resolve()):
                require(path.resolve() in qa_inputs and digest(path) == qa_inputs[path.resolve()], 'Unpinned QA compile input')
            else:
                role = 'android-sdk/' + path.relative_to(SDK).as_posix()
                require(role in pinned and digest(path) == pinned[role], 'Unpinned compiler dependency')
            dependencies.append(dict(unit=unit, path=str(path), sha256=digest(path)))
    baseline_meta = helper.Elf(MONITOR.read_bytes()).metadata(); monitor_meta = helper.Elf(monitor_target.read_bytes()).metadata()
    for name in ('exports', 'imports', 'needed', 'soname'): require(baseline_meta[name] == monitor_meta[name], 'Monitor dynamic interface differs: ' + name)
    for image in (candidate.metadata(), monitor_meta):
        require(image['all_loads_16k_compatible'] and image['bind_now'] and image['gnu_relro']
            and not any(image[name] for name in ('textrel', 'executable_stack', 'writable_executable_load')), 'ELF hardening differs')
    require(source_identities == {path: (path.stat().st_size, path.stat().st_mtime_ns, digest(path)) for path in source_identities}, 'Frozen diagnostic input changed')
    require(qa_inputs == {path.resolve(): digest(path) for path in (output / 'semantic').rglob('*') if path.is_file()}, 'QA source changed during compilation')
    require(all(digest(path) == pin for path, pin in sdk_inputs.items()), 'Frozen SDK input changed during compilation or linking')
    result = {'status': 'QA_GEOMETRY_CORE_MONITOR_BUILT_NOT_PACKAGED_STATIC_REVIEW_PENDING', 'diagnostic_only': True,
        'base_core_sha256': PINS[CORE], 'base_monitor_sha256': PINS[MONITOR], 'core': str(core_target), 'core_sha256': digest(core_target),
        'monitor': str(monitor_target), 'monitor_sha256': digest(monitor_target), 'hooks': hooks,
        'exact_changed_spans': [{'offset': hex(first), 'bytes': last - first} for first, last in sorted(changes)],
        'all_other_core_bytes_unchanged': True, 'gate_bytes': len(gate), 'gate_sha256': digest(output / 'gates.bin'),
        'RX_before': '0x1a7e5e4', 'RX_after': hex(end), 'exact_machine_state_cases': cases, 'changed_pin_arrays': changed_pins,
        'compiler_dependencies': dependencies, 'actual_linker_inputs': link_inputs, 'frozen_SDK_inputs_verified_before_after': len(sdk_inputs),
        'NO_FDE_INSIDE_PROBE_CAVE': True, 'exceptions_may_bypass_RET_invalidating_whole_window': True,
        'normal_release_source_profile_APK_loader_devices_or_network_modified': False, 'QA_emulator_only': True,
        'source_review_sha256': review_sha, 'preparation_sha256': digest(HERE / 'PREPARATION.json'), 'external_disk': disk}
    (output / 'BUILD_RECEIPT.json').write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8', newline='\n')
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=('prepare', 'build'))
    parser.add_argument('--output', type=Path)
    parser.add_argument('--review', type=Path)
    parser.add_argument('--review-sha256')
    args = parser.parse_args()
    if args.mode == 'prepare': result = prepare()
    else:
        if args.output is None or args.review is None or args.review_sha256 is None: parser.error('Build requires exact output and independent review binding')
        result = build(args.output, args.review, args.review_sha256)
    print(json.dumps({'status': result['status'], 'diagnostic_only': True}))
