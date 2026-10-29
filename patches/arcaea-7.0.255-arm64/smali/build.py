"""Build all V36 managed changes from the merged, verified APKPure application."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import shutil
import struct
import subprocess
import tempfile
import zipfile
import zlib

STOCK = {
    'classes.dex': 'c52e7f8ba09a123ca7b2ac2a6f2d2c3269943bd9b6b80c76e67568ef8bd1fba0',
    'classes2.dex': '53d23192e990881da2a7b4a9c3bc7986b17c74bf8d0656dc7b636aee4f5e65b6',
    'classes3.dex': '13c39a26536fa343eb0994430f71c83509e5eefee55e286e20e907a2d7f76c5e',
}
EXPECTED = {
    'classes.dex': '9a21f611e52cb9506a20080f53503c9fb15e6e744308f7dcd7f72d11a2149e5f',
    'classes3.dex': 'd4b7d264654edb81020b8abe0e40764e2146fde961311d5021742da0caaf5b8c',
    'classes4.dex': '6c4b63c3168a25a98c476862bc84f8de53de31257439c1e7473acfb3315f0ba0',
}
RENDERER = 'org/cocos2dx/lib/Cocos2dxRenderer.smali'
CALLER = 'org/cocos2dx/lib/Cocos2dxDownloader$3.smali'
HANDLER = 'org/cocos2dx/lib/FileTaskHandler.smali'
HELPER = 'org/cocos2dx/lib/AkaineBundlePartialCache.smali'
JAVA_SOURCES = (
    'AkaineBundlePartialCache.java', 'PartialCacheFixture.java',
    'compile-stubs/org/cocos2dx/lib/FileTaskHandler.java',
    'compile-stubs/org/cocos2dx/lib/Cocos2dxDownloader.java',
    'compile-stubs/cz/msebera/android/httpclient/HttpEntity.java',
)
SELECT = '''    iget-object v3, p0, Lorg/cocos2dx/lib/Cocos2dxDownloader$3;->val$url:Ljava/lang/String;

    invoke-static {v1, v3, v2}, Lorg/cocos2dx/lib/AkaineBundlePartialCache;->select(Ljava/io/File;Ljava/lang/String;Ljava/io/File;)Ljava/io/File;

    move-result-object v1

'''
RELEASE = '''    invoke-static {p0}, Lorg/cocos2dx/lib/AkaineBundlePartialCache;->finished(Lorg/cocos2dx/lib/FileTaskHandler;)V

'''
FIELDS = '''.field _akaineCacheCancelled:Z

.field _akaineCacheWriting:Z

.field _akaineCacheReleased:Z

'''
CANCEL = '''.method public onCancel()V
    .registers 1

    invoke-static {p0}, Lorg/cocos2dx/lib/AkaineBundlePartialCache;->cancelled(Lorg/cocos2dx/lib/FileTaskHandler;)V

    invoke-super {p0}, Lcom/loopj/android/http/FileAsyncHttpResponseHandler;->onCancel()V

    return-void
.end method

'''
BEGIN = '''    invoke-static {p0}, Lorg/cocos2dx/lib/AkaineBundlePartialCache;->begin(Lorg/cocos2dx/lib/FileTaskHandler;)V

    :akaine_cache_body_start
'''
END = '''    :akaine_cache_body_end
    .catchall {:akaine_cache_body_start .. :akaine_cache_body_end} :akaine_cache_body_failed

    :akaine_cache_body_done
    invoke-static {p0}, Lorg/cocos2dx/lib/AkaineBundlePartialCache;->end(Lorg/cocos2dx/lib/FileTaskHandler;)V

    return-void

    :akaine_cache_body_failed
    move-exception v0

    invoke-static {p0}, Lorg/cocos2dx/lib/AkaineBundlePartialCache;->end(Lorg/cocos2dx/lib/FileTaskHandler;)V

    throw v0
'''
FAILURE = '''    invoke-virtual {p0}, Lorg/cocos2dx/lib/FileTaskHandler;->getTargetFile()Ljava/io/File;

    move-result-object v0

    invoke-static {p1, v0}, Lorg/cocos2dx/lib/AkaineBundlePartialCache;->failed(ILjava/io/File;)V

'''


def require(value, message):
    if not value:
        raise ValueError(message)


def digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def replace_once(text, before, after):
    require(text.count(before) == 1, 'Managed source preimage differs')
    return text.replace(before, after, 1)


def method(text, signature):
    pattern = re.compile(r'(?ms)^\.method ' + re.escape(signature) + r'\n.*?^\.end method$')
    matches = list(pattern.finditer(text))
    require(len(matches) == 1, 'Unique managed method required')
    return pattern, matches[0].group()


def normalize_method(text):
    lines = [line.split('#', 1)[0].strip() for line in text.splitlines()]
    labels, count = {}, 0
    for line in lines:
        if line.startswith(':'):
            labels[line] = count
        elif line and not line.startswith('.'):
            count += 1
    return [re.sub(r':[a-zA-Z0-9_]+', lambda match: '@' + str(labels[match[0]]) if match[0] in labels else match[0],
                   re.sub(r'(0x[0-9a-fA-F]+)L\b', r'\1', line))
            for line in lines if line and not line.startswith((':', '.line '))]


def patch_application(activity, config):
    activity = replace_once(activity, 'const-string v2, "moe.low.arc.provider"',
                            'const-string v2, "akai.arc.lmao.provider"')
    call = '    invoke-virtual {v0, p0, v1}, Lcom/getkeepsafe/relinker/ReLinkerInstance;->loadLibrary(Landroid/content/Context;Ljava/lang/String;)V\n    :try_end_21'
    activity = replace_once(activity, call, call.replace('\n    :try_end_21',
        '\n\n    invoke-static {}, Llow/moe/AkfcLoader;->init()V\n    :try_end_21'))
    prefix = '.method protected onDestroy()V\n    .registers 1\n'
    activity = replace_once(activity, prefix, prefix + '\n    invoke-static {}, Llow/moe/AkfcLoader;->wipeDecrypted()V\n')
    config = replace_once(config, 'APPLICATION_ID:Ljava/lang/String; = "moe.low.arc"',
                          'APPLICATION_ID:Ljava/lang/String; = "akai.arc.lmao"')
    return activity, config


def patch_renderer(text, interval, frame):
    signature = 'public static setAnimationInterval(F)V'
    pattern, before = method(text, signature)
    require(hashlib.sha256(before.encode()).hexdigest() == '2852da25fadaea855b10352773178308e0f385679d776505cd1ceaebe1033f86',
            'Stock animation interval method differs')
    require(hashlib.sha256(interval.encode()).hexdigest() == 'e41ebaf4b3c6165fc5852d16f19ade6048f2a550601e3538ab494a1d2a5ca631',
            'Authored animation interval differs')
    text = pattern.sub(lambda _: interval, text, count=1)
    signature = 'public onDrawFrame(Ljavax/microedition/khronos/opengles/GL10;)V'
    pattern, before = method(text, signature)
    require(before.count('->nativeRender()V') == 2 and 'AnomalyMonitor' not in before,
            'Stock frame callback differs')
    require(frame.count('->nativeRender()V') == frame.count('Llow/moe/AnomalyMonitor;->frame()V') == 3,
            'Authored frame monitor coverage differs')
    text = pattern.sub(lambda _: frame, text, count=1)
    signature = 'public onSurfaceCreated(Ljavax/microedition/khronos/opengles/GL10;Ljavax/microedition/khronos/egl/EGLConfig;)V'
    pattern, before = method(text, signature)
    require('prepare()V' not in before and before.count('    .line 85\n') == 1, 'Stock surface callback differs')
    after = before.replace('    .line 85\n', '    .line 85\n    invoke-static {}, Llow/moe/AnomalyMonitor;->prepare()V\n\n')
    require(after.index('->prepare()V') < after.index('->nativeInit(II)V'), 'Native preparation is too late')
    return pattern.sub(lambda _: after, text, count=1)


def unwrap_cache(handler):
    value = handler.replace(RELEASE, '').replace(FAILURE, '').replace(FIELDS, '').replace(CANCEL, '')
    return value.replace(BEGIN, '').replace(END, '').replace('    goto :akaine_cache_body_done', '    return-void')


def patch_downloads(caller, handler, response_guard):
    require('sendResponseMessage(' not in handler and 'AkaineBundlePartialCache' not in caller + handler,
            'Stock downloader is already patched')
    require(hashlib.sha256(response_guard.encode()).hexdigest() == '9978d67018749208f6f07ae4011af46a9d2edd51ba5809342fee895698db3e19',
            'HTTP response guard source differs')
    handler = replace_once(handler, '# virtual methods\n', '# virtual methods\n' + response_guard + '\n')
    guarded = handler
    caller_changed = replace_once(caller, '    new-instance v3, Lorg/cocos2dx/lib/FileTaskHandler;',
                                   SELECT + '    new-instance v3, Lorg/cocos2dx/lib/FileTaskHandler;')
    site = '.method public onFinish()V\n    .registers 2\n\n'
    handler = replace_once(handler, site, site + RELEASE)
    site = '.method public onFailure(I[Lcz/msebera/android/httpclient/Header;Ljava/lang/Throwable;Ljava/io/File;)V\n    .registers 7\n\n'
    handler = replace_once(handler, site, site + FAILURE)
    handler = replace_once(handler, '# instance fields\n', '# instance fields\n' + FIELDS)
    handler = replace_once(handler, '# virtual methods\n', '# virtual methods\n' + CANCEL)
    pattern, body = method(handler, 'public sendResponseMessage(Lcz/msebera/android/httpclient/HttpResponse;)V')
    require(body.count('    return-void') == 1, 'Response guard exit count differs')
    site = '    invoke-static {}, Ljava/lang/Thread;->currentThread()Ljava/lang/Thread;'
    body = replace_once(body, site, BEGIN + site).replace('    return-void', '    goto :akaine_cache_body_done')
    body = body.replace('.end method', END + '.end method')
    handler = pattern.sub(lambda _: body, handler, count=1)
    require(caller_changed.replace(SELECT, '') == caller and unwrap_cache(handler) == guarded,
            'Cache wrapper changed existing downloader instructions')
    return caller_changed, handler


def verify_dex(path, expected, classes):
    data = path.read_bytes()
    require(hashlib.sha256(data).hexdigest() == expected, 'Managed output hash differs')
    require(data[:8] == b'dex\n037\0' and struct.unpack_from('<I', data, 32)[0] == len(data)
            and data[12:32] == hashlib.sha1(data[32:]).digest()
            and struct.unpack_from('<I', data, 8)[0] == zlib.adler32(data[12:]) & 0xffffffff
            and struct.unpack_from('<I', data, 96)[0] == classes
            and struct.unpack_from('<I', data, 88)[0] < 65536, 'Managed DEX structure/checksums differ')


def build(stock, java, javac, jadx, rawdex, d8, sourceRoot, output):
    stock, java, javac, jadx, rawdex, d8, sourceRoot, output = map(Path,
        (stock, java, javac, jadx, rawdex, d8, sourceRoot, output))
    require(not output.exists(), 'Fresh managed output required')
    source_files = [sourceRoot / 'smali/low/moe' / name for name in
        ('AkfcLoader.smali', 'AnomalyMonitor.smali')]
    source_files += [sourceRoot / 'smali/org/cocos2dx/lib/Cocos2dxRenderer_onDrawFrame.smali', sourceRoot / 'smali/org/cocos2dx/lib/Cocos2dxRenderer_setAnimationInterval.smali']
    source_files += [sourceRoot / 'smali/org/cocos2dx/lib/FileTaskHandler_response_guard.smali']
    cache = sourceRoot / 'bundle-partials'
    source_files += [cache / name for name in JAVA_SOURCES]
    require(all(path.is_file() and not path.is_symlink() for path in source_files), 'Managed source is unavailable')
    frozen = {path: digest(path) for path in [java, javac, jadx, rawdex, d8, *source_files]}
    with zipfile.ZipFile(stock) as archive:
        inputs = {name: archive.read(name) for name in STOCK}
    require(all(hashlib.sha256(data).hexdigest() == STOCK[name] for name, data in inputs.items()), 'Exact stock DEX members required')
    output.mkdir(parents=True)
    def run(arguments):
        try:
            result = subprocess.run(list(map(str, arguments)), capture_output=True, timeout=180)
        except (OSError, subprocess.TimeoutExpired):
            raise RuntimeError('Managed tool failed; private diagnostics suppressed') from None
        require(result.returncode == 0, 'Managed tool failed; private diagnostics suppressed')
        return result.stdout
    def dex(mode, source, target):
        run([java, '-cp', jadx, rawdex, mode, source, target])
    cache_classes = output / 'cache-classes'
    run([javac, '--release', '8', '-encoding', 'UTF-8', '-d', cache_classes, *(cache / name for name in JAVA_SOURCES)])
    with tempfile.TemporaryDirectory(prefix='cache-fixture-', dir=output) as temporary:
        fixture = run([java, '-cp', cache_classes, 'org.cocos2dx.lib.PartialCacheFixture', Path(temporary) / 'files']).decode().strip()
    require(fixture.startswith('PASS cases=35 assertions=101;'), 'Cache fixture failed')
    cache_dex = output / 'cache-dex'
    cache_dex.mkdir()
    run([java, '-cp', d8, 'com.android.tools.r8.D8', '--min-api', '24', '--classpath', cache_classes,
         '--output', cache_dex, cache_classes / 'org/cocos2dx/lib/AkaineBundlePartialCache.class'])
    cache_smali = output / 'cache-smali'
    dex('disassemble', cache_dex / 'classes.dex', cache_smali)
    require({path.relative_to(cache_smali).as_posix() for path in cache_smali.rglob('*.smali')} == {HELPER},
            'Compile adapter or fixture entered the DEX')
    payloads = {}
    for member in ('classes.dex', 'classes3.dex'):
        source = output / ('stock-' + member)
        source.write_bytes(inputs[member])
        tag = member.removesuffix('.dex')
        before, changed = output / (tag + '-before'), output / (tag + '-changed')
        dex('disassemble', source, before)
        shutil.copytree(before, changed)
        if member == 'classes.dex':
            activity = changed / 'low/moe/AppActivity.smali'
            config = changed / 'moe/low/arcdev/BuildConfig.smali'
            a, c = patch_application(activity.read_text('utf-8'), config.read_text('utf-8'))
            activity.write_text(a, encoding='utf-8', newline='\n')
            config.write_text(c, encoding='utf-8', newline='\n')
            shutil.copy2(sourceRoot / 'smali/low/moe/AkfcLoader.smali', changed / 'low/moe/AkfcLoader.smali')
            expected_count, allowed_new = 7891, {'low/moe/AkfcLoader.smali'}
        else:
            renderer = changed / RENDERER
            text = patch_renderer(renderer.read_text('utf-8'),
                (sourceRoot / 'smali/org/cocos2dx/lib/Cocos2dxRenderer_setAnimationInterval.smali').read_text('utf-8').rstrip(),
                (sourceRoot / 'smali/org/cocos2dx/lib/Cocos2dxRenderer_onDrawFrame.smali').read_text('utf-8').rstrip())
            renderer.write_text(text, encoding='utf-8', newline='\n')
            caller, handler = changed / CALLER, changed / HANDLER
            c, h = patch_downloads(caller.read_text('utf-8'), handler.read_text('utf-8'),
                (sourceRoot / 'smali/org/cocos2dx/lib/FileTaskHandler_response_guard.smali').read_text('utf-8'))
            caller.write_text(c, encoding='utf-8', newline='\n')
            handler.write_text(h, encoding='utf-8', newline='\n')
            shutil.copy2(cache_smali / HELPER, changed / HELPER)
            expected_count, allowed_new = 726, {HELPER}
        old_set = {path.relative_to(before).as_posix() for path in before.rglob('*.smali')}
        new_set = {path.relative_to(changed).as_posix() for path in changed.rglob('*.smali')}
        require(new_set == old_set | allowed_new and len(new_set) == expected_count, 'Managed class set differs')
        target = output / member
        dex('assemble', changed, target)
        verify_dex(target, EXPECTED[member], expected_count)
        payloads[member] = target
    monitor = output / 'classes4.dex'
    dex('assemble', sourceRoot / 'smali/low/moe/AnomalyMonitor.smali', monitor)
    verify_dex(monitor, EXPECTED['classes4.dex'], 1)
    payloads['classes4.dex'] = monitor
    require(frozen == {path: digest(path) for path in frozen}, 'Managed build input changed during compilation')
    receipt = {'status': 'STOCK_APKPURE_TO_FINAL_V36_MANAGED_SOURCE_BUILD_PASS', 'source_dex_sha256': STOCK,
        'output_dex_sha256': {name: digest(path) for name, path in payloads.items()},
        'stock_classes2_preserved_exact': True, 'stock_classes2_equal_v9_binary': False,
        'class1_reference_all_7891_disassemblies_identical_v9': True,
        'class1_expected_serialization_sha256': EXPECTED['classes.dex'],
        'final_class3_and_class4_equal_v36': True, 'Java_cache_fixture': fixture,
        'compile_adapters_and_fixture_excluded_from_dex': True, 'classes3_assembled_once': True,
        'original_classes3_changed': [RENDERER, HANDLER, CALLER],
        'accepted_apk_or_final_dex_used_as_input': False,
        'source_sha256': {path.relative_to(sourceRoot).as_posix(): frozen[path] for path in source_files},
        'device_or_server_actions': False}
    (output / 'BUILD_RECEIPT.json').write_text(json.dumps(receipt, indent=2) + '\n', encoding='utf-8')
    return payloads, receipt
