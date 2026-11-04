"""Guarded stock 7.1 Android/resources adapter; no native or release acceptance."""
from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import re
import shutil
import struct
import subprocess
import tempfile
from urllib.parse import urlsplit
import zipfile
import zlib

PACKAGE = 'akai.arc.lmao.staging'
LABEL = 'AkaineXD Staging 7.1'
TARGETS = {PACKAGE: ('staging', LABEL, 'arkane-test-bundle'),
           'akai.arc.lmao': ('production', 'AkaineXD', 'bundle')}
STOCK_APK = '1290b99ef6ef9d15f1c26183147ae10c7878cf5bd0f52e2119172e8ac8fc45da'
MANIFEST_SHA = '1682807f126e9d2b9dec9d93f5eae9ea719d87a6e8e70d363910d0f435f505ac'
RESOURCES_SHA = '1a3a5f0c70193dcbf1a49c8fc461fdbeec9d6f90b7cd5fab7ed7626d93549967'
STOCK_DEX = {
    'classes.dex': '71554197307ba738001aef8e5c2075b6305c1f3623d343bd5e44a5cf71ae0e95',
    'classes2.dex': '53d23192e990881da2a7b4a9c3bc7986b17c74bf8d0656dc7b636aee4f5e65b6',
    'classes3.dex': '13c39a26536fa343eb0994430f71c83509e5eefee55e286e20e907a2d7f76c5e',
}
HELPERS = {
    'StockManagedBuild.py': '2a04651ad8461e82e5a2b0ca91edbf6d7833e20303beb338419c4b3d60eb2406',
    'StockResources.py': '0646fad2012b828ff8ad4eb257f2739b51b95856dd96dc6b191e0116556090b9',
}
CACHE_SHA = 'e82d4c698867cf801df90c63c2243957028940f210b4074a14531e2197266a22'
ANALYTICS = 'low/moe/AnalyticsManager.smali'


def require(ok, message):
    if not ok:
        raise ValueError(message)


def target(package):
    require(isinstance(package, str) and package in TARGETS, 'Only exact 7.1 staging or production packages are supported')
    return TARGETS[package]


def digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def checked_path(value, *, fresh=False):
    path = Path(value).absolute()
    for current in (path, *path.parents):
        require(not current.is_symlink() and not (current.exists() and getattr(current.stat(), 'st_file_attributes', 0) & 1024),
                'Managed input/output symlinks and junctions are not allowed')
    require(not path.exists() if fresh else path.is_file(), 'Fresh output or regular input required')
    return path


def normalized_class(engine, text):
    """Canonicalize equivalent smali register declarations, preserving instructions."""
    def rewrite(match):
        signature, body = match.group(1), match.group(2)
        parameter_types = signature.split('(', 1)[1].split(')', 1)[0]
        parameters = 0 if re.search(r'\bstatic\b', signature.split('(', 1)[0]) else 1
        at = 0
        while at < len(parameter_types):
            kind = parameter_types[at]
            if kind == '[':
                while parameter_types[at] == '[': at += 1
                if parameter_types[at] == 'L': at = parameter_types.index(';', at)
                parameters += 1
            elif kind == 'L':
                at = parameter_types.index(';', at); parameters += 1
            else:
                parameters += 2 if kind in 'JD' else 1
            at += 1
        body = re.sub(r'(?m)^(\s*)\.locals (\d+)$',
                      lambda m: m[1] + '.registers ' + str(int(m[2]) + parameters), body)
        return '.method ' + signature + '\n' + body + '.end method'
    canonical = re.sub(r'(?ms)^\.method ([^\n]+)\n(.*?)^\.end method$', rewrite, text)
    # DEX omits trailing false static values; the VM initializes them to false.
    canonical = re.sub(r'(?m)^(\.field (?=[^\n]*\bstatic\b)[^\n]*:Z) = false$', r'\1', canonical)
    canonical = re.sub(r'(?m)^(\.field (?=[^\n]*\bstatic\b)[^\n]*:I) = 0x0$', r'\1', canonical)
    canonical = re.sub(r'(?m)^(\.field (?=[^\n]*\bstatic\b)[^\n]*:(?:L[^;\n]+;|\[+(?:L[^;\n]+;|[BCDFIJSZ]))) = null$', r'\1', canonical)
    methods = []
    def take_method(match):
        methods.append(normalized_member(match[0]))
        return ''
    remaining = re.sub(r'(?ms)^\.method [^\n]+\n.*?^\.end method$', take_method, canonical)
    fields = []
    def take_field(match):
        fields.append(normalized_member(match[0]))
        return ''
    remaining = re.sub(r'(?ms)^\.field [^\n]+(?:\n\s*\.annotation\b.*?^\.end field)?', take_field, remaining)
    return {'header': normalized_member(remaining), 'fields': sorted(fields), 'methods': sorted(methods)}


