"""Finite host checks for the source news-core extension; no target compilation."""
import hashlib
import os
from pathlib import Path
import struct
import unittest

import build_news_core as news

GATE = bytes.fromhex(
    '300c00b010020791110240f9310240d2110100b51122009131fedfc8310240d2910000b5'
    '102e40f9500000b400021fd6ea0bc1171f2003d51f2003d51f2003d59bce41f9300c00b0'
    '10020791110240f9310240d2f10200b51122009131fedfc8310240d2710200b5112e40f9'
    '310200b4113e40f950d03bd5310210cab10100b5300c00b010020791113240f9310213ca'
    '110100b5113640f931021bcab10000b510c2019111fedfc8510000b4fb0311aac4e0fd17')


def liveness_raw():
    raw = bytearray(news.CAVE + news.GATE_SIZE)
    raw[0x19f69b0:0x19f69b4] = bytes.fromhex('7f021beb')
    branch = 0x54000000 | (((0x19f72a8 - 0x19f69b4) // 4) << 5)
    struct.pack_into('<I', raw, 0x19f69b4, branch)
    raw[0x19f69b8:0x19f69bc] = bytes.fromhex('f0031faa')  # Define IP16 before a call.
    raw[0x19f69bc:0x19f69c0] = bytes.fromhex('00000094')
    raw[0x19f72a8:0x19f72ac] = bytes.fromhex('00000094')
    return raw


class NewsCoreTests(unittest.TestCase):
    def test_exact_authored_gates_all_fallback_and_owner_combinations(self):
        self.assertEqual(len(GATE), news.GATE_SIZE)
        self.assertEqual(hashlib.sha256(GATE).hexdigest(), news.GATE_SHA)
        proof = news.gate_proof(liveness_raw(), GATE, news.SYMBOLS)
        self.assertEqual(proof['emitted_gate_cases'], 1152)

    def test_live_scratch_register_is_rejected(self):
        raw = liveness_raw()
        raw[0x19f69b8:0x19f69bc] = bytes.fromhex('e00310aa')  # Read IP16 before definition.
        with self.assertRaisesRegex(ValueError, 'IP scratch register is live'):
            news.gate_proof(raw, GATE, news.SYMBOLS)

    def test_unknown_input_rejected_before_patch_or_pin_mutation(self):
        for raw, gate in ((b'unknown', GATE), (b'', bytes(news.GATE_SIZE)), (b'', GATE[:-1])):
            with self.assertRaises(ValueError): news.patch(raw, gate)
        with self.assertRaises(ValueError): news.owned_pins('unknown pins', bytes(32))

    def test_private_pin_update_keeps_existing_entries_and_adds_only_news(self):
        raw = liveness_raw(); raw[0x98:0xa8] = struct.pack('<QQ', news.RX_END, news.RX_END)
        raw[news.CAVE:news.RX_END] = GATE
        source = ('inline constexpr uintptr_t OWNED_RX_END = 0x1a7e5e4;\n'
                  'inline constexpr unsigned char reset_extra_pin_1[] = {' +
                  ','.join(hex(v) for v in struct.pack('<QQ', news.OLD_RX_END, news.OLD_RX_END)) + '};\n'
                  'struct OwnedPin { uintptr_t address; const unsigned char* bytes; size_t size; };\n'
                  'inline constexpr OwnedPin OWNED_CORE_PINS[] = {\n'
                  '{0x98,reset_extra_pin_1,sizeof(reset_extra_pin_1)},\n};\n')
        result = news.owned_pins(source, raw)
        self.assertIn('OWNED_RX_END = 0x1a7e6a4;', result)
        self.assertEqual(result.count('inline constexpr unsigned char news_limit_pin_'), 3)
        self.assertEqual(result.count('{0x98,reset_extra_pin_1,sizeof(reset_extra_pin_1)}'), 1)
        with self.assertRaises(ValueError): news.owned_pins(result, raw)

    @unittest.skipUnless(os.environ.get('AKAINE_TEST_NEWS_NORMAL_CORE')
                         and os.environ.get('AKAINE_TEST_NEWS_NORMAL_PINS'),
                         'Optional explicit normal source artifacts are not configured')
    def test_known_source_artifacts_reproduce_exact_core_and_pins_without_compile(self):
        core = Path(os.environ['AKAINE_TEST_NEWS_NORMAL_CORE']).read_bytes()
        pins = Path(os.environ['AKAINE_TEST_NEWS_NORMAL_PINS']).read_text(encoding='utf-8')
        self.assertEqual(news.sha(core), news.SOURCE_SHA)
        result = news.patch(core, GATE)
        self.assertEqual(news.sha(result), news.OUTPUT_SHA)
        proof = news.gate_proof(core, GATE, news.SYMBOLS)
        self.assertEqual(proof['emitted_gate_cases'], 1152)
        updated = news.owned_pins(pins, result).encode()
        self.assertEqual(news.sha(updated), news.OUTPUT_PINS_SHA)


if __name__ == '__main__': unittest.main()
