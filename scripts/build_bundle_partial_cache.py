"""Compile the reviewed public staging partial cache and patch the exact cap60 DEX."""
import hashlib
import json
from pathlib import Path
import re
import shutil
import struct
import tempfile
import zlib

import build_cap60_dex as dexutils
import build_release_profile as shared

SOURCE_SHA = 'ec16e94016acb1d602e9f01bd99beacd4a9c5b7eac9fa84825f078d6fabc6153'
OUTPUT_SHA = '20cdddd94102ef27c366379a5b11b3cb33cc8aa3e67cca502158373c62498761'
JAVA_SOURCES = (
    'AkaineBundlePartialCache.java', 'PartialCacheFixture.java',
    'compile-stubs/org/cocos2dx/lib/FileTaskHandler.java',
    'compile-stubs/org/cocos2dx/lib/Cocos2dxDownloader.java',
    'compile-stubs/cz/msebera/android/httpclient/HttpEntity.java',
)


def normalized_method(text):
    """Compare ordered effective catch handlers, independent of split DEX try regions."""
    lines = [line.split('#', 1)[0].strip() for line in text.splitlines()]
    labels, count = {}, 0
    for line in lines:
        if line.startswith(':'): labels[line] = count
        elif line and not line.startswith('.'): count += 1
    def label(match):
        return '@' + str(labels[match[0]]) if match[0] in labels else match[0]
    normalized, catches = [], [[] for unused in range(count)]
    for line in lines:
        if not line or line.startswith(':') or line.startswith('.line '): continue
        if line.startswith('.catch'):
            match = re.fullmatch(r'\.catch(all)?(?: (L[^ ]+;))? \{(:\w+) \.\. (:\w+)\} (:\w+)', line)
            if not match: raise ValueError('Unexpected DEX exception region')
            kind, start, end, target = match[2] or '*', labels[match[3]], labels[match[4]], labels[match[5]]
            if not 0 <= start <= end <= count: raise ValueError('Invalid DEX exception range')
            for index in range(start, end): catches[index].append((kind, target))
        else: normalized.append(re.sub(r':\w+', label, line))
    return normalized, catches


def equivalent_handler(left, right):
    pattern = re.compile(r'(?ms)^\.method ([^\n]+)\n.*?^\.end method$')
    a = {m[1]: normalized_method(m[0]) for m in pattern.finditer(left)}
    b = {m[1]: normalized_method(m[0]) for m in pattern.finditer(right)}
    if a != b: raise ValueError('Handler instructions or ordered exception coverage differ')
    headers = [pattern.sub('', value) for value in (left, right)]
    if sorted(dexutils.normalize_method(headers[0])) != sorted(dexutils.normalize_method(headers[1])):
        raise ValueError('Handler metadata differs')
    return {'method_count': len(a), 'ordered_exception_handlers_at_every_instruction_identical': True}


def compare(before, after, patcher):
    old = {p.relative_to(before).as_posix(): p.read_text('utf-8') for p in before.rglob('*.smali')}
    new = {p.relative_to(after).as_posix(): p.read_text('utf-8') for p in after.rglob('*.smali')}
    if len(old) != 725 or set(new) != set(old) | {patcher.HELPER}:
        raise ValueError('Partial-cache DEX class set differs')
    if {name for name in old if old[name] != new[name]} != {patcher.CALLER, patcher.HANDLER}:
        raise ValueError('Unrelated DEX class changed')
    if (new[patcher.CALLER].replace(patcher.SELECT, '') != old[patcher.CALLER]
            or patcher.unwrap(new[patcher.HANDLER]) != old[patcher.HANDLER]):
        raise ValueError('Unrelated downloader instructions changed')
    return {'existing_classes': 725, 'new_helper_classes': 1, 'existing_methods_changed': 4,
        'new_methods': 1, 'other_723_classes_unchanged': True, 'HTTP_guard_instructions_and_onSuccess_unchanged': True}


def build(source, java, javac, jar, rawdex, d8, output, candidate):
    for path, expected in ((source, SOURCE_SHA), (java, '5b463cad4fcd8e4c655cc1c6f45a3b2ebb002adac94ebad2fdaa4f43e2aee211'),
            (jar, 'fe3e12c45acf75f92369685fd02d1d7a7323385dc725680a9b98a0dac0ea554b'),
            (rawdex, '252425dc1998486b945b933d1eb4bed4199ea34b59054c28ec3177e02b551bf5')):
        if shared.digest(path) != expected: raise ValueError('Pinned partial-cache input differs')
    pinned = {path: shared.digest(path) for path in (Path(__file__), javac, d8,
        candidate / 'patch_restart.py', *(candidate / name for name in JAVA_SOURCES))}
    if {p.relative_to(candidate).as_posix() for p in candidate.rglob('*.java')} != set(JAVA_SOURCES):
        raise ValueError('Unexpected partial-cache Java input')
    patcher = shared.module('reviewed_bundle_partial_patch', candidate / 'patch_restart.py')
    disk = shared.physical_output(output)
    output.mkdir(parents=True)
    classes = output / 'classes'
    shared.run([javac, '--release', '8', '-encoding', 'UTF-8', '-d', classes,
        *(candidate / name for name in JAVA_SOURCES)])
    # The actual Java cache runs with disposable files; compile adapters never enter the DEX.
    with tempfile.TemporaryDirectory(prefix='cache-fixture-', dir=output) as temporary:
        fixture = shared.run([java, '-cp', classes, 'org.cocos2dx.lib.PartialCacheFixture', Path(temporary) / 'files']).decode().strip()
        if not fixture.startswith('PASS cases=28 assertions=92;'):
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
    if shared.digest(target) != OUTPUT_SHA or shared.digest(source) != SOURCE_SHA:
        raise ValueError('Authored partial-cache build does not reproduce accepted bytes')
    if pinned != {path: shared.digest(path) for path in pinned}:
        raise ValueError('Partial-cache build input changed during compilation')
    receipt = {'status': 'AUTHORED_PARTIAL_CACHE_DEX_EXACT_REPRODUCTION_PASS',
        'source_dex_sha256': SOURCE_SHA, 'classes3_path': str(target), 'classes3_sha256': OUTPUT_SHA,
        'classes3_bytes': len(raw), 'JVM_fixtures': fixture, 'comparison': comparison,
        'input_sha256': {str(path): value for path, value in pinned.items()}, 'external_disk': disk,
        'new_helper_compiled_from_Java': True, 'compile_adapters_excluded': True,
        'all_reassembled_instruction_and_exception_coverage_equivalent': True,
        'APK_device_server_network_or_key_actions': False}
    (output / 'BUILD_RECEIPT.json').write_text(json.dumps(receipt, indent=2) + '\n', encoding='utf-8')
    return target, receipt
