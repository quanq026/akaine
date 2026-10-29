"""Rebuild incoming SHA, exact task-size and repeated-run guards after Reset."""
import hashlib
import json
from pathlib import Path
import re
import shutil
import struct

import build_dynamic_core
import build_release_profile
import build_reset_core

SOURCE_SHA = 'e49d1a98dc66edb87d0deca35241e52653be41e126b26ee89d2f2b3b2267e71b'
OUTPUT_SHA = 'b45a34d912bfaa4cf5cec6c240523f5f4972ae33b7061bdd2b94d319d65df025'
GATE_SHA = '3b47951f4d2c79d033d35f77e8b1fac178145b43de6a856a389d6c80e2ea5957'
CAVE, END = 0x1a7e540, 0x1a7e580
FINAL_SHA = 'c29edd5f07010fcdcbba28e614f6791f60d5dafb22574640420b56fab9cba3fc'
RUN_GATE_SHA = 'd545911c8e2f47548fe73eaa3ebeb7666847e78d13c07647278f63c7ca5bf121'
RUN_HOOK, RUN_CAVE, RUN_END = 0x17c9f10, 0x1a7e580, 0x1a7e59c


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def patch(raw, gate):
    if sha(raw) != SOURCE_SHA or len(gate) != 64 or sha(gate) != GATE_SHA:
        raise ValueError('Reviewed integrity source/gate identity differs')
    phoff = struct.unpack_from('<Q', raw, 32)[0]
    phsize, phcount = struct.unpack_from('<HH', raw, 54)
    headers = [(phoff + i * phsize, struct.unpack_from('<IIQQQQQQ', raw, phoff + i * phsize))
               for i in range(phcount)]
    segments = [(at, row) for at, row in headers if row[0] == 1 and row[1] == 5 and row[3] == 0]
    assert len(segments) == 1
    at, segment = segments[0]
    assert at + 32 == 0x98 and segment[2] == 0 and segment[5] == segment[6] == CAVE
    assert END < min(row[3] for unused, row in headers if row[0] == 1 and row[3] > 0)
    assert raw[CAVE:END] == bytes(64)
    assert raw[0x107d800:0x107d804] == bytes.fromhex('08c34139')
    assert raw[0x13e50dc:0x13e50e0] == bytes.fromhex('152440f9')
    result = bytearray(raw)
    struct.pack_into('<QQ', result, at + 32, END, END)
    result[0x107d800:0x107d804] = build_dynamic_core.branch(0x107d800, CAVE)
    result[0x13e50dc:0x13e50e0] = build_dynamic_core.branch(0x13e50dc, 0x13e5114)
    result[CAVE:END] = gate
    spans = ((0x98, 16), (0x107d800, 4), (0x13e50dc, 4), (CAVE, 64))
    cursor = 0
    for start, length in spans:
        assert result[cursor:start] == raw[cursor:start]
        cursor = start + length
    assert result[cursor:] == raw[cursor:] and len(result) == len(raw)
    assert sha(result) == OUTPUT_SHA
    return bytes(result), spans


def owned_pins(text, raw):
    assert text.count('OWNED_RX_END = 0x1a7e540;') == 1
    text = text.replace('OWNED_RX_END = 0x1a7e540;', 'OWNED_RX_END = 0x1a7e580;')
    expression = r'(unsigned char\s+reset_extra_pin_1\[\]\s*=\s*\{)([^}]+)(\})'
    previous = re.search(expression, text)
    before = bytes(int(x, 16) for x in re.findall(r'0x([a-fA-F0-9]+)', previous[2]))
    assert before == struct.pack('<QQ', CAVE, CAVE)
    text, count = re.subn(expression, lambda m: m[1] + ','.join(hex(x) for x in raw[0x98:0xa8]) + m[3], text)
    assert count == 1
    definitions, entries = [], []
    for index, (address, length) in enumerate(((0x107d800, 4), (0x13e50dc, 4), (CAVE, 64))):
        name = 'integrity_extra_pin_' + str(index)
        assert name not in text
        definitions.append(build_reset_core.bytes_array(name, raw[address:address + length]) + '\n')
        entries.append('{' + hex(address) + ',' + name + ',sizeof(' + name + ')},\n')
    assert text.count('struct OwnedPin {') == 1
    text = text.replace('struct OwnedPin {', ''.join(definitions) + 'struct OwnedPin {')
    anchor = 'inline constexpr OwnedPin OWNED_CORE_PINS[] = {\n'
    assert text.count(anchor) == 1
    return text.replace(anchor, anchor + ''.join(entries))


