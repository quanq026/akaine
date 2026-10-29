"""Append the finite latest10-news gates to a freshly rebuilt normal core."""
import hashlib
import json
from pathlib import Path
import re
import shutil
import struct

import build_dynamic_core
import build_client_support as shared

SOURCE_SHA = '299f271b3b0bb8a656ba02be6fd6327f90b1a0fe2fe11d1e670ae51ccfdae42d'
OUTPUT_SHA = 'ce5210a472e437b3710075cc4a3a1253485ae1ba48bc2a17405caef067c5b1cf'
GATE_SHA = '255c74ff3d699de4fc9bf8fc8fcdba043ef73e50941fdc1a4279a1b061b1a841'
GATE_SOURCE_SHA = 'b2574361dcd8233743748ca18cfd651659657f774769e324bd11e374ce4dcf93'
SOURCE_PINS_SHA = 'b2b94f1e7b3c2e99dd60cc1c85b07f8da68d940f57db837f68bd2a5d1e791e1a'
OUTPUT_PINS_SHA = '09c41f25d4488fb0615cb7d0ff5d1a7e4b37c6d72ea95de85f1f1717f3854327'
CLI_PINS_SHA = '13b05282a4f55f5ffcdde74628a8edb19d403a62bb4e45aab6de59a3bbe49992'
CAVE, GATE_SIZE, OLD_RX_END = 0x1a7e5f0, 180, 0x1a7e5e4
RX_END = CAVE + GATE_SIZE
SYMBOLS = {'news_sort_gate': CAVE, 'news_end_gate': CAVE + 64}
SPANS = ((0x98, 16), (0x19f69a4, 4), (0x19f69ac, 4), (CAVE, GATE_SIZE))


def sha(raw): return hashlib.sha256(raw).hexdigest()


def require(value, reason):
    if not value: raise ValueError(reason)


def gate_proof(raw, gate, symbols):
    import capstone
    cs = capstone.Cs(capstone.CS_ARCH_ARM64, capstone.CS_MODE_ARM)
    cs.detail = True
    # These IP registers are dead on both actual successors until a definition/call.
    code = {i.address: i for i in cs.disasm(raw[0x19f69b0:0x19f72b4], 0x19f69b0)}
    pending = [(0x19f69b0, frozenset((16, 17)))]; seen = set(); inspected = []
    while pending:
        pc, live = pending.pop()
        if (pc, live) in seen:
            continue
        seen.add((pc, live)); ins = code[pc]
        reads, writes = ins.regs_access()
        ip = lambda regs: {int(ins.reg_name(v)[1:]) for v in regs if ins.reg_name(v) in ('x16', 'w16', 'x17', 'w17')}
        require(not ip(reads).intersection(live), 'An IP scratch register is live at the end gate')
        inspected.append(hex(pc))
        if ins.mnemonic in ('bl', 'blr', 'ret'):
            continue
        next_live = frozenset(set(live) - ip(writes))
        if not next_live:
            continue
        if ins.mnemonic == 'b':
            pending.append((int(ins.op_str.removeprefix('#'), 16), next_live))
        elif ins.mnemonic.startswith('b.'):
            pending.append((int(ins.op_str.removeprefix('#'), 16), next_live))
            pending.append((pc + 4, next_live))
        else:
            pending.append((pc + 4, next_live))
    require(raw[0x19f69b0:0x19f69b4].hex() == '7f021beb', 'Native immediate following CMP changed')
    cases = 0
    for slide in (0, 0x7123450000):
        decoded = {i.address: i for i in cs.disasm(gate, 0x1a7e5f0 + slide)}
        for version in (0, 1, 2):
            for ready in (0, 1, 2):
                for callback in (0, 0x1234567800):
                    for same_thread in (False, True):
                        for same_begin in (False, True):
                            for same_end in (False, True):
                                for selected in (0, 0x100000 + 10 * 56):
                                    for kind in ('news_sort_gate', 'news_end_gate'):
                                        regs = {f'x{i}': 0x50000 + i * 17 for i in range(31)}
                                        regs['x19'], regs['x20'] = 0x100000, 0x200000
                                        original = dict(regs); end = 0x100000 + 199 * 56
                                        box = 0x1c031c0 + slide
                                        memory = {box: version, box + 8: ready, box + 88: callback,
                                                  box + 96: regs['x19'] if same_begin else 0xdead,
                                                  box + 104: end if same_end else 0xbeef,
                                                  box + 112: selected, box + 120: 0x700000 if same_thread else 0x800000,
                                                  regs['x20'] + 0x398: end}
                                        pc = symbols[kind] + slide
                                        for _ in range(80):
                                            if pc not in decoded:
                                                break
                                            ins = decoded[pc]; parts = ins.op_str.split(', '); pc += 4
                                            if ins.mnemonic == 'adrp': regs[parts[0]] = int(parts[1].removeprefix('#'), 16)
                                            elif ins.mnemonic == 'add': regs[parts[0]] = regs[parts[1]] + int(parts[2].removeprefix('#'), 0)
                                            elif ins.mnemonic in ('ldr', 'ldar'):
                                                match = re.search(r'\[(x\d+)(?:, #(0x[0-9a-f]+|\d+))?\]', ins.op_str)
                                                regs[parts[0]] = memory[regs[match[1]] + (int(match[2], 0) if match[2] else 0)]
                                            elif ins.mnemonic == 'eor':
                                                right = int(parts[2].removeprefix('#'), 0) if parts[2].startswith('#') else regs[parts[2]]
                                                regs[parts[0]] = regs[parts[1]] ^ right
                                            elif ins.mnemonic in ('cbz', 'cbnz'):
                                                if bool(regs[parts[0]]) == (ins.mnemonic == 'cbnz'): pc = int(parts[1].removeprefix('#'), 16)
                                            elif ins.mnemonic == 'mrs':
                                                require(parts[1].lower() == 'tpidr_el0', 'Unexpected system register')
                                                regs[parts[0]] = 0x700000
                                            elif ins.mnemonic == 'mov': regs[parts[0]] = regs[parts[1]]
                                            elif ins.mnemonic == 'b': pc = int(ins.op_str.removeprefix('#'), 16)
                                            elif ins.mnemonic == 'br': pc = regs[parts[0]]
                                            else: raise ValueError('Unexpected flag/SP-affecting news gate instruction')
                                        else: raise ValueError('Unbounded news gate')
                                        common = version == ready == 1 and bool(callback)
                                        if kind == 'news_sort_gate':
                                            require(pc == (callback if common else 0xac15c8 + slide), 'Sort fallback target differs')
                                            except_regs = ('x16', 'x17')
                                        else:
                                            selected_ok = common and same_thread and same_begin and same_end and bool(selected)
                                            require(pc == 0x19f69b0 + slide and regs['x27'] == (selected if selected_ok else end), 'Native end selection differs')
                                            except_regs = ('x16', 'x17', 'x27')
                                        require(all(regs[k] == v for k, v in original.items() if k not in except_regs), 'News gate changed live arguments/LR')
                                        cases += 1
    return {'emitted_gate_cases': cases, 'IP_liveness_paths_checked': sorted(set(inspected)),
            'SP_LR_SIMD_flags': 'No gate instruction changes SP/LR/SIMD/NZCV; x16/x17 dead at ordinary site'}


