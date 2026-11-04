"""Build the complete production 7.1 payload set from the original APKPure merge."""
from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path, PurePosixPath
import re
import shlex
import shutil
import subprocess
import zipfile

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
BASELINE = HERE.with_name('arcaea-7.0.255-arm64')
STOCK_SHA = '1290b99ef6ef9d15f1c26183147ae10c7878cf5bd0f52e2119172e8ac8fc45da'
CORE_ENTRY = 'lib/arm64-v8a/libcocos2dcpp.so'
PROVIDER_ENTRY = 'lib/arm64-v8a/libfmodProvider.so'
RUNTIME_MODULES = ('mod', 'packs', 'cli', 'skill', 'replay', 'menu')


def require(value, reason):
    if not value:
        raise ValueError(reason)


def digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def no_links(value):
    path = Path(value).absolute()
    require(not any(p.is_symlink() or p.exists() and getattr(p.stat(), 'st_file_attributes', 0) & 1024
                    for p in (path, *path.parents)), 'Build links and junctions are not allowed')
    return path.resolve()


def relative(value):
    path = PurePosixPath(value)
    require(path.as_posix() == value and not path.is_absolute() and '..' not in path.parts
            and '\\' not in value and ':' not in value, 'Unsafe source path')
    return Path(*path.parts)