def patch_run_once(raw, gate):
    if sha(raw) != OUTPUT_SHA or len(gate) != 28 or sha(gate) != RUN_GATE_SHA:
        raise ValueError('Reviewed run-once source/gate identity differs')
    assert raw[RUN_HOOK:RUN_HOOK + 4] == bytes.fromhex('ff8303d1')
    assert raw[RUN_CAVE:RUN_END] == bytes(28)
    assert raw[0x98:0xa8] == struct.pack('<QQ', END, END)
    result = bytearray(raw)
    struct.pack_into('<QQ', result, 0x98, RUN_END, RUN_END)
    result[RUN_HOOK:RUN_HOOK + 4] = build_dynamic_core.branch(RUN_HOOK, RUN_CAVE)
    result[RUN_CAVE:RUN_END] = gate
    spans = ((0x98, 16), (RUN_HOOK, 4), (RUN_CAVE, 28))
    cursor = 0
    for start, length in spans:
        assert result[cursor:start] == raw[cursor:start]
        cursor = start + length
    assert result[cursor:] == raw[cursor:] and len(result) == len(raw)
    assert sha(result) == FINAL_SHA
    return bytes(result), spans


def run_once_owned_pins(text, raw):
    assert text.count('OWNED_RX_END = 0x1a7e580;') == 1
    text = text.replace('OWNED_RX_END = 0x1a7e580;', 'OWNED_RX_END = 0x1a7e59c;')
    expression = r'(unsigned char\s+reset_extra_pin_1\[\]\s*=\s*\{)([^}]+)(\})'
    before = bytes(int(x, 16) for x in re.findall(r'0x([a-fA-F0-9]+)', re.search(expression, text)[2]))
    assert before == struct.pack('<QQ', END, END)
    text, count = re.subn(expression, lambda m: m[1] + ','.join(hex(x) for x in raw[0x98:0xa8]) + m[3], text)
    assert count == 1
    definitions, entries = [], []
    for index, (address, length) in enumerate(((RUN_HOOK, 4), (RUN_CAVE, 28))):
        name = 'runonce_extra_pin_' + str(index)
        assert name not in text
        definitions.append(build_reset_core.bytes_array(name, raw[address:address + length]) + '\n')
        entries.append('{' + hex(address) + ',' + name + ',sizeof(' + name + ')},\n')
    assert text.count('struct OwnedPin {') == 1
    text = text.replace('struct OwnedPin {', ''.join(definitions) + 'struct OwnedPin {')
    anchor = 'inline constexpr OwnedPin OWNED_CORE_PINS[] = {\n'
    assert text.count(anchor) == 1
    return text.replace(anchor, anchor + ''.join(entries))



CHILD_GATE_SHA = '5187759372d5ec26dd77caa6160f0e1465eafe72a8705b635adbdc815bf4362e'
CHILD_FINAL_SHA = '299f271b3b0bb8a656ba02be6fd6327f90b1a0fe2fe11d1e670ae51ccfdae42d'
CHILD_CAVE, CHILD_END, CHILD_HOOK = 0x1a7e5a0, 0x1a7e5e4, 0x9ada6c
CHILD_DEPENDENCIES = [(0x9ada30, 0xb0), (0xc4d284, 0x9c), (0x1924a58, 8), (0x14e9988, 0x128),
                      (0x10905a8, 0x160), (0x9fd76c, 0x94), (0xefd848, 0x14), (0x124c4a0, 0x10), (0x986f60, 0x4fc)]

