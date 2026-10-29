"""Normalize only the accepted 60Hz interval method from authentic production DEX."""
import hashlib
import json
from pathlib import Path
import re
import shutil
import struct
import zipfile
import zlib

import build_release_profile as shared

ROOT = Path(__file__).resolve().parents[1]
PATCH = ROOT / 'patches/arcaea-7.0.255-arm64/runtime/prod-rebase-dex'
PROD_APK_SHA = 'f14c5ab0871440dec7ecf2107d32d6e2cad745abc82047d03b49db9dbac3f545'
PROD_DEX3_SHA = 'd1e5f99fe8cbad8760906437c033156f892ca4f338eb7764f70568b87c06d27a'
STAGING_DEX3_SHA = '6372ea45d2abdf921b2cd29ba86317bd33845f057dd77c8d8660cc997350c274'
DEX4_SHA = 'ad4caf5b688da460c938498f33e728e90bc21b52bc3c69286919ba2c1d821a17'
RENDERER = 'org/cocos2dx/lib/Cocos2dxRenderer.smali'
METHOD = re.compile(r'(?ms)^\.method public static setAnimationInterval\(F\)V\n.*?^\.end method$')
BEFORE_METHOD_SHA = '2852da25fadaea855b10352773178308e0f385679d776505cd1ceaebe1033f86'
AFTER_METHOD_SHA = 'e41ebaf4b3c6165fc5852d16f19ade6048f2a550601e3538ab494a1d2a5ca631'
TOOLS = {
    'java': '5b463cad4fcd8e4c655cc1c6f45a3b2ebb002adac94ebad2fdaa4f43e2aee211',
    'jar': 'fe3e12c45acf75f92369685fd02d1d7a7323385dc725680a9b98a0dac0ea554b',
    'rawdex': '252425dc1998486b945b933d1eb4bed4199ea34b59054c28ec3177e02b551bf5',
}


def require(value, reason):
    if not value:
        raise ValueError(reason)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def validate_members(dex3, dex4):
    require(sha(dex3) == PROD_DEX3_SHA and sha(dex4) == DEX4_SHA, 'Authentic production DEX members required')


def method_text(text, expected):
    matches = list(METHOD.finditer(text))
    require(len(matches) == 1 and sha(matches[0].group().encode()) == expected,
            'Exact animation-interval method preimage differs')
    return matches[0].group()


def normalize_renderer(text, before, after):
    actual = method_text(text, BEFORE_METHOD_SHA)
    require(actual == before and sha(after.encode()) == AFTER_METHOD_SHA, 'Authored interval patch differs')
    return text.replace(actual, after, 1)


def compare_classes(old, new, before, after):
    require(set(old) == set(new) and len(old) == 725, 'DEX class set differs')
    require([name for name in old if old[name] != new[name]] == [RENDERER], 'Unrelated DEX class changed')
    require(method_text(old[RENDERER], BEFORE_METHOD_SHA) == before
            and method_text(new[RENDERER], AFTER_METHOD_SHA) == after,
            'Reassembled interval method differs')
    require(METHOD.sub('<INTERVAL>', old[RENDERER]) == METHOD.sub('<INTERVAL>', new[RENDERER]),
            'Another renderer method or metadata changed')
    return {'classes': 725, 'unchanged_classes': 724, 'changed_method': 'Cocos2dxRenderer.setAnimationInterval(F)V',
            'all_other_methods_class_metadata_and_classes_identical': True}


def tree(path):
    return {file.relative_to(path).as_posix(): file.read_text(encoding='utf-8') for file in sorted(path.rglob('*.smali'))}


def build(prod_apk, java, jar, rawdex, output):
    prod_apk, java, jar, rawdex, output = map(Path, (prod_apk, java, jar, rawdex, output))
    require(shared.digest(prod_apk) == PROD_APK_SHA, 'Authentic production V9 whole APK required')
    with zipfile.ZipFile(prod_apk) as archive:
        dex3, dex4 = archive.read('classes3.dex'), archive.read('classes4.dex')
    validate_members(dex3, dex4)
    for name, path in (('java', java), ('jar', jar), ('rawdex', rawdex)):
        require(shared.digest(path) == TOOLS[name], 'Pinned DEX tool differs')
    before_path, after_path = PATCH / 'baseline_setAnimationInterval.smali', PATCH / 'setAnimationInterval.smali'
    before, after = before_path.read_text().rstrip(), after_path.read_text().rstrip()
    require(sha(before.encode()) == BEFORE_METHOD_SHA and sha(after.encode()) == AFTER_METHOD_SHA,
            'Versioned finite method patch differs')
    frozen = {str(path): shared.digest(path) for path in (Path(__file__), before_path, after_path, java, jar, rawdex)}
    disk = shared.physical_output(output)
    output.mkdir(parents=True)
    prod3 = output / 'prod-classes3.dex'; prod3.write_bytes(dex3)
    prod4 = output / 'classes4.dex'; prod4.write_bytes(dex4)
    def tool(mode, source, target):
        shared.run([java, '-cp', jar, rawdex, mode, source, target])
    original, candidate, verified = output / 'prod', output / 'candidate', output / 'verified'
    tool('disassemble', prod3, original)
    old = tree(original)
    require(RENDERER in old, 'Production renderer missing')
    patched = normalize_renderer(old[RENDERER], before, after)
    shutil.copytree(original, candidate)
    (candidate / RENDERER).write_text(patched, encoding='utf-8', newline='\n')
    compare_classes(old, tree(candidate), before, after)
    normalized = output / 'classes3.dex'
    tool('assemble', candidate, normalized)
    raw = normalized.read_bytes()
    require(sha(raw) == STAGING_DEX3_SHA and raw[:8] == b'dex\n037\0'
            and struct.unpack_from('<I', raw, 32)[0] == len(raw)
            and raw[12:32] == hashlib.sha1(raw[32:]).digest()
            and struct.unpack_from('<I', raw, 8)[0] == zlib.adler32(raw[12:]) & 0xffffffff
            and struct.unpack_from('<I', raw, 96)[0] == 725, 'Normalized DEX byte identity or header differs')
    tool('disassemble', normalized, verified)
    comparison = compare_classes(old, tree(verified), before, after)
    require(frozen == {path: shared.digest(Path(path)) for path in frozen}
            and shared.digest(prod_apk) == PROD_APK_SHA and shared.digest(prod4) == DEX4_SHA,
            'Frozen production/patch/tool input changed')
    result = {'status': 'PROD_V9_ROOTED_CLASSES3_EXACT_SINGLE_METHOD_NORMALIZATION_VERIFIED',
              'prod_APK_sha256': PROD_APK_SHA, 'prod_classes3_sha256': PROD_DEX3_SHA,
              'classes3_sha256': STAGING_DEX3_SHA, 'classes4_sha256': DEX4_SHA,
              'classes4_copied_exact_from_production': True, 'comparison': comparison,
              'method_before_sha256': BEFORE_METHOD_SHA, 'method_after_sha256': AFTER_METHOD_SHA,
              'input_hashes': frozen, 'external_disk': disk,
              'foreign_or_accepted_final_DEX_used_as_build_input': False,
              'device_server_profile_or_original_source_actions': False}
    (output / 'BUILD_RECEIPT.json').write_text(json.dumps(result, indent=2) + '\n', newline='\n')
    return {'classes3.dex': normalized, 'classes4.dex': prod4}, result