def engine(name):
    spec = importlib.util.spec_from_file_location('akaine71_' + name, HERE / (name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def source_hashes():
    paths = [p for p in HERE.iterdir() if p.is_file() and p.suffix in ('.py', '.json', '.h', '.S')]
    lock = json.loads((HERE / 'source-inputs.json').read_bytes())
    require(lock.get('schema') == 'akaine.port71.source-inputs.v1' and len(lock['files']) == 49,
            'Complete reviewed baseline source inventory required')
    paths.extend(no_links(BASELINE / relative(row['source'])) for row in lock['files'])
    return {p.relative_to(ROOT).as_posix(): digest(p) for p in paths}


def verify_sources(expected):
    require(all(digest(no_links(ROOT / relative(name))) == value for name, value in expected.items()),
            'Build source changed during compilation')


def prepare_sources(output):
    """Reuse the locked current sources without duplicating them in the repository."""
    output = no_links(output)
    require(not output.exists() and not output.is_relative_to(ROOT), 'Fresh external source output required')
    lock = json.loads((HERE / 'source-inputs.json').read_bytes())
    require(lock.get('schema') == 'akaine.port71.source-inputs.v1' and len(lock['files']) == 49,
            'Complete reviewed baseline source inventory required')
    rows, names = [], set()
    for row in lock['files']:
        source = no_links(BASELINE / relative(row['source'])); target = relative(row['target'])
        require(target not in names and source.name != 'embedded_key.h' and source.is_file()
                and digest(source) == row['sha256'], 'Baseline source missing or changed: ' + row['source'])
        names.add(target); rows.append((source, target, row['sha256']))
    output.mkdir(parents=True)
    hashes = {}
    for source, target, expected in rows:
        destination = output / target; destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)
        require(digest(source) == digest(destination) == expected, 'Source changed during preparation')
        hashes[target.as_posix()] = expected
    (output / 'SOURCE_INPUTS.json').write_text(json.dumps(hashes, indent=2) + '\n', encoding='utf-8')
    return hashes


def run(arguments):
    try:
        result = subprocess.run(list(map(str, arguments)), capture_output=True, timeout=240)
    except (OSError, subprocess.TimeoutExpired):
        raise RuntimeError('Native compiler failed or timed out; diagnostics suppressed') from None
    if result.returncode:
        raise RuntimeError('Native compiler failed; diagnostics suppressed')
    return result.stdout


def compile_monitor(kit, llvm, output):
    output.mkdir()
    common = [llvm / 'clang++.exe', '--target=aarch64-linux-android24',
              '--sysroot=' + str(llvm.parent / 'sysroot'), '-std=c++17', '-O2', '-Wall', '-Wextra',
              '-Werror', '-fPIC', '-fvisibility=hidden', '-fvisibility-inlines-hidden']
    for name, source, includes, exceptions in (
        ('monitor', kit / 'semantic/native/anomaly_monitor_mod.cpp', [kit / 'semantic/native'], False),
        ('owned', kit / 'semantic/owned/owned_pack_module.cpp', [kit / 'semantic/owned'], True),
    ):
        run([*common, '-fexceptions' if exceptions else '-fno-exceptions',
             *([] if exceptions else ['-fno-rtti']), *('-I' + str(path) for path in includes),
             '-MMD', '-MF', output / (name + '.d'), '-c', source, '-o', output / (name + '.o')])
        dependencies = shlex.split((output / (name + '.d')).read_text().replace('\\\n', ' ').split(': ', 1)[1])
        require(all(no_links(path).is_relative_to(kit) for path in dependencies),
                'Compiler used a source outside the generated runtime')
    target = output / 'libakaineanomaly_monitor.so'
    run([llvm / 'clang++.exe', '--target=aarch64-linux-android24', '-shared', '-static-libstdc++',
         '-Wl,--no-undefined', '-Wl,--strip-all', '-Wl,-z,max-page-size=16384',
         output / 'monitor.o', output / 'owned.o', '-llog', '-ldl', '-o', target])
    return target


def build_loader(key_header, crypto, output, llvm):
    """Compile with an external operator key; never read or print its contents."""
    key_header, crypto, output, llvm = map(no_links, (key_header, crypto, output, llvm))
    source = no_links(BASELINE / 'native/akfc_loader.cpp')
    require(key_header.name == 'embedded_key.h' and key_header.is_file() and not key_header.is_relative_to(ROOT),
            'Regular external opaque key header required')
    require(not (source.parent / 'embedded_key.h').exists(), 'Source-local key would shadow the external reference')
    require(crypto.is_file() and not output.exists(), 'Static crypto and fresh loader output required')
    frozen = {p: digest(p) for p in (source, key_header, crypto)}
    output.parent.mkdir(parents=True, exist_ok=True)
    run([llvm / 'clang++.exe', '--target=aarch64-linux-android24', '-Wl,--no-undefined', '-Wall', '-Wextra', '-Werror',
         '-Wno-unused-function', '-Wno-unused-variable', '-Wno-unused-parameter', '-Wno-sign-compare',
         '-std=c++17', '-O2', '-shared', '-fPIC', '-fvisibility=hidden', '-fvisibility-inlines-hidden',
         '-static-libstdc++', '-Wl,--strip-all', '-I' + str(key_header.parent), '-MD', '-MF', output.with_suffix('.d'),
         crypto, source, '-llog', '-ldl', '-o', output])
    symbols = run([llvm / 'llvm-readelf.exe', '--dyn-syms', '--wide', output]).decode()
    dynamic = run([llvm / 'llvm-readelf.exe', '-d', output]).decode()
    require(all(name in symbols for name in ('Java_low_moe_AkfcLoader_installHooks', 'Java_low_moe_AkfcLoader_wipeDecrypted'))
            and 'Java_low_moe_AkfcLoader_decryptFile' not in symbols
            and not any(' UND ' in line and ('akfc_' in line or 'EVP_' in line) for line in symbols.splitlines())
            and 'libcrypto.so' not in dynamic and 'libc++_shared.so' not in dynamic,
            'Loader JNI/static-crypto contract differs')
    require(frozen == {p: digest(p) for p in frozen}, 'Loader input changed during compilation')
    return output


def runtime_sources(source, core, native_receipt, provider, songlist, output):
    pins = engine('pins').prepare(core, native_receipt, source, output / 'pins')
    require(pins['headers_generated'] and pins['pending'] == [] and pins['resolved_pin_count'] == 506
            and pins['header_count'] == 27 and len(pins['header_sha256']) == 27,
            'Complete 506 runtime guards and 27 headers required')
    native = json.loads(native_receipt.read_bytes())
    kit = output / 'runtime'
    adapted = engine('runtime').prepare(source, kit, authored_addresses=native['authored_addresses'], environment='production')
    require(adapted['unresolved_authored_references'] == [], 'Unresolved runtime address blocks compilation')
    for name, expected in pins['header_sha256'].items():
        source_pin = no_links(output / 'pins' / relative(name)); target = kit / relative(name)
        require(name.startswith('semantic/') and name.endswith('.h') and digest(source_pin) == expected,
                'Generated guard identity differs')
        target.parent.mkdir(parents=True, exist_ok=True); shutil.copyfile(source_pin, target)
    (kit / 'semantic/owned/assetset_capability.h').write_text(
        '#pragma once\ninline constexpr bool AKAINE_ASSETSET_VERIFIED = false;\n'
        'inline constexpr const char* AKAINE_ASSETSET_HEADER = "";\n', encoding='utf-8', newline='\n')
    songs = json.loads(songlist.read_bytes()).get('songs')
    require(isinstance(songs, list) and songs and all(isinstance(row, dict)
            and all(isinstance(row.get(key), str) and re.fullmatch('[A-Za-z0-9_.-]+', row[key]) for key in ('id', 'set'))
            for row in songs) and len({row['id'] for row in songs}) == len(songs), 'Unique safe song and album IDs required')
    rows = '\n'.join('        {' + json.dumps(row['id']) + ', ' + json.dumps(row['set']) + '},'
                     for row in sorted(songs, key=lambda row: row['id']))
    (kit / 'semantic/native/catalog_v3.h').write_text(
        '#pragma once\n#include <cstring>\nnamespace anomaly_monitor {\n'
        'inline const char* album_for_song(const char* id) {\n'
        '    struct Row { const char* id; const char* pack; };\n'
        '    static constexpr Row rows[] = {\n' + rows + '\n    };\n'
        '    if (id) for (const auto& row : rows) if (std::strcmp(id, row.id) == 0) return row.pack;\n'
        '    return "unknown";\n}\n}\n', encoding='utf-8', newline='\n')
    for name in ('sfx_bridge.h', 'sfx_cache_path.h'):
        shutil.copyfile(HERE / name, kit / 'semantic/native' / name)
    waves, flat = [], set()
    for song in songs:
        for item in song.get('additional_files', []):
            name = item.get('file_name', '')
            if not name.endswith('.wav'):
                continue
            identity = song['id'] + '_' + name
            require(re.fullmatch('[A-Za-z0-9_][A-Za-z0-9_.-]*', name) and '..' not in name
                    and re.fullmatch('[A-Za-z0-9_][A-Za-z0-9_.-]*', song['id']) and '..' not in song['id']
                    and len(identity) <= 255 and identity not in flat, 'Unsafe or colliding declared WAV cache name')
            flat.add(identity); waves.append((song['id'], name))
    require(waves, 'The matching native catalogue must declare the WAV samples')
    (kit / 'semantic/native/sfx_files.h').write_text(
        '#pragma once\ninline constexpr akaine_sfx71::WaveFile AKAINE_SFX_FILES[] = {\n'
        + ''.join('{' + json.dumps(song) + ',' + json.dumps(name) + '},\n' for song, name in sorted(waves))
        + '};\n', encoding='utf-8', newline='\n')
    (kit / 'semantic/native/sfx_provider_pins.h').write_text(
        engine('provider').runtime_header(provider.read_bytes()), encoding='utf-8', newline='\n')
    generated = {path.relative_to(kit).as_posix(): digest(path) for path in kit.rglob('*') if path.is_file()}
    require(all(generated.get(name) == expected for name, expected in pins['header_sha256'].items()),
            'Generated runtime guards changed')
    return kit, pins, generated, len(waves)


def build(stock, llvm, output, *, java, javac, jadx, d8, songlist):
    """Return eleven rebuilt payloads; signing and the operator-key loader stay with the caller."""
    stock, llvm, output, java, javac, jadx, d8, songlist = map(no_links,
        (stock, llvm, output, java, javac, jadx, d8, songlist))
    require(stock.is_file() and digest(stock) == STOCK_SHA, 'Exact original APKPure 7.1 merged APK required')
    require(not output.exists() and not output.is_relative_to(ROOT), 'Fresh external payload output required')
    sources = source_hashes(); frozen = {p: digest(p) for p in (stock, java, javac, jadx, d8, songlist)}
    profile = json.loads((HERE / 'production-profile.json').read_bytes())
    require(profile.get('environment') == 'production' and profile.get('package') == 'akai.arc.lmao'
            and profile.get('application_version') == '7.1.0' and profile.get('version_code') == 1209907,
            'Exact production 7.1 profile required')
    seals = json.loads((HERE / 'production-output-seals.json').read_bytes())['payload_sha256']
    output.mkdir(parents=True)
    source = output / 'sources'; prepare_sources(source)
    with zipfile.ZipFile(stock) as archive:
        core_raw, provider_raw = archive.read(CORE_ENTRY), archive.read(PROVIDER_ENTRY)
    core, native = engine('native').build(core_raw, llvm, output / 'native', profile,
        runtime_bindings={'reviewed_modules': list(RUNTIME_MODULES)})
    require(native['output_identity_sealed'] and digest(core) == seals[CORE_ENTRY], 'Production native output differs')
    provider, provider_receipt = engine('provider').build(provider_raw)
    provider_path = output / 'libfmodProvider.so'; provider_path.write_bytes(provider)
    require(digest(provider_path) == seals[PROVIDER_ENTRY], 'Production provider output differs')
    kit, pins, generated, wave_count = runtime_sources(source, core, output / 'native/BUILD_RECEIPT.json',
                                                      provider_path, songlist, output)
    monitor = compile_monitor(kit, llvm, output / 'monitor')
    require(all(digest(no_links(kit / relative(name))) == expected for name, expected in generated.items()),
            'Generated runtime source changed during compilation')
    managed = engine('managed')
    expected = {name: value for name, value in seals.items() if not name.startswith('lib/')}
    replacements, managed_receipt = managed.prepare(stock, java, javac, jadx, d8, source, output / 'managed',
        package='akai.arc.lmao', bundle_urls=(), expected_outputs=expected)
    replacements.update({CORE_ENTRY: core, PROVIDER_ENTRY: provider_path,
                         'lib/arm64-v8a/libakaineanomaly_monitor.so': monitor})
    require(frozen == {p: digest(p) for p in frozen}, 'Build input changed during compilation')
    verify_sources(sources)
    receipt = {'schema': 'akaine.production71.source-build.v1', 'status': 'PRODUCTION71_SOURCE_PAYLOADS_VERIFIED',
        'package': profile['package'], 'application_version': profile['application_version'],
        'source_sha256': sources, 'songlist_sha256': frozen[songlist],
        'payload_sha256': {name: digest(path) for name, path in replacements.items()},
        'generated_source_sha256': generated, 'native': native, 'managed': managed_receipt,
        'provider': provider_receipt, 'runtime_pins': {'pin_count': pins['pin_count'], 'resolved_pin_count': pins['resolved_pin_count'],
            'header_count': pins['header_count'], 'pending': pins['pending']},
        'declared_wav_samples': wave_count, 'assetset_capability_verified': False,
        'monitor_matches_reference_content': digest(monitor) == seals['lib/arm64-v8a/libakaineanomaly_monitor.so'],
        'retained_partial_cache_enabled': False, 'accepted_APK_or_final_library_used_as_input': False,
        'original_media_preserved_by_payload_set': True, 'device_or_server_actions': False}
    (output / 'BUILD_RECEIPT.json').write_text(json.dumps(receipt, indent=2) + '\n', encoding='utf-8')
    return replacements, receipt
