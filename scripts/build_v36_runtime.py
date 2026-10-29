"""Build the V36 native runtime from the verified V9 APK and public sources."""
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import shutil
import struct
from types import SimpleNamespace
import zipfile

import assetset_identity
import build_client_support as support
import build_dynamic_core as owned
import build_integrity_core as integrity
import build_news_core as news
import build_prod_rebase_core as baseline
import build_production_news_core as production
import build_reset_core as reset

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / 'patches/arcaea-7.0.255-arm64/runtime'
LAYOUT = RUNTIME / 'pin-layout.json'
R5_SHA = '7f3811cbe0308b709c9dcd4c72b6ffe18ee23454973fcb852a966ca5cf0c36c8'
CORE_SHA = '1097f9e03939ae0cd47fc958bbb95ed241f61cf1f44eb7c2ef71406ea3367bbe'


def require(value, message):
    if not value:
        raise ValueError(message)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


class Elf:
    """The section view needed by the existing guarded native compilers."""
    def __init__(self, raw):
        require(raw[:6] == b'\x7fELF\x02\x01', 'Little-endian ELF64 required')
        self.raw = raw
        offset = struct.unpack_from('<Q', raw, 40)[0]
        stride, count, names = struct.unpack_from('<HHH', raw, 58)
        require(stride == 64 and names < count and offset + count * stride <= len(raw), 'ELF section table differs')
        rows = [struct.unpack_from('<IIQQQQIIQQ', raw, offset + index * stride) for index in range(count)]
        strings = rows[names]
        table = raw[strings[4]:strings[4] + strings[5]]
        self.sections = []
        for row in rows:
            require(row[0] < len(table), 'ELF section name differs')
            name = table[row[0]:].split(b'\0', 1)[0].decode('ascii')
            self.sections.append(dict(name=name, type=row[1], flags=row[2], address=row[3], offset=row[4], size=row[5]))
        self.named = {row['name']: row for row in self.sections}

    def bytes(self, address, size):
        rows = [row for row in self.sections if row['type'] != 8 and row['address'] <= address
                and address + size <= row['address'] + row['size']]
        require(len(rows) == 1, 'Unique file-backed ELF section required')
        row = rows[0]
        start = row['offset'] + address - row['address']
        return self.raw[start:start + size]


