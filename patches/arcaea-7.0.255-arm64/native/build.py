"""One guarded native build: original APKPure core -> current V36 ARM64 core.

Uses one finite source patch plan and one authored assembly translation unit.
No old APK, accepted final SO, staging artifact or historical builder is input.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import struct
import subprocess
import shlex
import zipfile

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
PATCH = ROOT / 'patches/arcaea-7.0.255-arm64'
RUNTIME = PATCH / 'runtime'
PLAN = PATCH / 'native-plan.json'
CORE_ENTRY = 'lib/arm64-v8a/libcocos2dcpp.so'
STOCK_SHA = '3eaca4e6dabb3395f276f8915698d57675757d0df0970e716b23a3dc201c79be'
BASE_SHA = 'f2729d67166faa1fcee05601ea35d775548d3bfdc2f1a3d04777b082066b235d'
OUTPUT_SHA = '1097f9e03939ae0cd47fc958bbb95ed241f61cf1f44eb7c2ef71406ea3367bbe'
INSERT, INSERT_SIZE, RX_END = 0x1a7d4d0, 0x4000, 0x1a7e6a4
GATES = (
    ('.owned_gates', INSERT, 4012, 'cfa75e6f1a42f26d917541975c435885e74defee50a83627f5cf72e6b02f337c'),
    ('.reset_gate', 0x1a7e480, 192, '5b2dd72017a6b7c44503e492d6afcfbe0974c564d9fcc0c2a97bc05604f04f31'),
    ('.download_size_gate', 0x1a7e540, 64, '3b47951f4d2c79d033d35f77e8b1fac178145b43de6a856a389d6c80e2ea5957'),
    ('.download_run_once_gate', 0x1a7e580, 28, 'd545911c8e2f47548fe73eaa3ebeb7666847e78d13c07647278f63c7ca5bf121'),
    ('.child_order_gate', 0x1a7e5a0, 68, '5187759372d5ec26dd77caa6160f0e1465eafe72a8705b635adbdc815bf4362e'),
    ('.news_gates', 0x1a7e5f0, 180, '255c74ff3d699de4fc9bf8fc8fcdba043ef73e50941fdc1a4279a1b061b1a841'),
)
SYMBOLS = {
    'owned_mailbox': 0x1c031c0, 'native_constructor_continue': 0x13f24c4,
    'native_reset_continue': 0x17840cc, 'native_append_continue': 0x1784124,
    'native_reserved_continue': 0x1716a60, 'native_finish_continue': 0x17842e4,
    'native_song_member_continue': 0x10a1de0, 'native_id_member_missing': 0x1a55300,
    'native_id_member_owned': 0x1a5559c, 'native_string_equal': 0x18910e8,
    'native_header_continue': 0x11aa890, 'reset_call_return': 0x1246c34,
    'native_persistence_tail': 0x181a9f4, 'native_refresh_continue': 0x181a81c,
    'native_fileutils_singleton': 0xb99da4, 'native_download_digest_failure': 0x107d8d0,
    'native_download_skiphash_dispatch': 0x107d804, 'native_download_run_body': 0x17c9f14,
    'native_child_sort': 0x986f60, 'native_news_sort': 0xac15c8, 'native_news_resume': 0x19f69b0,
}
HOOKS = (
    (0x13f24c0, 'fd7bbfa9', '042c1a14'), (0x17840b4, '684641f9', '5fe50b14'),
    (0x1784110, '684641f9', 'a6e50b14'), (0x1716a5c, 'ff4302d1', 'b49b0d14'),
    (0x17842e0, '685641f9', '44e60b14'), (0xf2bed8, 'ff4300d1', '9f472d14'),
    (0x10a1c9c, '684641f9', '98702714'), (0x1a55208, '684641f9', 'aaa30014'),
    (0x11aa88c, '818a48a9', 'a34e2314'), (0x181a818, 'e00e00b4', '1a8f0914'),
    (0x107d800, '08c34139', '50032814'), (0x13e50dc, '152440f9', '0e000014'),
    (0x17c9f10, 'ff8303d1', '9cd10a14'), (0x9ada6c, '3d65ff97', 'cd424394'),
)


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def file_sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def run(arguments):
    try:
        result = subprocess.run(list(map(str, arguments)), capture_output=True, timeout=180)
    except (OSError, subprocess.TimeoutExpired):
        raise RuntimeError('Native build tool failed; diagnostics suppressed') from None
    if result.returncode:
        raise RuntimeError('Native build tool failed: ' + Path(arguments[0]).name)
    return result.stdout


def branch(source, destination, *, link=False):
    displacement = destination - source
    require(displacement % 4 == 0 and -(1 << 27) <= displacement < (1 << 27), 'Branch range/alignment differs')
    return struct.pack('<I', (0x94000000 if link else 0x14000000) | ((displacement // 4) & 0x3ffffff))


def file_offset(data, address, size):
    require(data[:6] == b'\x7fELF\x02\x01' and struct.unpack_from('<H', data, 18)[0] == 183,
            'Little-endian AArch64 ELF64 required')
    at = struct.unpack_from('<Q', data, 32)[0]
    stride, count = struct.unpack_from('<HH', data, 54)
    require(stride == 56 and at + count * stride <= len(data), 'ELF program table differs')
    matches = []
    for index in range(count):
        row = struct.unpack_from('<IIQQQQQQ', data, at + index * stride)
        if row[0] == 1 and row[3] <= address and address + size <= row[3] + row[5]:
            matches.append(row[2] + address - row[3])
    require(len(matches) == 1 and matches[0] + size <= len(data), 'Unique complete file-backed native span required')
    return matches[0]


def apply_stock_plan(stock, plan_path=PLAN):
    require(sha(stock) == STOCK_SHA, 'Exact APKPure 7.0.255 arm64 core required')
    plan = json.loads(Path(plan_path).read_bytes())
    rows = [row for row in plan['binary_patches'] if row['archive_path'] == CORE_ENTRY]
    require(len(rows) == 1 and rows[0]['source_sha256'] == STOCK_SHA
            and rows[0]['output_sha256'] == BASE_SHA, 'Current upstream native plan required')
    result, occupied = bytearray(stock), set()
    for row in rows[0]['operations']:
        offset = row['offset']
        before, after = bytes.fromhex(row['before']), bytes.fromhex(row['after'])
        require(type(offset) is int and offset >= 0 and before and len(before) == len(after)
                and offset + len(before) <= len(stock), 'Invalid guarded native operation')
        positions = set(range(offset, offset + len(before)))
        require(not occupied.intersection(positions), 'Overlapping native operations')
        occupied.update(positions)
        require(stock[offset:offset + len(before)] == before, 'Native preimage guard differs: ' + row['label'])
        result[offset:offset + len(after)] = after
    require(sha(result) == BASE_SHA and len(result) == len(stock), 'Guarded native compatibility base differs')
    return bytes(result), len(rows[0]['operations'])


def compile_gates(llvm, source, output):
    before = sha(source.read_bytes())
    run([llvm / 'clang.exe', '--target=aarch64-linux-android24', '-c', source, '-o', output / 'gates.o'])
    run([llvm / 'ld.lld.exe', '--entry=owned_constructor_gate',
         *[f'--section-start={name}={address:#x}' for name, address, unused, unused_sha in GATES],
         *[f'--defsym={name}={value:#x}' for name, value in SYMBOLS.items()],
         output / 'gates.o', '-o', output / 'gates.elf'])
    result = {}
    for section, address, size, expected in GATES:
        path = output / (section.removeprefix('.') + '.bin')
        run([llvm / 'llvm-objcopy.exe', '-O', 'binary', '--only-section=' + section, output / 'gates.elf', path])
        data = path.read_bytes()
        require(len(data) == size and sha(data) == expected, 'Compiled gate differs: ' + section)
        result[section] = data
    require(before == sha(source.read_bytes()), 'Assembly source changed during build')
    return result, before


def extend_elf(base, gates):
    require(sha(base) == BASE_SHA, 'Guarded native base required')
    insertion = bytearray(INSERT_SIZE)
    occupied = set()
    for name, address, size, expected in GATES:
        data = gates[name]
        require(len(data) == size and sha(data) == expected and INSERT <= address
                and address + size <= INSERT + INSERT_SIZE, 'Compiled gate section guard differs')
        positions = set(range(address, address + size))
        require(not occupied.intersection(positions), 'Compiled gate sections overlap')
        occupied.update(positions)
        insertion[address - INSERT:address - INSERT + size] = data
    result = bytearray(base[:INSERT] + insertion + base[INSERT:])
    phoff = struct.unpack_from('<Q', base, 32)[0]
    phsize, phcount = struct.unpack_from('<HH', base, 54)
    require(phsize == 56, 'Native program-header stride differs')
    rx_count = bss_count = 0
    metadata = []
    for index in range(phcount):
        at = phoff + index * phsize
        row = struct.unpack_from('<IIQQQQQQ', base, at)
        if row[2] >= INSERT and row[5]:
            struct.pack_into('<Q', result, at + 8, row[2] + INSERT_SIZE)
            metadata.append({'offset': at + 8, 'bytes': 8, 'reason': 'Move file-backed program data after inserted gate space'})
        if row[0] == 1 and row[1] == 5 and row[3] == 0:
            require(row[2] == 0 and row[5] == row[6] == INSERT, 'Original executable segment layout differs')
            struct.pack_into('<QQ', result, at + 32, RX_END, RX_END)
            rx_count += 1
            metadata.append({'offset': at + 32, 'bytes': 16, 'reason': 'Include compiled native gates in executable segment'})
        if row[0] == 1 and row[3] == 0x1ba4920:
            require(row[6] == 0x5e8a0, 'Original runtime mailbox segment differs')
            struct.pack_into('<Q', result, at + 40, 0x5e920)
            bss_count += 1
            metadata.append({'offset': at + 40, 'bytes': 8, 'reason': 'Extend zero-initialized native runtime mailbox'})
    require(rx_count == bss_count == 1, 'Unique executable and mailbox segments required')
    shoff = struct.unpack_from('<Q', base, 40)[0]
    shsize, shcount = struct.unpack_from('<HH', base, 58)
    require(shsize == 64 and shoff >= INSERT and shoff + shcount * shsize <= len(base), 'Native section table differs')
    struct.pack_into('<Q', result, 40, shoff + INSERT_SIZE)
    metadata.append({'offset': 40, 'bytes': 8, 'reason': 'Move section-table file offset'})
    bss_sections = 0
    for index in range(shcount):
        old_at, new_at = shoff + index * shsize, shoff + INSERT_SIZE + index * shsize
        row = struct.unpack_from('<IIQQQQIIQQ', base, old_at)
        if row[4] >= INSERT:
            struct.pack_into('<Q', result, new_at + 24, row[4] + INSERT_SIZE)
            metadata.append({'offset': new_at + 24, 'bytes': 8, 'reason': 'Move section file offset after inserted gate space'})
        if row[1] == 8 and row[3] == 0x1be49d0:
            require(row[5] == 0x1e770, 'Native BSS section differs')
            struct.pack_into('<Q', result, new_at + 32, 0x1e870)
            bss_sections += 1
            metadata.append({'offset': new_at + 32, 'bytes': 8, 'reason': 'Cover BSS tail gap and owned runtime mailbox'})
    require(bss_sections == 1, 'Unique runtime BSS section required')
    hooks = [*HOOKS,
        (0x19f69a4, '092bc397', branch(0x19f69a4, 0x1a7e5f0, link=True).hex()),
        (0x19f69ac, '9bce41f9', branch(0x19f69ac, 0x1a7e630).hex())]
    for address, before, after in hooks:
        at = file_offset(base, address, 4)
        require(at < INSERT and base[at:at + 4] == bytes.fromhex(before), 'Native hook preimage differs')
        result[at:at + 4] = bytes.fromhex(after)
    require(len(result) == len(base) + INSERT_SIZE and sha(result) == OUTPUT_SHA, 'Complete V36 native source output differs')
    return bytes(result), metadata, hooks


def owned_header(raw, layout_path):
    layout = json.loads(Path(layout_path).read_bytes())
    if 'owned_header' in layout:
        layout = layout['owned_header']
    require(layout['path'] == 'semantic/owned/owned_core_pins.h' and len(layout['pins']) == 31, 'Current owned native pin layout required')
    text = '\n'.join(layout['template']) + '\n'
    for row in layout['pins']:
        name, size = row['symbol'], row['bytes']
        require(re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', name) and type(size) is int and size > 0, 'Invalid owned pin')
        at = file_offset(raw, int(row['address'], 16), size)
        data = raw[at:at + size]
        token = '@@' + name + '@@'
        require(sha(data) == row['sha256'] and text.count(token) == 1, 'Owned native pin guard differs')
        text = text.replace(token, ','.join(hex(value) for value in data))
    require('@@' not in text and sha(text.encode()) == layout['header_sha256'], 'Generated owned header differs')
    return text


def build_native(stock_core_bytes, llvm, output, *, plan=PLAN, assembly=PATCH / 'native/v36_gates.S',
                 pin_layout=RUNTIME / 'pin-layout.json'):
    output, llvm, assembly = Path(output), Path(llvm), Path(assembly)
    require(not output.exists() and not output.is_symlink(), 'Fresh native output required')
    for parent in output.absolute().parents:
        require(not parent.is_symlink() and not (parent.exists() and getattr(parent.stat(), 'st_file_attributes', 0) & 1024),
                'Native output junction/symlink rejected')
    inputs = {Path(path): sha(Path(path).read_bytes()) for path in (plan, assembly, pin_layout)}
    base, plan_operations = apply_stock_plan(stock_core_bytes, plan)
    output.mkdir(parents=True)
    gates, source_sha = compile_gates(llvm, assembly, output)
    raw, metadata, hooks = extend_elf(base, gates)
    target = output / 'libcocos2dcpp.so'
    target.write_bytes(raw)
    header = output / 'owned_core_pins.h'
    header.write_text(owned_header(raw, pin_layout), encoding='utf-8', newline='\n')
    require(inputs == {path: sha(path.read_bytes()) for path in inputs}, 'Native build source changed during compilation')
    receipt = {'status': 'STOCK_APKPURE_TO_V36_NATIVE_SOURCE_BUILD_PASS',
        'stock_core_sha256': STOCK_SHA, 'compatibility_base_sha256': BASE_SHA, 'native_core_sha256': sha(raw),
        'stock_bytes': len(stock_core_bytes), 'native_bytes': len(raw), 'guarded_native_plan_operations': plan_operations,
        'native_plan_sha256': inputs[Path(plan)], 'assembly_sha256': source_sha,
        'assembly_translation_units': 1, 'compiled_sections': [{'section': name, 'address': hex(address), 'bytes': size, 'sha256': expected}
            for name, address, size, expected in GATES], 'elf_metadata_changes': metadata,
        'native_instruction_hooks': [{'address': hex(address), 'before': before, 'after': after} for address, before, after in hooks],
        'owned_pin_header_sha256': sha(header.read_bytes()), 'owned_runtime_pins': 31,
        'V9_APK_or_final_library_used_as_input': False, 'device_or_server_actions': False, 'runtime_accepted': False}
    (output / 'BUILD_RECEIPT.json').write_text(json.dumps(receipt, indent=2) + '\n', encoding='utf-8')
    return target, header, receipt

LAYOUT = RUNTIME / 'pin-layout.json'
def safe_relative(value):
    path = PurePosixPath(value)
    require(path.as_posix() == value and not path.is_absolute() and '..' not in path.parts
            and '\\' not in value and ':' not in value and value.startswith('semantic/') and value.endswith('.h'),
            'Unsafe generated header path')
    return path


def read_pin(raw, pin):
    size = pin['bytes']
    require(type(size) is int and 0 < size <= len(raw), 'Invalid native pin size')
    if 'file_offset' in pin:
        offset = pin['file_offset']
        require(type(offset) is int and offset >= 0 and offset + size <= len(raw), 'Invalid native pin offset')
        return raw[offset:offset + size]
    address = int(pin['address'], 16)
    at = file_offset(raw, address, size)
    return raw[at:at + size]


def render_header(header, raw, *, validate=True):
    safe_relative(header['path'])
    text = '\n'.join(header['template']) + '\n'
    seen = set()
    for pin in header['pins']:
        name = pin['symbol']
        require(re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', name) and name not in seen, 'Invalid or duplicate pin symbol')
        seen.add(name)
        token = '@@' + name + '@@'
        require(text.count(token) == 1, 'Unique native pin placeholder required')
        data = read_pin(raw, pin)
        require(not validate or sha(data) == pin['sha256'], 'Native pin byte guard differs')
        text = text.replace(token, ','.join(hex(value) for value in data))
    require('@@' not in text, 'Unresolved native pin placeholder')
    return text


def load_layout():
    layout = json.loads(LAYOUT.read_bytes())
    require(layout.get('schema') == 'akaine.native-pin-layout.v1' and layout.get('core_sha256') == OUTPUT_SHA,
            'V36 native pin layout required')
    paths = [str(safe_relative(header['path'])) for header in layout['headers']]
    require(len(paths) == len(set(paths)) == 26, 'Exactly 26 unique native header layouts required')
    return layout


def catalogue_header(path):
    raw = Path(path).read_bytes()
    require(len(raw) <= 32 * 1024 * 1024, 'Song catalogue exceeds supported size')
    document = json.loads(raw.decode('utf-8-sig'))
    songs = document.get('songs') if isinstance(document, dict) else None
    require(isinstance(songs, list) and 0 < len(songs) <= 100000, 'Nonempty song catalogue required')
    pairs = {}
    for song in songs:
        require(isinstance(song, dict), 'Invalid song catalogue row')
        identity, pack = song.get('id'), song.get('set')
        require(all(isinstance(value, str) and value and len(value.encode('utf-8')) <= 512
                    and not any(ord(char) < 32 or ord(char) == 127 for char in value) for value in (identity, pack)),
                'Song id and set must be bounded UTF-8 strings')
        require(identity not in pairs, 'Duplicate song id in catalogue')
        pairs[identity] = pack
    lines = ['#pragma once', '#include <string.h>', 'namespace {',
             'struct SongAlbum { const char* song; const char* album; };', 'static constexpr SongAlbum SONG_ALBUMS[] = {']
    lines += ['{' + json.dumps(identity, ensure_ascii=False) + ',' + json.dumps(pairs[identity], ensure_ascii=False) + '},'
              for identity in sorted(pairs)]
    lines += ['};', 'inline const char* album_for_song(const char* song) {',
              'for (const auto& row : SONG_ALBUMS) if (!strcmp(row.song, song)) return row.album;', 'return "unknown";', '}', '}']
    return '\n'.join(lines) + '\n', len(pairs)


def write_fresh(path, text):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x', encoding='utf-8', newline='\n') as stream:
        stream.write(text)


def build_runtime(stock_apk, kit, output, llvm, songlist, asset_overlays):
    """Build the current core and derive runtime guards from its actual bytes."""
    stock_apk, kit, output = map(Path, (stock_apk, kit, output))
    before = file_sha(stock_apk)
    with zipfile.ZipFile(stock_apk) as archive:
        stock = archive.read(CORE_ENTRY)
    core, owned, receipt = build_native(stock, llvm, output)
    final = core.read_bytes()
    layout = load_layout()
    for header in layout['headers']:
        write_fresh(kit / safe_relative(header['path']), render_header(header, final))
    write_fresh(kit / 'semantic/owned/owned_core_pins.h', owned.read_text('utf-8'))
    catalogue, count = catalogue_header(songlist)
    write_fresh(kit / 'semantic/native/catalog_v3.h', catalogue)
    assets = inspect_assets(stock_apk)
    rows = {row['path']: row for row in assets['assets']}
    for name, path in asset_overlays.items():
        require(name.startswith('assets/'), 'Only asset overlays affect asset identity')
        relative = name.removeprefix('assets/')
        path = Path(path)
        rows[relative] = {'path': relative, 'bytes': path.stat().st_size, 'sha256': file_sha(path)}
    assets['assetset_sha256'] = canonical_digest(list(rows.values()))
    assets['asset_count'] = len(rows)
    write_fresh(kit / 'semantic/owned/assetset_capability.h', '#pragma once\n'
        'inline constexpr bool AKAINE_ASSETSET_VERIFIED = true;\n'
        'inline constexpr char AKAINE_ASSETSET_HEADER[] = "Akaine-Assets: ' + assets['assetset_sha256'] + '";\n')
    require(file_sha(stock_apk) == before, 'Stock APK changed during native build')
    receipt.update(pin_headers=len(layout['headers']), song_count=count,
                   assets=assets['asset_count'], assetset_sha256=assets['assetset_sha256'])
    return core, receipt



ASSET_SCHEMA = 'akaine.apk-assets.v1'
DOMAIN = ASSET_SCHEMA.encode('ascii') + b'\0'

def canonical_digest(rows):
    result = hashlib.sha256(DOMAIN)
    seen = set()
    for row in sorted(rows, key=lambda row: row['path'].encode('utf-8')):
        name = row['path']
        path = PurePosixPath(name)
        if (not name or name == '.' or path.is_absolute() or path.as_posix() != name or '\\' in name or ':' in name or '\0' in name
                or '..' in path.parts or name in seen or type(row['bytes']) is not int or not 0 <= row['bytes'] <= 0xffffffffffffffff):
            raise ValueError('Unsafe or duplicate APK asset identity row')
        digest = row['sha256']
        if not isinstance(digest, str) or len(digest) != 64 or any(value not in '0123456789abcdef' for value in digest):
            raise ValueError('Asset SHA256 must be exact lowercase hexadecimal')
        seen.add(name)
        encoded = name.encode('utf-8')
        result.update(struct.pack('<I', len(encoded)))
        result.update(encoded)
        result.update(struct.pack('<Q', row['bytes']))
        result.update(bytes.fromhex(digest))
    if not seen:
        raise ValueError('APK asset set is empty')
    return result.hexdigest()


def inspect_assets(path, expected_apk_sha=None):
    path = Path(path)
    before = path.stat()
    if path.is_symlink() or not path.is_file():
        raise ValueError('Regular APK required')
    apk_sha = file_sha(path)
    if expected_apk_sha and apk_sha != expected_apk_sha:
        raise ValueError('Source APK hash differs')
    rows = []
    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()
        if len(names) != len(set(names)):
            raise ValueError('Duplicate APK ZIP member')
        for item in archive.infolist():
            if not item.filename.startswith('assets/') or item.is_dir():
                continue
            with archive.open(item) as stream:
                digest = hashlib.file_digest(stream, 'sha256').hexdigest()
            rows.append({'path': item.filename.removeprefix('assets/'), 'bytes': item.file_size, 'sha256': digest})
    result = canonical_digest(rows)
    after = path.stat()
    if (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) != (
            after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns):
        raise ValueError('APK changed while asset identity was read')
    return {'schema': ASSET_SCHEMA, 'apk': str(path.resolve()), 'apk_sha256': apk_sha, 'assetset_sha256': result,
            'asset_count': len(rows), 'asset_bytes': sum(row['bytes'] for row in rows),
            'assets': sorted(rows, key=lambda row: row['path'].encode('utf-8'))}



def compile_monitor(kit, llvm, output):
    output.mkdir()
    common = [llvm / "clang++.exe", "--target=aarch64-linux-android24",
              "--sysroot=" + str(llvm.parent / "sysroot"), "-std=c++17", "-O2", "-Wall", "-Wextra",
              "-Werror", "-fPIC", "-fvisibility=hidden", "-fvisibility-inlines-hidden"]
    for name, source, includes, exceptions in (
        ("monitor", kit / "semantic/native/anomaly_monitor_mod.cpp", [kit / "semantic/native"], False),
        ("owned", kit / "semantic/owned/owned_pack_module.cpp", [kit / "semantic/owned"], True),
    ):
        run([*common, "-fexceptions" if exceptions else "-fno-exceptions",
                   *([] if exceptions else ["-fno-rtti"]), *("-I" + str(path) for path in includes),
                   "-MMD", "-MF", output / (name + ".d"), "-c", source, "-o", output / (name + ".o")])
        dependencies = shlex.split((output / (name + ".d")).read_text().replace("\\\n", " ").split(": ", 1)[1])
        for value in dependencies:
            Path(value).resolve().relative_to(kit.resolve())
    target = output / "libakaineanomaly_monitor.so"
    run([llvm / "clang++.exe", "--target=aarch64-linux-android24", "-shared", "-static-libstdc++",
               "-Wl,--no-undefined", "-Wl,--strip-all", "-Wl,-z,max-page-size=16384",
               output / "monitor.o", output / "owned.o", "-llog", "-ldl", "-o", target])
    return target


def verify_loader(loader, llvm):
    symbols = run([llvm / "llvm-readelf.exe", "--dyn-syms", "--wide", loader]).decode()
    dynamic = run([llvm / "llvm-readelf.exe", "-d", loader]).decode()
    if (any(name not in symbols for name in ("Java_low_moe_AkfcLoader_installHooks", "Java_low_moe_AkfcLoader_wipeDecrypted"))
            or "Java_low_moe_AkfcLoader_decryptFile" in symbols
            or any(" UND " in line and ("akfc_" in line or "EVP_" in line) for line in symbols.splitlines())
            or "libcrypto.so" in dynamic or "libc++_shared.so" in dynamic):
        raise ValueError("Loader JNI/static-crypto contract differs")


def build_loader(key_header, crypto, output, llvm):
    """Compile the operator's loader without reading or logging the opaque key."""
    key_header, crypto, output, llvm = map(Path, (key_header, crypto, output, llvm))
    source = PATCH / 'native/akfc_loader.cpp'
    require(key_header.name == 'embedded_key.h' and key_header.is_file()
            and not key_header.is_symlink(), 'Regular external opaque key header required')
    try:
        key_header.resolve().relative_to(ROOT.resolve())
    except ValueError:
        pass
    else:
        raise ValueError('Opaque key header must remain outside the repository')
    require(not (source.parent / 'embedded_key.h').exists(), 'Source-local key header would shadow the external reference')
    require(not output.exists(), 'Fresh loader output required')
    output.parent.mkdir(parents=True, exist_ok=True)
    run([llvm / 'clang++.exe', '--target=aarch64-linux-android24', '-Wl,--no-undefined', '-Wall', '-Wextra', '-Werror',
         '-Wno-unused-function', '-Wno-unused-variable', '-Wno-unused-parameter', '-Wno-sign-compare',
         '-std=c++17', '-O2', '-shared', '-fPIC', '-fvisibility=hidden', '-fvisibility-inlines-hidden',
         '-static-libstdc++', '-Wl,--strip-all', '-I' + str(key_header.parent), '-MD', '-MF', output.with_suffix('.d'),
         crypto, source, '-llog', '-ldl', '-o', output])
    verify_loader(output, llvm)
    return output
