"""Rebuild accepted staging core patches from the authentic production V9 APK."""
import hashlib
import json
from pathlib import Path
import struct
from types import SimpleNamespace
import zipfile

import build_dynamic_core
import build_integrity_core
import build_release_profile as shared
import build_reset_core

PROD_APK_SHA = 'f14c5ab0871440dec7ecf2107d32d6e2cad745abc82047d03b49db9dbac3f545'
PROD_CORE_SHA = 'f2729d67166faa1fcee05601ea35d775548d3bfdc2f1a3d04777b082066b235d'
STAGING_INPUT_SHA = 'aba3463bcb06ca5567c1190009c2ae1f9b7ddf56d1c1503f8d5055980a1f2c1b'
FINAL_SHA = '299f271b3b0bb8a656ba02be6fd6327f90b1a0fe2fe11d1e670ae51ccfdae42d'
CORE_ENTRY = 'lib/arm64-v8a/libcocos2dcpp.so'
INSERT, INSERT_SIZE, RX_END = 0x1a7d4d0, 0x4000, 0x1a7e5e4
ROUTES = (
    (0x782a74, 37, 'ff4e64f4f9796b2b88bff4c3f282f43183bdbcaa39aae26775d8c931820b71f1',
     b'https://auth.akai.id.vn/t/auth/login\0'),
    (0x782ab0, 56, '2afec8d0c5b85116b7d42b53fcaae987484e6bc70440f3040c026fe7830ef035',
     b'https://arcapi-v3.akai.id.vn/t/compose/aggregate?calls=\0'),
    (0x782afc, 51, '84b1823684a24d861834130f6d57c18d31a4c618de38f1a0d3b75f17bdb5b115',
     b'https://arcapi-v3.akai.id.vn/t/game/content_bundle\0'),
    (0x1ba600d, 2, '77be4cad7a432e47f43ad898bb9b1e83b888a988432ad76c473f870ab22c05c2',
     bytes.fromhex('29aa')),
)
# Exact accepted instruction preimages and outputs; all other original bytes survive.
HOOKS = (
    (0x13f24c0, 'fd7bbfa9', '042c1a14'), (0x17840b4, '684641f9', '5fe50b14'),
    (0x1784110, '684641f9', 'a6e50b14'), (0x1716a5c, 'ff4302d1', 'b49b0d14'),
    (0x17842e0, '685641f9', '44e60b14'), (0xf2bed8, 'ff4300d1', '9f472d14'),
    (0x10a1c9c, '684641f9', '98702714'), (0x1a55208, '684641f9', 'aaa30014'),
    (0x11aa88c, '818a48a9', 'a34e2314'), (0x181a818, 'e00e00b4', '1a8f0914'),
    (0x107d800, '08c34139', '50032814'), (0x13e50dc, '152440f9', '0e000014'),
    (0x17c9f10, 'ff8303d1', '9cd10a14'), (0x9ada6c, '3d65ff97', 'cd424394'),
)
GATES = (
    ('r5-core/gates.bin', INSERT, 4012, 'cfa75e6f1a42f26d917541975c435885e74defee50a83627f5cf72e6b02f337c'),
    ('reset-core/gate.bin', 0x1a7e480, 192, '5b2dd72017a6b7c44503e492d6afcfbe0974c564d9fcc0c2a97bc05604f04f31'),
    ('integrity-core/gate.bin', 0x1a7e540, 64, '3b47951f4d2c79d033d35f77e8b1fac178145b43de6a856a389d6c80e2ea5957'),
    ('integrity-core/run-gate.bin', 0x1a7e580, 28, 'd545911c8e2f47548fe73eaa3ebeb7666847e78d13c07647278f63c7ca5bf121'),
    ('integrity-core/child-order-gate.bin', 0x1a7e5a0, 68, '5187759372d5ec26dd77caa6160f0e1465eafe72a8705b635adbdc815bf4362e'),
)


def require(value, reason):
    if not value:
        raise ValueError(reason)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def file_offset(raw, address, size):
    phoff = struct.unpack_from('<Q', raw, 32)[0]
    stride, count = struct.unpack_from('<HH', raw, 54)
    rows = [struct.unpack_from('<IIQQQQQQ', raw, phoff + i * stride) for i in range(count)]
    matches = [row[2] + address - row[3] for row in rows
               if row[0] == 1 and row[3] <= address and address + size <= row[3] + row[5]]
    require(len(matches) == 1, 'Unique complete file-backed PT_LOAD span required')
    return matches[0]


