"""Own compiled gate fixtures distinguish callback capture from the actual task."""
import hashlib
from pathlib import Path
import struct
import unittest

import capstone
import build_integrity_core as integrity

GATE = bytes.fromhex('280f40f91f0500f18b010054166ec497080040f908ad40f9e163009100013fd6'
                     '290f40f91f0009eb80000054ffff03a9ff2700f9d7fcd71708c34139a2fcd717')
RUN_GATE = bytes.fromhex('087040f9a80000b508a0433968000035ff8303d1602ef517c0035fd6')


def run_gate(gate, capture_size, actual_task_size, file_size):
    decoder = capstone.Cs(capstone.CS_ARCH_ARM64, capstone.CS_MODE_ARM)
    pc, registers, flags, cleared, measured = integrity.CAVE, {}, None, set(), False
    for unused in range(30):
        if pc in (0x107d804, 0x107d8d0): return pc, cleared, measured
        instruction = next(decoder.disasm(gate[pc - integrity.CAVE:pc - integrity.CAVE + 4], pc))
        op, operands = instruction.mnemonic, instruction.op_str
        if op == 'ldr' and operands in ('x8, [x25, #0x18]', 'x9, [x25, #0x18]',
                                       'x8, [x24, #0x18]', 'x9, [x24, #0x18]'):
            registers[operands[:2]] = actual_task_size if 'x25' in operands else capture_size
        elif op == 'cmp':
            if operands == 'x8, #1': flags = registers['x8'], 1
            elif operands == 'x0, x9': flags = registers['x0'], registers['x9']
            else: raise AssertionError(operands)
        elif op in ('b.lt', 'b.eq'):
            if flags[0] < flags[1] if op == 'b.lt' else flags[0] == flags[1]:
                pc = int(operands[1:], 16); continue
        elif op == 'b': pc = int(operands[1:], 16); continue
        elif op == 'bl': assert operands == '#0xb99da4'
        elif op == 'blr': assert operands == 'x8'; registers['x0'] = file_size; measured = True
        elif op == 'stp': assert operands == 'xzr, xzr, [sp, #0x38]'; cleared.update((0x38, 0x40))
        elif op == 'str': assert operands == 'xzr, [sp, #0x48]'; cleared.add(0x48)
        else:
            assert (op, operands) in (('ldr', 'x8, [x0]'), ('ldr', 'x8, [x8, #0x158]'),
                ('add', 'x1, sp, #0x18'), ('ldrb', 'w8, [x24, #0x70]'))
        pc += 4
    raise AssertionError('Gate escaped bounded instructions')


class IntegrityCoreTests(unittest.TestCase):
    def test_run_once_gate_fresh_active_terminal_tasks_preserve_stack(self):
        self.assertEqual(hashlib.sha256(RUN_GATE).hexdigest(), integrity.RUN_GATE_SHA)
        decoder = capstone.Cs(capstone.CS_ARCH_ARM64, capstone.CS_MODE_ARM)
        for handle, terminal in ((0, 0), (1, 0), (0, 1), (1, 1), (0, 255), (2**64 - 1, 0)):
            pc, register, stack = integrity.RUN_CAVE, None, 0
            for unused in range(10):
                if pc == 0x17c9f14:
                    self.assertEqual((handle, terminal, stack), (0, 0, -0xe0)); break
                instruction = next(decoder.disasm(RUN_GATE[pc - integrity.RUN_CAVE:pc - integrity.RUN_CAVE + 4], pc))
                op, operands = instruction.mnemonic, instruction.op_str
                if op == 'ldr': self.assertEqual(operands, 'x8, [x0, #0xe0]'); register = handle
                elif op == 'ldrb': self.assertEqual(operands, 'w8, [x0, #0xe8]'); register = terminal
                elif op == 'cbnz':
                    if register: pc = int(operands.split('#')[1], 16); continue
                elif op == 'sub': self.assertEqual(operands, 'sp, sp, #0xe0'); stack -= 0xe0
                elif op == 'b': pc = int(operands[1:], 16); continue
                elif op == 'ret': self.assertTrue(handle or terminal); self.assertEqual(stack, 0); break
                else: self.fail(str(instruction))
                pc += 4
            else: self.fail('Run-once gate escaped bounded instructions')

    def test_compiled_gate_uses_final_path_task_size_not_global_capture(self):
        self.assertEqual(hashlib.sha256(GATE).hexdigest(), integrity.GATE_SHA)
        for capture, task, actual in ((1636313, 2128746, 2128746), (2128746, 1636313, 1636313),
                                      (1636313, 2128746, 1636313), (2128746, 1636313, 2128746),
                                      (999, 2128746, 0), (999, 2128746, 65537), (999, 2128746, 2128747),
                                      (999, 2128746, -1), (999, 0, -1), (999, -1, 3)):
            with self.subTest(capture=capture, task=task, actual=actual):
                target, cleared, measured = run_gate(GATE, capture, task, actual)
                bad = task > 0 and task != actual
                self.assertEqual(target, 0x107d8d0 if bad else 0x107d804)
                self.assertEqual(cleared, {0x38, 0x40, 0x48} if bad else set())
                self.assertEqual(measured, task > 0)
        old = bytearray(GATE); old[0] = 0x08; old[32] = 0x09
        self.assertEqual(run_gate(old, 1636313, 2128746, 2128746)[0], 0x107d8d0)
        self.assertEqual(run_gate(old, 1636313, 2128746, 1636313)[0], 0x107d804)

    def test_private_pin_update_preserves_old_entries_and_replaces_PH_once(self):
        source = ('inline constexpr uintptr_t OWNED_RX_END = 0x1a7e540;\n'
                  'inline constexpr unsigned char reset_extra_pin_1[] = {' +
                  ','.join(hex(x) for x in struct.pack('<QQ', integrity.CAVE, integrity.CAVE)) + '};\n'
                  'struct OwnedPin { uintptr_t address; const unsigned char* bytes; size_t size; };\n'
                  'inline constexpr OwnedPin OWNED_CORE_PINS[] = {\n'
                  '{0x98,reset_extra_pin_1,sizeof(reset_extra_pin_1)},\n};\n')
        raw = bytearray(integrity.END)
        raw[0x98:0xa8] = struct.pack('<QQ', integrity.END, integrity.END)
        raw[integrity.CAVE:integrity.END] = GATE
        result = integrity.owned_pins(source, raw)
        self.assertIn('OWNED_RX_END = 0x1a7e580;', result)
        self.assertEqual(result.count('{0x98,reset_extra_pin_1,sizeof(reset_extra_pin_1)}'), 1)
        self.assertEqual(result.count('inline constexpr unsigned char integrity_extra_pin_'), 3)
        with self.assertRaises(AssertionError): integrity.owned_pins(result, raw)
        with self.assertRaises(AssertionError): integrity.owned_pins(source.replace('0x40,0xe5', '0x41,0xe5', 1), raw)

    def test_unknown_core_or_gate_fails_before_parsing(self):
        for raw, gate in ((b'unknown core', GATE), (b'', bytes(64)), (b'', GATE[:-1])):
            with self.assertRaises(ValueError): integrity.patch(raw, gate)
        for raw, gate in ((b'unknown core', RUN_GATE), (b'', bytes(28)), (b'', RUN_GATE[:-1])):
            with self.assertRaises(ValueError): integrity.patch_run_once(raw, gate)


if __name__ == '__main__': unittest.main()
