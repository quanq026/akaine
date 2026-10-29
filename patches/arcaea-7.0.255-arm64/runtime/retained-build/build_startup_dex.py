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

RENDERER = 'org/cocos2dx/lib/Cocos2dxRenderer.smali'
MONITOR = 'low/moe/AnomalyMonitor.smali'
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


def build(sources, java, jar, rawdex, output):
    """Add only early native preparation to the two freshly normalized DEX files."""
    import build_client_support as shared
    output = Path(output)
    shared.fresh_output(output)
    output.mkdir(parents=True)
    result, receipts = {}, {}
    def invoke(mode, source, target):
        shared.run([java, '-cp', jar, rawdex, mode, source, target])
    for name in ('classes3', 'classes4'):
        before, after, verified = [output / (name + suffix) for suffix in ('-before', '-after', '-verified')]
        invoke('disassemble', sources[name + '.dex'], before)
        shutil.copytree(before, after)
        relative = RENDERER if name == 'classes3' else MONITOR
        target = after / relative
        text = target.read_text(encoding='utf-8')
        if name == 'classes3':
            start = text.index('.method ' + SURFACE)
            at = text.index('    .line 85\n', start) + len('    .line 85\n')
            text = text[:at] + '    invoke-static {}, Llow/moe/AnomalyMonitor;->prepare()V\n\n' + text[at:]
        else:
            require('prepareNative' not in text, 'Preparation already present')
            text += '\n' + PREPARE
        target.write_text(text, encoding='utf-8', newline='\n')
        compare(before, after, name)
        dex = output / (name + '.dex')
        invoke('assemble', after, dex)
        raw = dex.read_bytes()
        require(raw[:8] == b'dex\n037\0' and struct.unpack_from('<I', raw, 32)[0] == len(raw), 'DEX header differs')
        require(raw[12:32] == hashlib.sha1(raw[32:]).digest()
                and struct.unpack_from('<I', raw, 8)[0] == zlib.adler32(raw[12:]) & 0xffffffff,
                'DEX checksum differs')
        invoke('disassemble', dex, verified)
        receipts[name] = compare(before, verified, name)
        result[name + '.dex'] = dex
    return result, receipts