def normalize_routes(prod):
    require(sha(prod) == PROD_CORE_SHA, 'Authentic production V9 core required')
    result = bytearray(prod)
    rows, allowed = [], set()
    for address, size, before_sha, replacement in ROUTES:
        at = file_offset(prod, address, size)
        before = prod[at:at + size]
        require(len(replacement) == size and sha(before) == before_sha, 'Production route preimage differs')
        result[at:at + size] = replacement
        allowed.update(range(at, at + size))
        rows.append({'runtime_VA': hex(address), 'prod_file_offset': hex(at), 'bytes': size,
                     'before_sha256': before_sha, 'after_sha256': sha(replacement),
                     'changed_bytes': sum(a != b for a, b in zip(before, replacement))})
    changed = {i for i, (a, b) in enumerate(zip(prod, result)) if a != b}
    require(len(result) == len(prod) and len(changed) == 61 and changed <= allowed
            and sha(result) == STAGING_INPUT_SHA, 'Finite production-to-staging route normalization differs')
    return bytes(result), rows


def account_output(prod, candidate, gates):
    """Reconstruct every final byte from prod plus declared routes/gates/ELF edits."""
    normalized, routes = normalize_routes(prod)
    require(len(candidate) == len(prod) + INSERT_SIZE, 'Unexpected output length')
    insertion = bytearray(INSERT_SIZE)
    gate_rows = []
    for name, address, size, expected in GATES:
        blob = gates[name]
        require(len(blob) == size and sha(blob) == expected, 'Authored compiled gate identity differs')
        insertion[address - INSERT:address - INSERT + size] = blob
        gate_rows.append({'name': name, 'RVA': hex(address), 'bytes': size, 'sha256': expected})
    result = bytearray(normalized[:INSERT] + insertion + normalized[INSERT:])
    phoff = struct.unpack_from('<Q', prod, 32)[0]
    phsize, phcount = struct.unpack_from('<HH', prod, 54)
    metadata = []
    for i in range(phcount):
        at = phoff + i * phsize
        row = struct.unpack_from('<IIQQQQQQ', prod, at)
        if row[2] >= INSERT and row[5]:
            struct.pack_into('<Q', result, at + 8, row[2] + INSERT_SIZE)
            metadata.append({'offset': hex(at + 8), 'bytes': 8, 'reason': 'Shift file-backed program offset'})
        if row[0] == 1 and row[1] == 5 and row[3] == 0:
            require(row[2] == 0 and row[5] == row[6] == INSERT, 'Production RX layout differs')
            struct.pack_into('<QQ', result, at + 32, RX_END, RX_END)
            metadata.append({'offset': hex(at + 32), 'bytes': 16, 'reason': 'Extend RX to authored gates'})
        if row[0] == 1 and row[3] == 0x1ba4920:
            require(row[6] == 0x5e8a0, 'Production data/BSS layout differs')
            struct.pack_into('<Q', result, at + 40, 0x5e920)
            metadata.append({'offset': hex(at + 40), 'bytes': 8, 'reason': '128-byte zero-initialized mailbox'})
    shoff = struct.unpack_from('<Q', prod, 40)[0]
    shsize, shcount = struct.unpack_from('<HH', prod, 58)
    struct.pack_into('<Q', result, 40, shoff + INSERT_SIZE)
    metadata.append({'offset': '0x28', 'bytes': 8, 'reason': 'Shift section-table file offset'})
    for i in range(shcount):
        old_at, new_at = shoff + i * shsize, shoff + INSERT_SIZE + i * shsize
        fields = struct.unpack_from('<IIQQQQIIQQ', prod, old_at)
        if fields[4] >= INSERT:
            struct.pack_into('<Q', result, new_at + 24, fields[4] + INSERT_SIZE)
            metadata.append({'offset': hex(new_at + 24), 'bytes': 8, 'reason': 'Shift section file offset'})
        if fields[1] == 8 and fields[3] == 0x1be49d0:
            require(fields[5] == 0x1e770, 'Production BSS section differs')
            struct.pack_into('<Q', result, new_at + 32, 0x1e870)
            metadata.append({'offset': hex(new_at + 32), 'bytes': 8, 'reason': 'Cover prior BSS tail gap plus mailbox'})
    hook_rows = []
    for address, before, after in HOOKS:
        at = file_offset(prod, address, 4)
        require(prod[at:at + 4] == bytes.fromhex(before), 'Production instruction preimage differs')
        require(at < INSERT, 'Hook unexpectedly requires shifted file offset')
        result[at:at + 4] = bytes.fromhex(after)
        hook_rows.append({'RVA': hex(address), 'bytes': 4, 'before_hex': before, 'after_hex': after})
    require(bytes(result) == candidate, 'Unaccounted output byte differs from production-root reconstruction')
    require(sha(candidate) == FINAL_SHA, 'Final staging core identity differs')
    return {'prod_input_sha256': PROD_CORE_SHA, 'normalized_input_sha256': STAGING_INPUT_SHA,
            'final_core_sha256': FINAL_SHA, 'route_data_spans': routes, 'instruction_sites': hook_rows,
            'compiled_gates': gate_rows, 'inserted_file_bytes': INSERT_SIZE, 'ELF_metadata_fields': metadata,
            'every_output_byte_reconstructed_from_prod_and_declared_changes': True,
            'all_unlisted_production_input_bytes_preserved': True}