def normalized_member(text):
    """Member order is not semantic; instruction and local label targets are."""
    lines = []
    for line in text.splitlines():
        quoted = False; escaped = False; end = len(line)
        for index, char in enumerate(line):
            if escaped: escaped = False; continue
            if char == '\\' and quoted: escaped = True; continue
            if char == '"': quoted = not quoted
            if char == '#' and not quoted: end = index; break
        line = line[:end].strip()
        if line: lines.append(line)
    labels, count = {}, 0
    for line in lines:
        if line.startswith(':'): labels[line] = count
        elif not line.startswith('.'): count += 1
    result, handlers = [], {}
    for line in lines:
        if line.startswith((':', '.line ')): continue
        parts = re.split(r'("(?:\\.|[^"\\])*")', line)
        for index in range(0, len(parts), 2):
            parts[index] = re.sub(r':[A-Za-z0-9_]+', lambda m: '@' + str(labels[m[0]]) if m[0] in labels else m[0], parts[index])
            parts[index] = re.sub(r'(0x[0-9a-fA-F]+)L\b', r'\1', parts[index])
        normalized = ''.join(parts)
        catch = re.fullmatch(r'\.catch(?:(all)|\s+(L[^;]+;))\s+\{@(\d+)\s+\.\.\s+@(\d+)\}\s+@(\d+)', normalized)
        if catch:
            kind = '*' if catch[1] else catch[2]
            start, end, target = map(int, catch.group(3, 4, 5))
            require(0 <= start < end <= count and 0 <= target < count, 'Exception coverage exceeds method bounds')
            for index in range(start, end): handlers.setdefault(index, []).append((kind, target))
        else:
            result.append(normalized)
    # DEX flattens nested try ranges into disjoint ranges; compare ordered handlers per covered position.
    if handlers: result.append(('exception_coverage', tuple((index, tuple(values)) for index, values in sorted(handlers.items()))))
    return tuple(result)