def patch(raw, gate):
    require(sha(raw) == SOURCE_SHA and len(gate) == GATE_SIZE and sha(gate) == GATE_SHA,
            'Exact normal source core and authored news gate required')
    require(raw[0x98:0xa8] == struct.pack('<QQ', OLD_RX_END, OLD_RX_END)
            and raw[0x19f69a4:0x19f69a8].hex() == '092bc397'
            and raw[0x19f69ac:0x19f69b0].hex() == '9bce41f9'
            and raw[CAVE:RX_END] == bytes(GATE_SIZE), 'News hook/RX/cave preimage differs')
    result = bytearray(raw)
    result[CAVE:RX_END] = gate
    struct.pack_into('<QQ', result, 0x98, RX_END, RX_END)
    branch = struct.unpack('<I', build_dynamic_core.branch(0x19f69a4, SYMBOLS['news_sort_gate']))[0] | 0x80000000
    result[0x19f69a4:0x19f69a8] = struct.pack('<I', branch)
    result[0x19f69ac:0x19f69b0] = build_dynamic_core.branch(0x19f69ac, SYMBOLS['news_end_gate'])
    cursor = 0
    for at, size in SPANS:
        require(result[cursor:at] == raw[cursor:at], 'Unlisted news core change')
        cursor = at + size
    require(result[cursor:] == raw[cursor:] and len(result) == len(raw)
            and sha(result) == OUTPUT_SHA, 'News core identity differs')
    return bytes(result)


