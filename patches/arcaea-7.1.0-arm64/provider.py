"""Retain the verified V36 FMOD error diagnostic on the exact 7.1 provider."""
import hashlib
from pathlib import Path

SOURCE_SHA = 'c05377995a79030c66f75d2775ac3cec3ebbbc9aa680d952781e9372863fa17a'
OUTPUT_SHA = '679d1eff38c619086c5eaef251c4bd60f2aeaad11eb4b7c0d7e0bab71fe23ca6'
OFFSET = 0x3be68
BEFORE = bytes.fromhex('a8835b38a9835cf8c0fefff000a837911f010072a102899a50')
AFTER = bytes.fromhex('3f030072a302969aa1e0ed10a27bed50800080521f2003d54c')


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def build(raw):
    if sha(raw) != SOURCE_SHA or raw[OFFSET:OFFSET + len(BEFORE)] != BEFORE:
        raise ValueError('Exact 7.1 provider/preimage required')
    result = raw[:OFFSET] + AFTER + raw[OFFSET + len(BEFORE):]
    if len(result) != len(raw) or sha(result) != OUTPUT_SHA:
        raise ValueError('FMOD diagnostic output identity differs')
    receipt = {'schema': 'akaine.port71.provider.v1', 'source_sha256': SOURCE_SHA,
               'output_sha256': OUTPUT_SHA, 'engine_sha256': sha(Path(__file__).read_bytes()),
               'offset': OFFSET, 'declared_bytes': len(BEFORE),
               'scope': 'Existing FMOD error text to Android log; not an audio read-contract fix',
               'error_propagation_unchanged': True, 'runtime_accepted': False}
    return result, receipt


def validate(source, output, receipt):
    expected, proof = build(source)
    if output != expected or receipt != proof:
        raise ValueError('Provider payload or receipt differs from its exact source build')


def runtime_header(raw):
    if sha(raw) != OUTPUT_SHA:
        raise ValueError('Exact diagnostic provider required for runtime guards')
    # The exact source hash fixes the VA-zero RX segment and all call/relocation associations.
    spans = ((0x34e60, 544), (0x23078, 376), (0x2a068, 676), (0x3ba38, 1628), (0x4b8f0, 16))
    arrays, rows = [], []
    for index, (address, count) in enumerate(spans):
        name = 'AKAINE_SFX_PROVIDER_' + str(index)
        arrays.append('inline constexpr unsigned char ' + name + '[] = {'
                      + ','.join(hex(b) for b in raw[address:address + count]) + '};\n')
        rows.append('{' + hex(address) + ',' + name + ',sizeof(' + name + ')},\n')
    return ('#pragma once\nstruct AkaineSfxPin { uintptr_t address; const unsigned char* bytes; size_t size; };\n'
            + ''.join(arrays) + 'inline constexpr AkaineSfxPin AKAINE_SFX_PROVIDER_PINS[] = {\n'
            + ''.join(rows) + '};\n')
