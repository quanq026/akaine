"""Build only the exact cap60 pacing method over the current accepted classes3."""
import hashlib
import json
from pathlib import Path
import re
import shutil
import struct
import subprocess
import sys
import zlib

CANDIDATE = OUTPUT = None
DEX_SHA = 'a4376908eee34e5c9eb405f763342322f35cfbb2dd516e39c6344a14c8d43b88'
RENDERER = 'org/cocos2dx/lib/Cocos2dxRenderer.smali'
METHOD = re.compile(r'(?ms)^\.method public onDrawFrame\(Ljavax/microedition/khronos/opengles/GL10;\)V\n.*?^\.end method$')


def digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def run(arguments):
    result = subprocess.run(list(map(str, arguments)), capture_output=True, timeout=180)
    if result.returncode or result.stderr.strip():
        raise RuntimeError('Pacing DEX tool failed; inspect nonsecret source and tool inputs')
    return result.stdout


def normalize_method(text):
    lines = [line.split('#', 1)[0].strip() for line in text.splitlines()]
    labels, count = {}, 0
    for line in lines:
        if line.startswith(':'): labels[line] = count
        elif line and not line.startswith('.'): count += 1
    result = []
    for line in lines:
        if not line or line.startswith(':') or line.startswith('.line '): continue
        line = re.sub(r'(0x[0-9a-fA-F]+)L\b', r'\1', line)
        line = re.sub(r':[a-zA-Z0-9_]+', lambda match: '@' + str(labels[match[0]]) if match[0] in labels else match[0], line)
        result.append(line)
    return result


def compare(before, after):
    old = {p.relative_to(before).as_posix(): p.read_text('utf-8') for p in before.rglob('*.smali')}
    new = {p.relative_to(after).as_posix(): p.read_text('utf-8') for p in after.rglob('*.smali')}
    if old.keys() != new.keys() or len(old) != 725:
        raise ValueError('DEX class set changed')
    if [name for name in old if old[name] != new[name]] != [RENDERER]:
        raise ValueError('Unrelated class changed')
    if METHOD.sub('<DRAW>', old[RENDERER]) != METHOD.sub('<DRAW>', new[RENDERER]):
        raise ValueError('Another renderer method or metadata changed')
    return {'classes': len(old), 'changed_class': RENDERER, 'changed_methods': 1,
            'all_other_methods_and_classes_identical': True}


def build(source, java, jar, helper, output, candidate):
    global OUTPUT, CANDIDATE
    OUTPUT, CANDIDATE = output, candidate
    import build_client_support as driver
    for path, expected in ((source, DEX_SHA), (java, '5b463cad4fcd8e4c655cc1c6f45a3b2ebb002adac94ebad2fdaa4f43e2aee211'),
            (jar, 'fe3e12c45acf75f92369685fd02d1d7a7323385dc725680a9b98a0dac0ea554b'),
            (helper, '252425dc1998486b945b933d1eb4bed4199ea34b59054c28ec3177e02b551bf5')):
        if digest(path) != expected: raise ValueError('Pinned source/tool differs')
    input_hashes = {p.name: digest(p) for p in (Path(__file__), CANDIDATE / 'baseline_onDrawFrame.smali',
        CANDIDATE / 'onDrawFrame.smali', CANDIDATE / 'test_cap60_pacing.py')}
    subprocess.run([sys.executable, str(CANDIDATE / 'test_cap60_pacing.py')], capture_output=True,
                   check=True, timeout=30)
    disk = driver.physical_output(OUTPUT)
    OUTPUT.mkdir(parents=True)
    def tool(mode, path, target): return run([java, '-cp', jar, helper, mode, path, target])
    before, after, verified = OUTPUT / 'baseline', OUTPUT / 'candidate', OUTPUT / 'verified'
    tool('disassemble', source, before)
    text = (before / RENDERER).read_text('utf-8')
    matches = list(METHOD.finditer(text))
    if len(matches) != 1 or matches[0].group() != (CANDIDATE / 'baseline_onDrawFrame.smali').read_text().rstrip():
        raise ValueError('Actual current draw callback differs')
    shutil.copytree(before, after)
    replacement = (CANDIDATE / 'onDrawFrame.smali').read_text().rstrip()
    (after / RENDERER).write_text(METHOD.sub(lambda unused: replacement, text, count=1), encoding='utf-8', newline='\n')
    compare(before, after)
    target = OUTPUT / 'classes3.dex'
    tool('assemble', after, target)
    raw = target.read_bytes()
    if (raw[:8] != b'dex\n037\0' or struct.unpack_from('<I', raw, 32)[0] != len(raw)
            or raw[12:32] != hashlib.sha1(raw[32:]).digest()
            or struct.unpack_from('<I', raw, 8)[0] != zlib.adler32(raw[12:]) & 0xffffffff
            or struct.unpack_from('<I', raw, 96)[0] != 725 or struct.unpack_from('<I', raw, 88)[0] >= 65536):
        raise ValueError('Assembled DEX contract differs')
    tool('disassemble', target, verified)
    comparison = compare(before, verified)
    actual = METHOD.search((verified / RENDERER).read_text('utf-8')).group()
    if normalize_method(actual) != normalize_method(replacement):
        raise ValueError('Reassembled draw instructions/catch structure differ')
    if input_hashes != {p.name: digest(p) for p in (Path(__file__), CANDIDATE / 'baseline_onDrawFrame.smali',
            CANDIDATE / 'onDrawFrame.smali', CANDIDATE / 'test_cap60_pacing.py')} or digest(source) != DEX_SHA:
        raise ValueError('Pacing inputs changed during build')
    receipt = {'status': 'STATIC_VERIFIED_CAP60_DEX_RUNTIME_PENDING', 'source_classes3_sha256': DEX_SHA,
               'classes3_sha256': digest(target), 'classes3_bytes': len(raw), 'classes3_path': str(target),
               'source_files': input_hashes, 'comparison': comparison, 'assembled_method_matches_template': True,
               'fixtures': 7, 'external_disk': disk, 'policy': 'Only exact16666668ns gets absolute-deadline cap60 pacing; existing other fast/slow branches preserved.',
               'API': 'Thread.sleep(long,int) and System.nanoTime; existing nativeRender/monitor/video lifecycle unchanged.',
               'APK_packaged': False, 'device_or_Git_actions': False, 'runtime_performance_accepted': False}
    (OUTPUT / 'BUILD_RECEIPT.json').write_text(json.dumps(receipt, indent=2) + '\n', encoding='utf-8')
    return target, receipt