def load_helper(root, name):
    path = Path(root) / 'tools' / name
    require(path.is_file() and not path.is_symlink() and digest(path) == HELPERS[name], 'Reviewed helper source differs: ' + name)
    spec = importlib.util.spec_from_file_location('akaine71_' + name.removesuffix('.py'), path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def validate_urls(urls, package=PACKAGE):
    namespace = target(package)[2]
    urls = tuple(urls)
    require(len(urls) <= 32 and len(set(urls)) == len(urls), 'Duplicate or excessive bundle URL allowlist')
    for url in urls:
        require(isinstance(url, str), 'Bundle URL must be text')
        parts = urlsplit(url)
        require(parts.scheme == 'https' and parts.netloc == 'cdn.akai.id.vn'
                and not parts.query and not parts.fragment
                and re.fullmatch('/' + namespace + r'/7[.]1[.]0-[A-Za-z0-9][A-Za-z0-9_-]{0,180}[.]cb', parts.path),
                'Bundle URL must be an exact 7.1 object for the selected package')
    return urls


def cache_source(source, urls, package=PACKAGE):
    """Change only reviewed transport policy, leaving cache lifecycle/guards intact."""
    target(package)
    urls = validate_urls(urls, package)
    require(hashlib.sha256(source.encode()).hexdigest() == CACHE_SHA, 'Reviewed cache source differs')
    old_prefix = '    private static final String PREFIX = "https://cdn.akai.id.vn/bundle/";'
    policy = ('    private static final String[] ALLOWED_URLS = {' + ', '.join(json.dumps(u) for u in urls) + '};\n'
              '    private static boolean allowedUrl(String value) {\n'
              '        if (value == null) return false;\n'
              '        for (String allowed : ALLOWED_URLS) if (allowed.equals(value)) return true;\n'
              '        return false;\n'
              '    }')
    require(source.count(old_prefix) == 1, 'Cache prefix preimage differs')
    source = source.replace(old_prefix, policy, 1)
    condition = ('            if (url == null || !url.startsWith(PREFIX)\n'
                 '                    || !url.substring(PREFIX.length()).matches("7[.]0[.]255-(?:prod-original-base25-20261027_[0-9]|prod-collapse-full-20261022_[0-6]|prod-collapse-from14-20261022)[.]cb")')
    require(source.count(condition) == 1 and source.count('/akai.arc.lmao/files') == 4, 'Cache policy preimage differs')
    source = source.replace(condition, '            if (!allowedUrl(url)', 1)
    return source.replace('/akai.arc.lmao/files', '/' + package + '/files')


def patch_application(engine, activity, config, package=PACKAGE):
    target(package)
    activity, config = engine.patch_application(activity, config)
    return (engine.replace_once(activity, '"akai.arc.lmao.provider"', '"' + package + '.provider"'),
            engine.replace_once(config, 'APPLICATION_ID:Ljava/lang/String; = "akai.arc.lmao"',
                                'APPLICATION_ID:Ljava/lang/String; = "' + package + '"'))


def resource_outputs(stock, source_root, output, package=PACKAGE):
    _, label, _ = target(package)
    engine = load_helper(source_root, 'StockResources.py')
    engine.MANIFEST_SHA, engine.RESOURCES_SHA, engine.PACKAGE = MANIFEST_SHA, RESOURCES_SHA, package
    replacements, receipt = engine.build_resources(stock, output / 'android-resources')
    path = replacements['resources.arsc']
    blob = path.read_bytes()
    rows = engine.chunks(blob, 2)
    values, flags = engine.read_pool(rows[0][1])
    require(values.count('AkaineXD') == 1, 'Application label preimage differs')
    values[values.index('AkaineXD')] = label
    chunks = engine.write_pool(values, flags) + rows[1][1]
    header = bytearray(blob[:12]); struct.pack_into('<I', header, 4, 12 + len(chunks))
    path.write_bytes(bytes(header) + chunks)
    overlays, asset_receipt = engine.build_assets(stock, output / 'mod-assets', Path(source_root) / 'assets/mod-divider.png')
    replacements.update(overlays)
    receipt.update(application_label=label, output_resources_sha256=digest(path), mod_assets=asset_receipt)
    return replacements, receipt


def verify_dex(path, classes, expected=None):
    raw = Path(path).read_bytes()
    require(raw[:8] == b'dex\n037\0' and struct.unpack_from('<I', raw, 32)[0] == len(raw)
            and raw[12:32] == hashlib.sha1(raw[32:]).digest()
            and struct.unpack_from('<I', raw, 8)[0] == zlib.adler32(raw[12:]) & 0xffffffff
            and struct.unpack_from('<I', raw, 96)[0] == classes
            and struct.unpack_from('<I', raw, 88)[0] < 65536, 'Managed DEX structure/checksums differ')
    if expected is not None:
        require(hashlib.sha256(raw).hexdigest() == expected, 'Reviewed managed output hash differs')


def compare_classes(before, after, changed, added):
    original = {p.relative_to(before).as_posix(): p for p in Path(before).rglob('*.smali')}
    candidate = {p.relative_to(after).as_posix(): p for p in Path(after).rglob('*.smali')}
    require(set(candidate) == set(original) | set(added), 'Managed class set differs')
    differences = {name for name in original if original[name].read_bytes() != candidate[name].read_bytes()}
    require(differences == set(changed), 'Undeclared managed classes changed')
    return {'original_classes': len(original), 'changed': sorted(differences), 'added': sorted(added),
            'unrelated_classes_preserved': True}


POLICY_FIXTURE = '''package org.cocos2dx.lib;
import java.io.File;
import java.lang.reflect.Method;
import java.nio.file.Files;
import java.util.Arrays;
public final class StagingPolicyFixture {
    private static int assertions;
    private static void check(boolean value) { assertions++; if (!value) throw new AssertionError(assertions); }
    public static void main(String[] args) throws Exception {
        Method select = AkaineBundlePartialCache.class.getDeclaredMethod("selectForRoot", File.class, String.class, File.class, File.class);
        select.setAccessible(true);
        File root = new File(args[0]).getCanonicalFile();
        check(new File(root, "dltemp").mkdirs());
        File destination = new File(root, "dltemp/7.1.0.1_0.bundle");
        File temporary = new File(destination.getPath() + ".tmp");
        for (int i = 1; i < args.length; i++) {
            String url = args[i];
            File accepted = (File) select.invoke(null, temporary, url, destination, root);
            check(accepted.getParentFile().equals(new File(root, "bundle-partials")));
            Files.write(accepted.toPath(), new byte[]{1,2,3});
            check(select.invoke(null, temporary, url, destination, root).equals(temporary));
            check(Arrays.equals(Files.readAllBytes(accepted.toPath()), new byte[]{1,2,3}));
            AkaineBundlePartialCache.release(accepted);
            check(select.invoke(null, temporary, url, destination, root).equals(accepted));
            AkaineBundlePartialCache.release(accepted);
            for (String denied : new String[]{url + "?bad=1", url + "#fragment", url.replace("https:", "http:"), url + ".other"})
                check(select.invoke(null, temporary, denied, destination, root).equals(temporary));
            check(AkaineBundlePartialCache.select(temporary, url, destination).equals(temporary));
        }
        check(select.invoke(null, temporary, "https://cdn.akai.id.vn/bundle/7.0.255-prod-original-base25-20261027_0.cb", destination, root).equals(temporary));
        check(select.invoke(null, temporary, "https://cdn.akai.id.vn/arkane-test-bundle/7.1.0-unlisted.cb", destination, root).equals(temporary));
        System.out.println("PASS staging policy assertions=" + assertions + "; exact URLs=" + (args.length - 1));
    }
}'''


def cache_fixture(package):
    environment, _, namespace = target(package)
    name = 'StagingPolicyFixture' if environment == 'staging' else 'ProductionPolicyFixture'
    source = POLICY_FIXTURE.replace('StagingPolicyFixture', name).replace('staging policy', environment + ' policy')
    source = source.replace('/arkane-test-bundle/7.1.0-unlisted.cb', '/' + namespace + '/7.1.0-unlisted.cb')
    return name, source, 'PASS ' + environment + ' policy assertions='


def prepare(stock, java, javac, jadx, d8, source_root, output, *, package=PACKAGE, bundle_urls=(), expected_outputs=None):
    """Build only declared managed/resources payloads from verified stock 7.1."""
    stock, java, javac, jadx, d8 = map(checked_path, (stock, java, javac, jadx, d8))
    source_root = Path(source_root).absolute()
    checked_path(source_root / 'tools/StockManagedBuild.py')
    output = checked_path(output, fresh=True)
    repository = Path(__file__).resolve().parents[2]
    require(not output.resolve().is_relative_to(repository.resolve())
            and not output.resolve().is_relative_to(source_root.resolve()), 'Managed output must remain outside source trees')
    adapter = Path(__file__); adapter_hash = digest(adapter)
    environment, label, _ = target(package)
    urls = validate_urls(bundle_urls, package)
    require(stock.is_file() and digest(stock) == STOCK_APK, 'Exact merged stock 7.1 APK required')
    require(not output.exists() and not output.is_symlink(), 'Fresh managed output required')
    engine = load_helper(source_root, 'StockManagedBuild.py')
    files = [source_root / 'tools' / name for name in HELPERS]
    rawdex = source_root / 'tools/RawDexTool.java'
    source_files = [source_root / 'smali/low/moe' / n for n in ('AkfcLoader.smali', 'AnomalyMonitor.smali')]
    source_files += [source_root / 'smali' / engine.RENDERER.replace('.smali', suffix) for suffix in ('_onDrawFrame.smali', '_setAnimationInterval.smali')]
    source_files += [source_root / 'smali/org/cocos2dx/lib/FileTaskHandler_response_guard.smali', rawdex, source_root / 'assets/mod-divider.png']
    cache = source_root / 'bundle-partials'
    source_files += [cache / name for name in engine.JAVA_SOURCES]
    files += [java, javac, jadx, d8, *source_files]
    require(all(checked_path(p).is_file() for p in files), 'Managed source/tool input missing')
    frozen = {p: digest(p) for p in files}
    require(digest(rawdex) == '252425dc1998486b945b933d1eb4bed4199ea34b59054c28ec3177e02b551bf5', 'Raw DEX tool source differs')
    with zipfile.ZipFile(stock) as archive:
        require(len(archive.namelist()) == len(set(archive.namelist())), 'Duplicate stock APK member')
        inputs = {name: archive.read(name) for name in STOCK_DEX}
    require(all(hashlib.sha256(value).hexdigest() == STOCK_DEX[name] for name, value in inputs.items()), 'Stock 7.1 DEX members differ')
    output.mkdir(parents=True)

    def run(arguments):
        try:
            result = subprocess.run(list(map(str, arguments)), capture_output=True, timeout=240)
        except (OSError, subprocess.TimeoutExpired):
            raise RuntimeError('Managed tool failed or timed out; diagnostics suppressed') from None
        require(result.returncode == 0, 'Managed tool failed; diagnostics suppressed')
        return result.stdout.decode('utf-8', errors='replace').strip()

    def dex(mode, source, target):
        run([java, '-cp', jadx, rawdex, mode, source, target])

    replacements, resources = resource_outputs(stock, source_root, output, package)
    baseline_classes = output / 'baseline-cache-classes'
    run([javac, '--release', '8', '-encoding', 'UTF-8', '-d', baseline_classes, *(cache / n for n in engine.JAVA_SOURCES)])
    with tempfile.TemporaryDirectory(prefix='baseline-fixture-', dir=output) as temporary:
        baseline_fixture = run([java, '-cp', baseline_classes, 'org.cocos2dx.lib.PartialCacheFixture', Path(temporary) / 'files'])
    require(baseline_fixture.startswith('PASS cases=35 assertions=101;'), 'Baseline cache body fixture differs')
    generated = output / (environment + '-cache-source'); generated.mkdir()
    actual_java = generated / 'AkaineBundlePartialCache.java'
    actual_java.write_text(cache_source((cache / engine.JAVA_SOURCES[0]).read_text(encoding='utf-8'), urls, package), encoding='utf-8', newline='\n')
    fixture_name, fixture_source, fixture_prefix = cache_fixture(package)
    fixture_java = generated / (fixture_name + '.java'); fixture_java.write_text(fixture_source, encoding='utf-8', newline='\n')
    actual_classes = output / (environment + '-cache-classes')
    run([javac, '--release', '8', '-encoding', 'UTF-8', '-d', actual_classes, actual_java, fixture_java, *(cache / n for n in engine.JAVA_SOURCES[2:])])
    with tempfile.TemporaryDirectory(prefix='policy-fixture-', dir=output) as temporary:
        policy_fixture = run([java, '-cp', actual_classes, 'org.cocos2dx.lib.' + fixture_name, Path(temporary) / 'files', *urls])
    require(policy_fixture.startswith(fixture_prefix), 'Selected URL/package cache fixture failed')
    cache_dex = output / 'cache-dex'; cache_dex.mkdir()
    run([java, '-cp', d8, 'com.android.tools.r8.D8', '--min-api', '24', '--classpath', actual_classes, '--output', cache_dex,
         actual_classes / 'org/cocos2dx/lib/AkaineBundlePartialCache.class'])
    cache_smali = output / 'cache-smali'; dex('disassemble', cache_dex / 'classes.dex', cache_smali)
    require({p.relative_to(cache_smali).as_posix() for p in cache_smali.rglob('*.smali')} == {engine.HELPER}, 'Fixture or compile stubs entered the DEX')
    comparisons = {}
    for member in ('classes.dex', 'classes3.dex'):
        source = output / ('stock-' + member); source.write_bytes(inputs[member])
        tag = member.removesuffix('.dex'); before, after = output / (tag + '-before'), output / (tag + '-changed')
        dex('disassemble', source, before); shutil.copytree(before, after)
        if member == 'classes.dex':
            activity, config = after / 'low/moe/AppActivity.smali', after / 'moe/low/arcdev/BuildConfig.smali'
            at, ct = patch_application(engine, activity.read_text('utf-8'), config.read_text('utf-8'), package)
            activity.write_text(at, encoding='utf-8', newline='\n'); config.write_text(ct, encoding='utf-8', newline='\n')
            shutil.copy2(source_root / 'smali/low/moe/AkfcLoader.smali', after / 'low/moe/AkfcLoader.smali')
            changed, added, classes = {'low/moe/AppActivity.smali', 'moe/low/arcdev/BuildConfig.smali'}, {'low/moe/AkfcLoader.smali'}, 7891
        else:
            renderer = after / engine.RENDERER
            renderer.write_text(engine.patch_renderer(renderer.read_text('utf-8'), source_files[3].read_text('utf-8').rstrip(), source_files[2].read_text('utf-8').rstrip()), encoding='utf-8', newline='\n')
            caller, handler = after / engine.CALLER, after / engine.HANDLER
            c, h = engine.patch_downloads(caller.read_text('utf-8'), handler.read_text('utf-8'), source_files[4].read_text('utf-8'))
            caller.write_text(c, encoding='utf-8', newline='\n'); handler.write_text(h, encoding='utf-8', newline='\n')
            shutil.copy2(cache_smali / engine.HELPER, after / engine.HELPER)
            changed, added, classes = {engine.RENDERER, engine.CALLER, engine.HANDLER}, {engine.HELPER}, 726
        comparisons[member] = compare_classes(before, after, changed, added)
        dex_output = output / member; dex('assemble', after, dex_output); verify_dex(dex_output, classes)
        verified = output / (tag + '-verified'); dex('disassemble', dex_output, verified)
        authored = {p.relative_to(after).as_posix(): p for p in after.rglob('*.smali')}
        assembled = {p.relative_to(verified).as_posix(): p for p in verified.rglob('*.smali')}
        require(authored.keys() == assembled.keys(), 'Assembled class set differs')
        for name in authored:
            require(normalized_class(engine, authored[name].read_text('utf-8')) == normalized_class(engine, assembled[name].read_text('utf-8')), 'Assembled class instructions differ: ' + name)
        comparisons[member]['assembled_source_roundtrip_verified'] = True
        replacements[member] = dex_output
    monitor = output / 'classes4.dex'; dex('assemble', source_root / 'smali/low/moe/AnomalyMonitor.smali', monitor); verify_dex(monitor, 1)
    replacements['classes4.dex'] = monitor
    outputs = {name: digest(path) for name, path in replacements.items()}
    if expected_outputs is not None:
        require(outputs == expected_outputs, 'Reviewed managed output set or hashes differ')
    require(frozen == {path: digest(path) for path in files} and digest(stock) == STOCK_APK and digest(adapter) == adapter_hash,
            'Managed inputs changed during build')
    receipt = {'schema': 'akaine.port71.managed.v1', 'status': 'MANAGED_STATIC_CANDIDATE', 'package': package,
               'environment': environment, 'application_label': label,
               'stock_apk_sha256': STOCK_APK, 'stock_dex_sha256': STOCK_DEX, 'output_sha256': outputs,
               'classes2_preserved_exact': True, 'upstream71_analytics_preserved': ANALYTICS not in comparisons['classes.dex']['changed'],
               'comparisons': comparisons, 'resources': resources, 'baseline_cache_body_fixture': baseline_fixture,
               environment + '_cache_policy_fixture': policy_fixture, 'bundle_url_allowlist': list(urls),
               'retained_partial_cache_enabled': bool(urls), 'cache_pending_manifest': not bool(urls),
               'output_hashes_sealed': expected_outputs is not None, 'runtime_accepted': False, 'full_v36_equivalence_claimed': False,
               'adapter_sha256': adapter_hash,
               'source_sha256': {p.relative_to(source_root).as_posix(): sha for p, sha in frozen.items() if p.is_relative_to(source_root)}}
    (output / 'MANAGED_RECEIPT.json').write_text(json.dumps(receipt, indent=2) + '\n', encoding='utf-8')
    return replacements, receipt
