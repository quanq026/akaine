"""Add guarded pack preparation before nativeInit, preserving V18 pacing and other classes."""
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import shutil
import struct
import subprocess
import zlib

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
SOURCE = Path('D:/AkaineBuilds/pack-capacity-20261023/dex-v19-source')
BUILD = SOURCE.parent / 'dex-v19-build'
RETAINED = Path('D:/From 15_10/akaine-development-20261012/work/bundle1013-download-fix-20261019')
JAVA = Path('W:/Not at home/drives/E/AkaineTools/Java-clean/jdk-17.0.20+8/bin/java.exe')
JAR = Path('W:/Not at home/drives/E/AkaineTools/bin/jadx/lib/jadx-1.5.6-all.jar')
RENDERER = 'org/cocos2dx/lib/Cocos2dxRenderer.smali'
MONITOR = 'low/moe/AnomalyMonitor.smali'
PINS = {'classes3': '6372ea45d2abdf921b2cd29ba86317bd33845f057dd77c8d8660cc997350c274',
        'classes4': 'ad4caf5b688da460c938498f33e728e90bc21b52bc3c69286919ba2c1d821a17'}
METHOD = re.compile(r'(?ms)^\.method ([^\n]+)\n.*?^\.end method$')
SURFACE = 'public onSurfaceCreated(Ljavax/microedition/khronos/opengles/GL10;Ljavax/microedition/khronos/egl/EGLConfig;)V'
PREPARE = '''.method public static prepare()V
    .registers 2

    sget-boolean v0, Llow/moe/AnomalyMonitor;->available:Z
    if-eqz v0, :done
    :try_start
    invoke-static {}, Llow/moe/AnomalyMonitor;->prepareNative()Z
    :try_end
    .catch Ljava/lang/LinkageError; {:try_start .. :try_end} :unavailable
    return-void
    :unavailable
    move-exception v0
    const-string v0, "AkainePacks"
    const-string v1, "early_prepare_unavailable"
    invoke-static {v0, v1}, Landroid/util/Log;->e(Ljava/lang/String;Ljava/lang/String;)I
    :done
    return-void
.end method

.method private static native prepareNative()Z
.end method
'''


def require(ok, message):
    if not ok:
        raise ValueError(message)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def methods(text):
    return {match.group(1): match.group(0) for match in METHOD.finditer(text)}


def instructions(text):
    return [line.strip() for line in text.splitlines()
            if line.strip() and not line.strip().startswith(('.line ', '#'))]


def compare(before, after, dex):
    old = {p.relative_to(before).as_posix(): p.read_text('utf-8') for p in before.rglob('*.smali')}
    new = {p.relative_to(after).as_posix(): p.read_text('utf-8') for p in after.rglob('*.smali')}
    require(old.keys() == new.keys(), 'Class set changed')
    target = RENDERER if dex == 'classes3' else MONITOR
    require([k for k in old if old[k] != new[k]] == [target], 'Unrelated class changed')
    a, b = methods(old[target]), methods(new[target])
    if dex == 'classes3':
        require(a.keys() == b.keys(), 'Renderer method set changed')
        require([k for k in a if a[k] != b[k]] == [SURFACE], 'Other renderer method changed')
        call = 'invoke-static {}, Llow/moe/AnomalyMonitor;->prepare()V'
        current = instructions(b[SURFACE])
        require(current.count(call) == 1, 'Preparation call duplicated or missing')
        current.remove(call)
        require(current == instructions(a[SURFACE]), 'Existing nativeInit flow changed')
        require(b[SURFACE].index(call) < b[SURFACE].index('->nativeInit(II)V'), 'Preparation is too late')
    else:
        require(set(b) - set(a) == {'public static prepare()V', 'private static native prepareNative()Z'},
                'Monitor method additions differ')
        require(all(a[k] == b[k] for k in a), 'Existing monitor methods changed')
        require('Ljava/lang/LinkageError;' in b['public static prepare()V'], 'Missing JNI failure guard')
    require(instructions(METHOD.sub('', old[target])) == instructions(METHOD.sub('', new[target])),
            'Class metadata changed')
    return {'classes': len(old), 'unchanged_classes': len(old) - 1,
            'unchanged_existing_methods': sum(len(methods(v)) for v in old.values()) - (dex == 'classes3'),
            'target': target, 'existing_pacing_and_monitor_methods_identical': True}


def tool(mode, source, output):
    result = subprocess.run([str(JAVA), '-cp', str(RETAINED) + ';' + str(JAR), 'RawDexTool', mode,
                             str(source), str(output)], capture_output=True, text=True, timeout=180)
    require(result.returncode == 0 and not result.stderr.strip(), 'DEX tool failed: ' + result.stderr[:1000])


def main():
    spec = importlib.util.spec_from_file_location('frozen_zip', ROOT / 'work/perf-20261023/release/package_v17.py')
    shared = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(shared)
    shared.EXTERNAL, shared.OUTPUT, shared.BUILD_DIR = SOURCE.parent, BUILD / 'unused.apk', BUILD
    disk = shared.external_target()
    require(not BUILD.exists(), 'Fresh output directory required')
    for dex, pin in PINS.items():
        require(sha(SOURCE / (dex + '.dex')) == pin, 'V18 DEX changed')
    BUILD.mkdir()
    result = {}
    for dex, pin in PINS.items():
        candidate, verified = BUILD / (dex + '-source'), BUILD / (dex + '-verified')
        shutil.copytree(SOURCE / dex, candidate)
        path = candidate / (RENDERER if dex == 'classes3' else MONITOR)
        text = path.read_text('utf-8')
        if dex == 'classes3':
            start = text.index('.method ' + SURFACE)
            at = text.index('    .line 85\n', start) + len('    .line 85\n')
            text = text[:at] + '    invoke-static {}, Llow/moe/AnomalyMonitor;->prepare()V\n\n' + text[at:]
        else:
            require('prepareNative' not in text, 'Preparation already present')
            text += '\n' + PREPARE
        path.write_text(text, encoding='utf-8', newline='\n')
        compare(SOURCE / dex, candidate, dex)
        output = BUILD / (dex + '.dex')
        tool('assemble', candidate, output)
        raw = output.read_bytes()
        require(raw[:8] == b'dex\n037\0' and struct.unpack_from('<I', raw, 32)[0] == len(raw), 'DEX037 header invalid')
        require(raw[12:32] == hashlib.sha1(raw[32:]).digest() and
                struct.unpack_from('<I', raw, 8)[0] == zlib.adler32(raw[12:]) & 0xffffffff, 'DEX checksum invalid')
        require(struct.unpack_from('<I', raw, 88)[0] < 65536, 'DEX method reference overflow')
        tool('disassemble', output, verified)
        result[dex] = {'source_sha256': pin, 'path': str(output), 'sha256': sha(output),
                       'comparison': compare(SOURCE / dex, verified, dex)}
    receipt = {'status': 'STATIC_VERIFIED_RUNTIME_PENDING', 'dex': result,
               'builder_sha256': sha(__file__), 'external_disk': disk, 'device_actions': False}
    (BUILD / 'BUILD_RECEIPT.json').write_text(json.dumps(receipt, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(receipt))


if __name__ == '__main__':
    main()
