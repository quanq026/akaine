"""Focused private-fixture proof for production input and complete byte accounting."""
import os
from pathlib import Path
import unittest
from unittest.mock import patch
import zipfile

import build_prod_rebase_core as rebase


class ProdRebaseCoreTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        apk = os.environ.get('AKAINE_PROD_REBASE_TEST_APK')
        build = os.environ.get('AKAINE_PROD_REBASE_TEST_GATE_ROOT')
        if not apk or not build:
            raise unittest.SkipTest('Set private authentic APK and accepted gate-root fixture references')
        build = Path(build)
        with zipfile.ZipFile(apk) as archive:
            cls.prod = archive.read(rebase.CORE_ENTRY)
        cls.final = (build / 'integrity-core/libcocos2dcpp-integrity.so').read_bytes()
        cls.gates = {name: (build / name).read_bytes() for name, _, _, _ in rebase.GATES}

    def test_authentic_prod_normalizes_only_exact_four_route_spans(self):
        candidate, rows = rebase.normalize_routes(self.prod)
        self.assertEqual(rebase.sha(candidate), rebase.STAGING_INPUT_SHA)
        self.assertEqual(len(rows), 4)
        self.assertEqual(sum(row['changed_bytes'] for row in rows), 61)
        self.assertEqual(len(candidate), len(self.prod))
        self.assertEqual(rows[3]['prod_file_offset'], '0x1b9e00d')

    def test_wrong_input_or_repeated_normalization_is_rejected(self):
        normalized, unused = rebase.normalize_routes(self.prod)
        for raw in (b'unknown', normalized, self.prod[:-1], bytes([self.prod[0] ^ 1]) + self.prod[1:]):
            with self.assertRaisesRegex(ValueError, 'Authentic production'):
                rebase.normalize_routes(raw)

    def test_route_preimage_check_is_independent_of_whole_input_hash(self):
        at = rebase.file_offset(self.prod, rebase.ROUTES[0][0], rebase.ROUTES[0][1])
        tampered = bytearray(self.prod); tampered[at] ^= 1
        actual_sha = rebase.sha
        with patch.object(rebase, 'sha', side_effect=lambda raw: rebase.PROD_CORE_SHA if raw is tampered else actual_sha(raw)):
            with self.assertRaisesRegex(ValueError, 'route preimage'):
                rebase.normalize_routes(tampered)

    def test_complete_accepted_output_is_accounted(self):
        proof = rebase.account_output(self.prod, self.final, self.gates)
        self.assertTrue(proof['every_output_byte_reconstructed_from_prod_and_declared_changes'])
        self.assertEqual(len(proof['instruction_sites']), 14)
        self.assertEqual(proof['inserted_file_bytes'], 16384)
        self.assertEqual(proof['final_core_sha256'], rebase.FINAL_SHA)

    def test_unlisted_code_route_header_tail_or_insertion_change_rejected(self):
        for at in (0x783100, 0x782a74, 40, rebase.INSERT + 0x3fff, len(self.final) - 1):
            candidate = bytearray(self.final); candidate[at] ^= 1
            with self.assertRaisesRegex(ValueError, 'Unaccounted output byte'):
                rebase.account_output(self.prod, candidate, self.gates)

    def test_compiled_gate_tampering_rejected(self):
        name = rebase.GATES[0][0]
        gates = dict(self.gates); gates[name] = bytes([gates[name][0] ^ 1]) + gates[name][1:]
        with self.assertRaisesRegex(ValueError, 'compiled gate identity'):
            rebase.account_output(self.prod, self.final, gates)


if __name__ == '__main__':
    unittest.main()