class UnwindMap:
    def __init__(self, elf):
        self.elf = elf
        row = elf.named['.eh_frame_hdr']
        self.base = row['address']
        data = elf.bytes(self.base, row['size'])
        require(data[:4] == bytes((1, 0x1b, 3, 0x3b)), 'ELF unwind encoding differs')
        count = struct.unpack_from('<I', data, 8)[0]
        require(12 + count * 8 <= len(data), 'ELF unwind table exceeds section')
        self.rows = [(self.base + start, self.base + fde) for start, fde in struct.iter_unpack('<ii', data[12:12 + count * 8])]
        self.starts = [row[0] for row in self.rows]
        require(self.starts == sorted(self.starts), 'ELF unwind table must be ordered')

    def containing(self, address):
        from bisect import bisect_right
        index = bisect_right(self.starts, address) - 1
        require(index >= 0, 'Native function has no unwind entry')
        start, fde = self.rows[index]
        length, cie, relative, span = struct.unpack('<IIii', self.elf.bytes(fde, 16))
        require(length >= 12 and cie > 0 and span > 0 and fde + 8 + relative == start
                and start <= address < start + span, 'Native function unwind range differs')
        return {'start': hex(start), 'span': span}


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
    return owned.virtual_bytes(raw, address, size)


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
    require(layout.get('schema') == 'akaine.native-pin-layout.v1' and layout.get('core_sha256') == CORE_SHA,
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


def build(base_apk, kit, output, llvm, songlist):
    base_apk, kit, output, llvm = map(Path, (base_apk, kit, output, llvm))
    require(support.digest(base_apk) == baseline.PROD_APK_SHA, 'Verified production V9 APK required')
    with zipfile.ZipFile(base_apk) as archive:
        prod = archive.read(baseline.CORE_ENTRY)
    normalized, routes = baseline.normalize_routes(prod)
    layout = load_layout()
    catalogue, song_count = catalogue_header(songlist)
    disk = support.physical_output(output)
    output.mkdir(parents=True)
    for source in ('semantic/owned/owned_gates.S', 'semantic/owned/reset_gate.S', 'news/news_gates.S',
                   'integrity/download_success_size_gate.S', 'integrity/download_run_once_gate.S',
                   'integrity/child_order_gate.S'):
        require((kit / source).is_file() and not (kit / source).is_symlink(), 'Required hydrated runtime source missing')
    source = SimpleNamespace(Elf=Elf, elf=Elf(normalized))
    source.unwind = UnwindMap(source.elf)
    r5 = owned.build_core(kit, output / 'r5-core', llvm, source)
    r5_raw = r5.read_bytes()
    require(sha(r5_raw) == R5_SHA, 'Freshly compiled owned-pack core differs')
    reset_input = output / 'reset-input'
    owned_input = reset_input / 'semantic/owned/owned_core_pins.h'
    owned_input.parent.mkdir(parents=True)
    shutil.copy2(output / 'r5-core/owned_core_pins.h', owned_input)
    song_layout = next(header for header in layout['headers'] if header['path'] == 'semantic/song-v9/cli_song_pins.h')
    write_fresh(reset_input / 'semantic/song-v9/cli_song_pins.h', render_header(song_layout, r5_raw, validate=False))
    import capstone
    reader = SimpleNamespace(raw=r5_raw, SHA=sha(r5_raw), elf=Elf(r5_raw),
                             read=lambda address, size: owned.virtual_bytes(r5_raw, address, size),
                             decoder=capstone.Cs(capstone.CS_ARCH_ARM64, capstone.CS_MODE_ARM))
    reset_core, reset_pins, reset_proof = reset.build(kit / 'semantic/owned/reset_gate.S', reset_input,
        output / 'reset-core', llvm, reader)
    normal, normal_pins, integrity_proof = integrity.build(reset_core, reset_pins,
        kit / 'integrity/download_success_size_gate.S', kit / 'integrity/download_run_once_gate.S',
        kit / 'integrity/child_order_gate.S', output / 'integrity-core', llvm)
    accounting = baseline.account_output(prod, normal.read_bytes(),
        {name: (output / name).read_bytes() for name, _, _, _ in baseline.GATES})
    news_core, generated_pins, news_proof = news.build(normal, normal_pins, kit / 'news/news_gates.S',
        output / 'news-core', llvm)
    final, route_proof = production.production_routes(prod, news_core.read_bytes())
    require(sha(final) == CORE_SHA, 'Production V36 core identity differs')
    target = output / 'libcocos2dcpp.so'
    target.write_bytes(final)
    for header in layout['headers']:
        write_fresh(kit / safe_relative(header['path']), render_header(header, final))
    require((kit / 'semantic/song-v9/cli_song_pins.h').read_bytes() == (generated_pins / 'cli_song_pins.h').read_bytes(),
            'Derived song pin header differs from compiled-stage pin header')
    write_fresh(kit / 'semantic/owned/owned_core_pins.h', (generated_pins / 'owned_core_pins.h').read_text('utf-8'))
    write_fresh(kit / 'semantic/native/catalog_v3.h', catalogue)
    assets = assetset_identity.inspect_apk(base_apk, baseline.PROD_APK_SHA)
    write_fresh(kit / 'semantic/owned/assetset_capability.h', '#pragma once\n'
        'inline constexpr bool AKAINE_ASSETSET_VERIFIED = true;\n'
        'inline constexpr char AKAINE_ASSETSET_HEADER[] = "Akaine-Assets: ' + assets['assetset_sha256'] + '";\n')
    require(support.digest(base_apk) == baseline.PROD_APK_SHA, 'Source APK changed during build')
    receipt = dict(status='V36_NATIVE_CORE_BUILT_FROM_VERIFIED_APK_AND_PUBLIC_SOURCES',
        base_apk_sha256=baseline.PROD_APK_SHA, core_sha256=CORE_SHA, core=str(target),
        pin_headers=26, instruction_pins=sum(len(header['pins']) for header in layout['headers']),
        pin_layout_sha256=support.digest(LAYOUT), songlist_sha256=support.digest(Path(songlist)), song_count=song_count,
        assetset_sha256=assets['assetset_sha256'], assets=assets['asset_count'],
        route_normalization=routes, finite_native_accounting=accounting, reset=reset_proof,
        integrity=integrity_proof, news=news_proof, production_routes=route_proof,
        accepted_binary_used_as_compiler_input=False, private_kit_required=False, external_disk=disk,
        runtime_verified=False, device_or_server_actions=False)
    write_fresh(output / 'BUILD_RECEIPT.json', json.dumps(receipt, indent=2) + '\n')
    return target, generated_pins, receipt