def patch_child_order(raw, gate):
    if sha(raw) != FINAL_SHA or len(gate) != CHILD_END - CHILD_CAVE or sha(gate) != CHILD_GATE_SHA:
        raise ValueError('Exact reviewed ordinary source and 68-byte gate required')
    assert raw[0x98:0xa8] == struct.pack('<QQ', RUN_END, RUN_END)
    assert raw[CHILD_CAVE:CHILD_END] == bytes(CHILD_END - CHILD_CAVE)
    assert raw[CHILD_HOOK:CHILD_HOOK + 4] == bytes.fromhex('3d65ff97')
    delta = CHILD_CAVE - CHILD_HOOK
    assert delta % 4 == 0 and -(1 << 27) <= delta < 1 << 27
    result = bytearray(raw)
    struct.pack_into('<QQ', result, 0x98, CHILD_END, CHILD_END)
    struct.pack_into('<I', result, CHILD_HOOK, 0x94000000 | ((delta // 4) & 0x3ffffff))
    result[CHILD_CAVE:CHILD_END] = gate
    changes = [(0x98, 16), (CHILD_HOOK, 4), (CHILD_CAVE, len(gate))]
    cursor = 0
    for at, length in sorted(changes):
        assert result[cursor:at] == raw[cursor:at]
        cursor = at + length
    assert result[cursor:] == raw[cursor:] and len(result) == len(raw) and sha(result) == CHILD_FINAL_SHA
    return bytes(result), changes


def child_order_owned_pins(text, raw):
    assert text.count(f'OWNED_RX_END = {RUN_END:#x};') == 1
    text = text.replace(f'OWNED_RX_END = {RUN_END:#x};', f'OWNED_RX_END = {CHILD_END:#x};')
    expression = r'(unsigned char\s+reset_extra_pin_1\[\]\s*=\s*\{)([^}]+)(\})'
    previous = re.search(expression, text)
    assert bytes(int(x, 16) for x in re.findall(r'0x([a-fA-F0-9]+)', previous[2])) == struct.pack('<QQ', RUN_END, RUN_END)
    text, count = re.subn(expression, lambda m: m[1] + ','.join(hex(x) for x in raw[0x98:0xa8]) + m[3], text)
    assert count == 1
    definitions, entries = [], []
    for index, (at, length) in enumerate([*CHILD_DEPENDENCIES, (CHILD_CAVE, CHILD_END - CHILD_CAVE)]):
        name = 'child_order_dependency_pin_' + str(index)
        assert name not in text
        definitions.append('inline constexpr unsigned char ' + name + '[] = {' + ','.join(hex(x) for x in raw[at:at + length]) + '};\n')
        entries.append('{' + hex(at) + ',' + name + ',sizeof(' + name + ')},\n')
    assert text.count('struct OwnedPin {') == 1
    text = text.replace('struct OwnedPin {', ''.join(definitions) + 'struct OwnedPin {')
    anchor = 'inline constexpr OwnedPin OWNED_CORE_PINS[] = {\n'
    assert text.count(anchor) == 1
    return text.replace(anchor, anchor + ''.join(entries))


def build(source, baseline_pins, assembly, run_assembly, child_assembly, output, llvm):
    disk = build_release_profile.physical_output(output)
    raw = source.read_bytes()
    if sha(raw) != SOURCE_SHA:
        raise ValueError('Integrity build requires freshly rebuilt reviewed Reset core')
    output.mkdir(parents=True)
    run = build_reset_core.run
    run([llvm / 'clang.exe', '--target=aarch64-linux-android24', '-c', assembly, '-o', output / 'gate.o'])
    run([llvm / 'ld.lld.exe', '--entry=download_success_size_gate', f'--section-start=.download_size_gate={CAVE:#x}',
         '--defsym=native_fileutils_singleton=0xb99da4', '--defsym=native_download_digest_failure=0x107d8d0',
         '--defsym=native_download_skiphash_dispatch=0x107d804', output / 'gate.o', '-o', output / 'gate.elf'])
    run([llvm / 'llvm-objcopy.exe', '-O', 'binary', '--only-section=.download_size_gate', output / 'gate.elf', output / 'gate.bin'])
    size_candidate, spans = patch(raw, (output / 'gate.bin').read_bytes())
    run([llvm / 'clang.exe', '--target=aarch64-linux-android24', '-c', run_assembly, '-o', output / 'run-gate.o'])
    run([llvm / 'ld.lld.exe', '--entry=download_run_once_gate', f'--section-start=.download_run_once_gate={RUN_CAVE:#x}',
         '--defsym=native_download_run_body=0x17c9f14', output / 'run-gate.o', '-o', output / 'run-gate.elf'])
    run([llvm / 'llvm-objcopy.exe', '-O', 'binary', '--only-section=.download_run_once_gate',
         output / 'run-gate.elf', output / 'run-gate.bin'])
    run_once_candidate, run_spans = patch_run_once(size_candidate, (output / 'run-gate.bin').read_bytes())
    run([llvm / 'clang.exe', '--target=aarch64-linux-android24', '-c', child_assembly, '-o', output / 'child-order-gate.o'])
    run([llvm / 'ld.lld.exe', '--entry=child_order_gate', f'--section-start=.child_order_gate={CHILD_CAVE:#x}',
         '--defsym=owned_mailbox=0x1c031c0', '--defsym=native_child_sort=0x986f60',
         output / 'child-order-gate.o', '-o', output / 'child-order-gate.elf'])
    run([llvm / 'llvm-objcopy.exe', '-O', 'binary', '--only-section=.child_order_gate',
         output / 'child-order-gate.elf', output / 'child-order-gate.bin'])
    candidate, child_spans = patch_child_order(run_once_candidate, (output / 'child-order-gate.bin').read_bytes())
    core = output / 'libcocos2dcpp-integrity.so'
    core.write_bytes(candidate)
    private = output / 'private-pins'; private.mkdir()
    owned = baseline_pins / 'owned_core_pins.h'
    size_pins = owned_pins(owned.read_text(encoding='utf-8'), size_candidate)
    (private / owned.name).write_text(child_order_owned_pins(run_once_owned_pins(size_pins, run_once_candidate), candidate), encoding='utf-8', newline='\n')
    shutil.copy2(baseline_pins / 'cli_song_pins.h', private / 'cli_song_pins.h')
    receipt = {'status': 'EXACT_REVIEWED_INTEGRITY_CORE_AND_PINS_REBUILT', 'source_core_sha256': SOURCE_SHA,
               'core_sha256': sha(candidate), 'size_guard_core_sha256': sha(size_candidate),
               'gate_sha256': GATE_SHA, 'run_gate_sha256': RUN_GATE_SHA, 'RX_end': hex(CHILD_END),
               'four_exact_spans': [{'offset': hex(at), 'bytes': length, 'before_sha256': sha(raw[at:at + length]),
                                    'after_sha256': sha(size_candidate[at:at + length])} for at, length in spans],
               'three_run_once_spans': [{'offset': hex(at), 'bytes': length,
                                        'before_sha256': sha(size_candidate[at:at + length]),
                                        'after_sha256': sha(run_once_candidate[at:at + length])} for at, length in run_spans],
               'three_child_order_spans': [{'offset': hex(at), 'bytes': length,
                                           'before_sha256': sha(run_once_candidate[at:at + length]),
                                           'after_sha256': sha(candidate[at:at + length])} for at, length in child_spans],
               'child_gate_sha256': CHILD_GATE_SHA, 'child_assembly_sha256': sha(child_assembly.read_bytes()),
               'all_other_bytes_unchanged': True, 'assembly_sha256': sha(assembly.read_bytes()),
               'run_assembly_sha256': sha(run_assembly.read_bytes()),
               'build_script_sha256': sha(Path(__file__).read_bytes()), 'external_disk': disk,
               'runtime_accepted': False, 'device_or_server_actions': False}
    (output / 'BUILD_RECEIPT.json').write_text(json.dumps(receipt, indent=2) + '\n')
    return core, private, receipt
