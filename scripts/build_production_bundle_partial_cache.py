"""Compile production-only cache sources; retain the reviewed DEX comparison engine."""
import json
from pathlib import Path
import re
import shutil
import struct
import tempfile
import zlib
import hashlib

from build_bundle_partial_cache import JAVA_SOURCES, SOURCE_SHA, compare, equivalent_handler
import build_cap60_dex as dexutils
import build_client_support as shared

# This DEX has no operator key material; its guarded source build is reproducible.
OUTPUT_SHA = 'd4b7d264654edb81020b8abe0e40764e2146fde961311d5021742da0caaf5b8c'


def build(source, java, javac, jar, rawdex, d8, output, sources, *, candidate=False):
    if type(candidate) is not bool or (not candidate and (not isinstance(OUTPUT_SHA, str)
            or re.fullmatch('[0-9a-f]{64}', OUTPUT_SHA) is None)):
        raise ValueError('A sealed production DEX hash or explicit candidate build is required')
    for path, expected in ((source, SOURCE_SHA), (java, '5b463cad4fcd8e4c655cc1c6f45a3b2ebb002adac94ebad2fdaa4f43e2aee211'),
            (jar, 'fe3e12c45acf75f92369685fd02d1d7a7323385dc725680a9b98a0dac0ea554b'),
            (rawdex, '252425dc1998486b945b933d1eb4bed4199ea34b59054c28ec3177e02b551bf5')):
        if shared.digest(path) != expected: raise ValueError('Pinned partial-cache input differs')
    pinned = {path: shared.digest(path) for path in (Path(__file__), javac, d8,
        sources / 'patch_restart.py', *(sources / name for name in JAVA_SOURCES))}
    if {p.relative_to(sources).as_posix() for p in sources.rglob('*.java')} != set(JAVA_SOURCES):
        raise ValueError('Unexpected partial-cache Java input')
    patcher = shared.module('reviewed_bundle_partial_patch', sources / 'patch_restart.py')
    disk = shared.physical_output(output)
    output.mkdir(parents=True)
    classes = output / 'classes'
    shared.run([javac, '--release', '8', '-encoding', 'UTF-8', '-d', classes,
        *(sources / name for name in JAVA_SOURCES)])
    # The actual Java cache runs with disposable files; compile adapters never enter the DEX.
    with tempfile.TemporaryDirectory(prefix='cache-fixture-', dir=output) as temporary:
        fixture = shared.run([java, '-cp', classes, 'org.cocos2dx.lib.PartialCacheFixture', Path(temporary) / 'files']).decode().strip()
        if not fixture.startswith('PASS cases=35 assertions=101;'):
            raise ValueError('Partial-cache fixtures differ')
    helper_dex = output / 'helper-dex'; helper_dex.mkdir()
    shared.run([java, '-cp', d8, 'com.android.tools.r8.D8', '--min-api', '24', '--classpath', classes,
        '--output', helper_dex, classes / 'org/cocos2dx/lib/AkaineBundlePartialCache.class'])
    def tool(mode, path, target): return shared.run([java, '-cp', jar, rawdex, mode, path, target])
    helper_smali = output / 'helper-smali'
    tool('disassemble', helper_dex / 'classes.dex', helper_smali)
    if [p.relative_to(helper_smali).as_posix() for p in helper_smali.rglob('*.smali')] != [patcher.HELPER]:
        raise ValueError('Compile adapter or fixture entered the DEX')
    before, after, verified = [output / name for name in ('baseline', 'candidate', 'verified')]
    tool('disassemble', source, before); shutil.copytree(before, after)
    caller, handler = patcher.patch((before / patcher.CALLER).read_text('utf-8'), (before / patcher.HANDLER).read_text('utf-8'))
    (after / patcher.CALLER).write_text(caller, encoding='utf-8', newline='\n')
    (after / patcher.HANDLER).write_text(handler, encoding='utf-8', newline='\n')
    shutil.copy2(helper_smali / patcher.HELPER, after / patcher.HELPER)
    comparison = compare(before, after, patcher)
    target = output / 'classes3.dex'; tool('assemble', after, target)
    raw = target.read_bytes()
    if (raw[:8] != b'dex\n037\0' or struct.unpack_from('<I', raw, 32)[0] != len(raw)
            or raw[12:32] != hashlib.sha1(raw[32:]).digest()
            or struct.unpack_from('<I', raw, 8)[0] != zlib.adler32(raw[12:]) & 0xffffffff
            or struct.unpack_from('<I', raw, 96)[0] != 726 or struct.unpack_from('<I', raw, 88)[0] >= 65536):
        raise ValueError('Partial-cache DEX header differs')
    tool('disassemble', target, verified)
    for relative in {p.relative_to(after).as_posix() for p in after.rglob('*.smali')}:
        authored, assembled = [(folder / relative).read_text('utf-8') for folder in (after, verified)]
        if relative == patcher.HANDLER: equivalent_handler(authored, assembled)
        elif dexutils.normalize_method(authored) != dexutils.normalize_method(assembled):
            raise ValueError('Reassembled partial-cache instructions differ')
    actual = shared.digest(target)
    if shared.digest(source) != SOURCE_SHA or (not candidate and actual != OUTPUT_SHA):
        raise ValueError('Production partial-cache build differs from the sealed source/output identity')
    if pinned != {path: shared.digest(path) for path in pinned}:
        raise ValueError('Partial-cache build input changed during compilation')
    receipt = {'status': ('UNACCEPTED_PRODUCTION_PARTIAL_CACHE_SOURCE_CANDIDATE' if candidate
                   else 'AUTHORED_PRODUCTION_PARTIAL_CACHE_DEX_EXACT_REPRODUCTION_PASS'),
        'candidate_only': candidate, 'sealed_expected_sha256': None if candidate else OUTPUT_SHA,
        'source_dex_sha256': SOURCE_SHA, 'classes3_path': str(target), 'classes3_sha256': actual,
        'classes3_bytes': len(raw), 'JVM_fixtures': fixture, 'comparison': comparison,
        'input_sha256': {str(path): value for path, value in pinned.items()}, 'external_disk': disk,
        'new_helper_compiled_from_Java': True, 'compile_adapters_excluded': True,
        'all_reassembled_instruction_and_exception_coverage_equivalent': True,
        'APK_device_server_network_or_key_actions': False}
    (output / 'BUILD_RECEIPT.json').write_text(json.dumps(receipt, indent=2) + '\n', encoding='utf-8')
    return target, receipt