def build(prod_apk, kit, output, llvm):
    prod_apk, kit, output, llvm = map(Path, (prod_apk, kit, output, llvm))
    require(shared.digest(prod_apk) == PROD_APK_SHA, 'Authentic production V9 whole APK required')
    with zipfile.ZipFile(prod_apk) as archive:
        prod = archive.read(CORE_ENTRY)
    normalized, route_rows = normalize_routes(prod)
    disk = shared.physical_output(output)
    output.mkdir(parents=True)
    Elf = shared.module('prod_rebase_elf', kit / 'retained-build/compare_core.py').Elf
    Unwind = shared.module('prod_rebase_unwind', kit / 'retained-build/core_unwind_map.py').UnwindMap
    source = SimpleNamespace(Elf=Elf, elf=Elf(normalized))
    source.unwind = Unwind(source.elf)
    r5 = build_dynamic_core.build_core(kit, output / 'r5-core', llvm, source)
    require(shared.digest(output / 'r5-core/owned_core_pins.h')
            == shared.digest(kit / 'reset-baseline/semantic/owned/owned_core_pins.h'), 'Regenerated R5 pins differ')
    import capstone
    raw = r5.read_bytes()
    reader = SimpleNamespace(raw=raw, SHA=sha(raw), elf=Elf(raw),
                             read=lambda address, size: build_dynamic_core.virtual_bytes(raw, address, size),
                             decoder=capstone.Cs(capstone.CS_ARCH_ARM64, capstone.CS_MODE_ARM))
    core, unused_pins, reset = build_reset_core.build(kit / 'semantic/owned/reset_gate.S', kit / 'reset-baseline',
                                                     output / 'reset-core', llvm, reader)
    core, pins, integrity = build_integrity_core.build(core, unused_pins, kit / 'integrity/download_success_size_gate.S',
        kit / 'integrity/download_run_once_gate.S', kit / 'integrity/child_order_gate.S', output / 'integrity-core', llvm)
    accounting = account_output(prod, core.read_bytes(), {name: (output / name).read_bytes() for name, _, _, _ in GATES})
    for name, role in (('owned_core_pins.h', 'semantic/owned/owned_core_pins.h'),
                       ('cli_song_pins.h', 'semantic/song-v9/cli_song_pins.h')):
        require(shared.digest(pins / name) == shared.digest(kit / role), 'Regenerated final pins differ')
    require(shared.digest(prod_apk) == PROD_APK_SHA, 'Production APK changed during build')
    receipt = {'status': 'PROD_V9_ROOTED_STAGING_CORE_REBUILT_AND_EVERY_BYTE_ACCOUNTED',
               'prod_APK_sha256': PROD_APK_SHA, 'core_sha256': shared.digest(core), 'core': str(core),
               'private_pins': str(pins), 'route_normalization': route_rows, 'accounting': accounting,
               'reset_receipt': reset, 'integrity_receipt': integrity, 'external_disk': disk,
               'builder_sha256': shared.digest(Path(__file__)), 'compiled_from_prod_input_and_authored_gates': True,
               'accepted_final_SO_used_as_build_input': False, 'device_or_server_actions': False}
    (output / 'BUILD_RECEIPT.json').write_text(json.dumps(receipt, indent=2) + '\n', newline='\n')
    return core, pins, receipt