def owned_pins(text, raw):
    require(text.count('OWNED_RX_END = 0x1a7e5e4;') == 1, 'Normal owned RX pin differs')
    text = text.replace('OWNED_RX_END = 0x1a7e5e4;', f'OWNED_RX_END = {RX_END:#x};')
    expression = r'(unsigned char\s+reset_extra_pin_1\[\]\s*=\s*\{)([^}]+)(\})'
    match = re.search(expression, text)
    require(match and bytes(int(v, 16) for v in re.findall(r'0x([0-9a-fA-F]+)', match[2]))
            == struct.pack('<QQ', OLD_RX_END, OLD_RX_END), 'Normal RX bytes differ')
    text, count = re.subn(expression, lambda m: m[1] + ','.join(hex(v) for v in raw[0x98:0xa8]) + m[3], text)
    require(count == 1 and text.count('struct OwnedPin {') == 1, 'Owned pin declaration differs')
    definitions, entries = [], []
    for index, (at, size) in enumerate(SPANS[1:]):
        name = 'news_limit_pin_' + str(index)
        require(name not in text, 'News pins already present')
        definitions.append('inline constexpr unsigned char ' + name + '[] = {' +
                           ','.join(hex(v) for v in raw[at:at + size]) + '};\n')
        entries.append('{' + hex(at) + ',' + name + ',sizeof(' + name + ')},\n')
    text = text.replace('struct OwnedPin {', ''.join(definitions) + 'struct OwnedPin {', 1)
    anchor = 'inline constexpr OwnedPin OWNED_CORE_PINS[] = {\n'
    require(text.count(anchor) == 1, 'Owned pin array differs')
    return text.replace(anchor, anchor + ''.join(entries), 1)


def build(normal_core, pins, gate_source, output, llvm):
    normal_core, pins, gate_source, output, llvm = map(Path, (normal_core, pins, gate_source, output, llvm))
    inputs = {normal_core: SOURCE_SHA, pins / 'owned_core_pins.h': SOURCE_PINS_SHA,
              pins / 'cli_song_pins.h': CLI_PINS_SHA, gate_source: GATE_SOURCE_SHA}
    require(all(p.is_file() and not p.is_symlink() and shared.digest(p) == pin for p, pin in inputs.items()),
            'News stage source input differs')
    disk = shared.physical_output(output); output.mkdir(parents=True)
    shared.run([llvm / 'clang.exe', '--target=aarch64-linux-android24', '-c', gate_source, '-o', output / 'gates.o'])
    shared.run([llvm / 'ld.lld.exe', '--entry=news_sort_gate', '--section-start=.news_gates=0x1a7e5f0',
                '--defsym=owned_mailbox=0x1c031c0', '--defsym=native_news_sort=0xac15c8',
                '--defsym=native_news_resume=0x19f69b0', output / 'gates.o', '-o', output / 'gates.elf'])
    shared.run([llvm / 'llvm-objcopy.exe', '-O', 'binary', '--only-section=.news_gates',
                output / 'gates.elf', output / 'gates.bin'])
    symbols = {}
    for line in shared.run([llvm / 'llvm-nm.exe', '-n', output / 'gates.elf']).decode().splitlines():
        row = line.split()
        if len(row) == 3 and row[2] in SYMBOLS: symbols[row[2]] = int(row[0], 16)
    require(symbols == SYMBOLS, 'Exact authored news gate symbols differ')
    raw, gate = normal_core.read_bytes(), (output / 'gates.bin').read_bytes()
    candidate = patch(raw, gate)
    machine = gate_proof(raw, gate, symbols)
    require(machine['emitted_gate_cases'] == 1152, 'News gate case count differs')
    core = output / 'libcocos2dcpp.so'; core.write_bytes(candidate)
    output_pins = output / 'pins'; output_pins.mkdir()
    owned = output_pins / 'owned_core_pins.h'
    owned.write_text(owned_pins((pins / 'owned_core_pins.h').read_text(encoding='utf-8'), candidate),
                     encoding='utf-8', newline='\n')
    shutil.copy2(pins / 'cli_song_pins.h', output_pins / 'cli_song_pins.h')
    require(shared.digest(owned) == OUTPUT_PINS_SHA
            and shared.digest(output_pins / 'cli_song_pins.h') == CLI_PINS_SHA, 'Regenerated news pins differ')
    require(all(shared.digest(p) == pin for p, pin in inputs.items()), 'News stage input changed during build')
    receipt = {'status': 'NORMAL_SOURCE_CORE_NEWS_EXTENSION_REBUILT_AND_ACCOUNTED',
        'normal_core_sha256': SOURCE_SHA, 'core_sha256': shared.digest(core),
        'gate_sha256': sha(gate), 'gate_source_sha256': GATE_SOURCE_SHA, 'gate_bytes': len(gate),
        'source_owned_pins_sha256': SOURCE_PINS_SHA, 'owned_pins_sha256': shared.digest(owned),
        'cli_song_pins_sha256': CLI_PINS_SHA, 'builder_sha256': shared.digest(Path(__file__)),
        'exact_core_spans': [{'offset': hex(at), 'bytes': size} for at, size in SPANS],
        'all_other_normal_core_bytes_preserved': True, 'machine_proof': machine,
        'compiled_from_fresh_normal_core_and_authored_gate': True,
        'accepted_final_SO_used_as_build_input': False, 'external_disk': disk,
        'device_or_APK_actions': False}
    (output / 'BUILD_RECEIPT.json').write_text(json.dumps(receipt, indent=2) + '\n', encoding='utf-8', newline='\n')
    return core, output_pins, receipt
