"""Build only the scoped Reset leaf gate/core/private pin overlays; no APK/device."""
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import struct
import subprocess
import sys

HERE = BUILD = KIT = LLVM = None
HOOK, CAVE, TAIL, CONTINUE, CALL_RETURN = 0x181a818, 0x1a7e480, 0x181a9f4, 0x181a81c, 0x1246c34


def sha(raw): return hashlib.sha256(raw).hexdigest()


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def run(arguments):
    result = subprocess.run([str(x) for x in arguments], capture_output=True, timeout=30)
    if result.returncode:
        raise RuntimeError('Reset leaf assembly/link verification failed')
    return result.stdout.decode(errors='replace')


def bytes_array(name, raw):
    return 'inline constexpr unsigned char ' + name + '[] = {' + ','.join(hex(x) for x in raw) + '};'


def build(assembly, baseline_kit, output, llvm, reader):
    global HERE, BUILD, KIT, LLVM
    HERE, BUILD, KIT, LLVM = assembly.parent, output, baseline_kit, llvm
    import build_client_support as guard
    from build_dynamic_core import branch, virtual_bytes
    disk = guard.physical_output(BUILD)
    assert reader.SHA == '7f3811cbe0308b709c9dcd4c72b6ffe18ee23454973fcb852a966ca5cf0c36c8'
    original = reader.raw
    assert reader.read(HOOK, 4) == bytes.fromhex('e00e00b4')
    assert reader.read(0x1246c30, 4) == bytes.fromhex('e91b1794') or next(reader.decoder.disasm(reader.read(0x1246c30, 4), 0x1246c30)).op_str == '#0x181a7d4'
    phoff, phsize, phcount = struct.unpack_from('<Q', original, 32)[0], *struct.unpack_from('<HH', original, 54)
    headers = [(phoff + i * phsize, struct.unpack_from('<IIQQQQQQ', original, phoff + i * phsize)) for i in range(phcount)]
    rx = [(at, row) for at, row in headers if row[0] == 1 and row[1] == 5 and row[3] == 0]
    assert len(rx) == 1
    rx_at, rx_row = rx[0]
    assert rx_row[2] == 0 and rx_row[5] == rx_row[6] == 0x1a7e47c and CAVE == (rx_row[5] + 15) & ~15
    BUILD.mkdir(parents=True)
    run([LLVM / 'clang.exe', '--target=aarch64-linux-android24', '-c', assembly, '-o', BUILD / 'gate.o'])
    run([LLVM / 'ld.lld.exe', '--entry=reset_default_second_refresh_gate', f'--section-start=.reset_gate={CAVE:#x}',
         f'--defsym=reset_call_return={CALL_RETURN:#x}', f'--defsym=native_persistence_tail={TAIL:#x}',
         f'--defsym=native_refresh_continue={CONTINUE:#x}', BUILD / 'gate.o', '-o', BUILD / 'gate.elf'])
    run([LLVM / 'llvm-objcopy.exe', '-O', 'binary', '--only-section=.reset_gate', BUILD / 'gate.elf', BUILD / 'gate.bin'])
    gate = (BUILD / 'gate.bin').read_bytes()
    assert 0 < len(gate) <= 512 and not len(gate) % 4
    new_end = CAVE + len(gate)
    assert new_end < min(row[3] for at, row in headers if row[0] == 1 and row[3] > 0)
    assert original[CAVE:new_end] == bytes(len(gate))
    candidate = bytearray(original)
    candidate[HOOK:HOOK + 4] = branch(HOOK, CAVE)
    candidate[CAVE:new_end] = gate
    struct.pack_into('<QQ', candidate, rx_at + 32, new_end, new_end)
    allowed = sorted(((HOOK, HOOK + 4), (CAVE, new_end), (rx_at + 32, rx_at + 48)))
    cursor = 0
    for start, end in allowed:
        assert cursor <= start and candidate[cursor:start] == original[cursor:start]
        cursor = end
    assert candidate[cursor:] == original[cursor:]
    assert virtual_bytes(candidate, CAVE, len(gate)) == gate
    assert candidate[0x1a7d4d0:0x1a7e47c] == original[0x1a7d4d0:0x1a7e47c]
    sections = []
    for section in reader.elf.sections:
        if section['type'] == 8 or not section['size']:
            continue
        start, end = section['offset'], section['offset'] + section['size']
        before, after = original[start:end], candidate[start:end]
        if before != after:
            assert section['name'] == '.text' and start <= HOOK < end
            offset = HOOK - start
            assert before[:offset] == after[:offset] and before[offset + 4:] == after[offset + 4:]
        sections.append({'name': section['name'], 'original_sha256': sha(before), 'candidate_sha256': sha(after)})
    core = BUILD / 'libcocos2dcpp-reset-default.so'
    core.write_bytes(candidate)
    private = BUILD / 'private-pins'
    private.mkdir()
    owned_source = KIT / 'semantic/owned/owned_core_pins.h'
    owned = owned_source.read_text(encoding='utf-8')
    assert 'OWNED_RX_END = 0x1a7e47c;' in owned
    owned = owned.replace('OWNED_RX_END = 0x1a7e47c;', f'OWNED_RX_END = {new_end:#x};')
    extra = [(CAVE, gate), (rx_at + 32, bytes(candidate[rx_at + 32:rx_at + 48])), (HOOK, bytes(candidate[HOOK:HOOK + 4]))]
    for index, (address, raw) in enumerate(extra):
        owned = owned.replace('struct OwnedPin {', bytes_array('reset_extra_pin_' + str(index), raw) + '\nstruct OwnedPin {', 1)
    at = owned.index('inline constexpr OwnedPin OWNED_CORE_PINS[] = {') + len('inline constexpr OwnedPin OWNED_CORE_PINS[] = {')
    owned = owned[:at] + '\n' + '\n'.join(f'{{{address:#x},reset_extra_pin_{index},sizeof(reset_extra_pin_{index})}},' for index, (address, raw) in enumerate(extra)) + owned[at:]
    (private / 'owned_core_pins.h').write_text(owned, encoding='utf-8', newline='\n')
    song_source = KIT / 'semantic/song-v9/cli_song_pins.h'
    song = song_source.read_text(encoding='utf-8')
    expression = r'inline constexpr unsigned char CLI_SONG_SORT_GROUP_REVERSE\[\] = \{([^}]+)\};'
    match = re.search(expression, song)
    before = bytes(int(value, 16) for value in re.findall(r'0x([0-9a-fA-F]+)', match[1]))
    assert before == reader.read(0x181a7d4, len(before))
    updated = virtual_bytes(candidate, 0x181a7d4, len(before))
    song = re.sub(expression, lambda unused: bytes_array('CLI_SONG_SORT_GROUP_REVERSE', updated), song, count=1)
    (private / 'cli_song_pins.h').write_text(song, encoding='utf-8', newline='\n')
    disassembly = run([LLVM / 'llvm-objdump.exe', '-d', BUILD / 'gate.elf'])
    (BUILD / 'GATE_DISASSEMBLY.txt').write_text(disassembly, encoding='utf-8')
    instructions = list(reader.decoder.disasm(gate, CAVE))
    assert len(instructions) * 4 == len(gate) and not any(i.mnemonic in ('bl', 'blr') for i in instructions)
    assert not any(i.mnemonic.startswith(('st', 'ld')) and '[x19' in i.op_str for i in instructions if i.mnemonic.startswith('st'))
    for instruction in instructions:
        if instruction.mnemonic == 'b':
            target = int(instruction.op_str.lstrip('#'), 16)
            assert CAVE <= target < new_end or target in (TAIL, CONTINUE)
    receipt = {'status': 'RESET_CORE_AND_PRIVATE_PINS_BUILT_SYMBOLIC_REVIEW_PENDING',
               'source_core_sha256': reader.SHA, 'core': str(core), 'core_sha256': sha(candidate),
               'gate_address': hex(CAVE), 'gate_bytes': len(gate), 'gate_sha256': sha(gate),
               'old_RX_end': hex(rx_row[5]), 'new_RX_end': hex(new_end),
               'three_exact_file_spans': [{'offset': hex(start), 'bytes': end - start,
                   'before_sha256': sha(original[start:end]), 'after_sha256': sha(candidate[start:end])} for start, end in allowed],
               'all_other_file_bytes_unchanged': True, 'original_sections': sections,
               'existing_owned_gate_bytes_unchanged': True, 'ELF_sections_FDE_notes_relocations_unchanged': True,
               'saved_LR_binding': 'original181a7dc savesx29/x30 atSP+d0;181a7f4 setsx29=SP+d0;gatechecks[x29+8]==core+1246c34',
               'gate_has_no_native_calls_or_per_frame_work': True, 'numeric_counters_added': False,
               'private_pin_files': [{'name': path.name, 'sha256': sha(path.read_bytes())} for path in sorted(private.iterdir())],
               'required_relink': 'Recompile latest owned module with new privateOWNED_RX_END+extra3pins and latest monitor with updatedCLI_SONG_SORT_GROUP_REVERSE; do not reuse oldowned.o ordisablepins.',
               'assembly_sha256': sha(assembly.read_bytes()), 'build_script_sha256': sha(Path(__file__).read_bytes()),
               'device_or_APK_or_server_or_Git_actions': False, 'external_disk': disk,
               'limits': ['LeafgatehasnoadditionalFDE;originalunwindsectionsareunchangedandframepointerpreserved. A stackcapturewhilePCisinsideleafcanlackmatchingunwindmetadata.',
                          'SymbolicfixtureisnotactualARMexecution. Independentreview/combinedmonitorclosure/staticexport/hardeningchecksrequired beforeAPK.',
                          'No claimthat2488msisenabledgatecost;matchedResetmeasurement/runtimeinvariantsstillpending.']}
    (BUILD / 'BUILD_RECEIPT.json').write_text(json.dumps(receipt, indent=2) + '\n')
    return core, private, receipt
