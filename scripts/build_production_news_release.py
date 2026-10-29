"""Production V36 sibling profile; existing source compilers remain unchanged."""
import argparse
import json
from pathlib import Path
import shutil

import build_news_core
import build_prod_rebase_news_core
import build_prod_rebase_release as engine
import build_production_news_core as core
import build_production_bundle_partial_cache as partial_cache

ROOT = engine.ROOT
PROFILE = ROOT / 'patches/arcaea-7.0.255-arm64/production-news-v36-source-lock.json'
CHECKOUT = PROFILE.with_name('production-news-v36-checkout-sources.json')
PLAN = PROFILE.with_name('production-news-v36-plan.json')
RELEASE = 'production-prod-v9-news-v36'
SEALED = 'PRODUCTION_V36_CONTROLS_SEALED'
PENDING = 'PRODUCTION_V36_CANDIDATE_CONTROLS_UNACCEPTED'
BASE_ROLE = engine.BASE_ROLE
digest = engine.digest
expected_payloads = engine.expected_payloads


def bound_paths(lock, paths):
    document = json.loads(CHECKOUT.read_bytes())
    if document['source_lock_sha256'] != digest(PROFILE):
        raise ValueError('Production checkout map differs from source lock')
    return engine.shared.checkout_paths(lock, paths, document, ROOT)


def verify(lock, paths, candidate=False):
    required_status = PENDING if candidate else SEALED
    if (lock.get('release') != RELEASE or lock.get('status') != required_status
            or lock.get('application_version') != '7.0.255' or lock.get('content_version') != '7.0.255.25'
            or lock.get('base_apk') != {'role': BASE_ROLE, 'sha256': core.PROD_APK_SHA}):
        raise ValueError('Explicit production V36 profile and matching acceptance state required')
    rows = engine.shared.verify(lock, paths)
    forbidden = {'base/v18-staging.apk', 'dex/classes3-source.dex', 'dex/classes4-source.dex'}
    if forbidden & {row['role'] for row in rows}:
        raise ValueError('Foreign base/raw DEX inputs are forbidden')
    bound = {Path(paths[row['role']]).resolve(): row['sha256'] for row in rows}
    modules = (*engine.ACTIVE_MODULES, build_news_core, build_prod_rebase_news_core, core, partial_cache)
    for path in (Path(__file__), engine.LOADER_PROFILE, *(Path(module.__file__) for module in modules)):
        if bound.get(path.resolve()) != digest(path):
            raise ValueError('Active production builder is not a pinned source: ' + path.name)
    plan = json.loads(PLAN.read_bytes())
    expected = expected_payloads(lock)
    replacements = plan.get('replacements', [])
    if (digest(PLAN) != lock.get('build_plan_sha256') or plan.get('environment') != 'production'
            or plan.get('not_for_production') is not False or plan.get('source_sha256') != core.PROD_APK_SHA
            or plan.get('content_version') != lock['content_version'] or plan.get('binary_patches') != []
            or len(replacements) != 5 or {row['archive_path']: row['sha256'] for row in replacements} != expected
            or any(row['file'] != 'final/payload/' + row['archive_path'] for row in replacements)):
        raise ValueError('Production five-payload assembly contract differs')
    if not candidate and expected['lib/arm64-v8a/libcocos2dcpp.so'] != core.OUTPUT_SHA:
        raise ValueError('Production core hash control differs')
    engine.build_loader_equivalence.verify(json.loads(engine.LOADER_PROFILE.read_bytes()), engine.final.loader_paths(paths))
    return rows


def validate_provenance(receipt, dex, loader, actual):
    staging = dict(actual)
    staging['lib/arm64-v8a/libcocos2dcpp.so'] = core.STAGING_NEWS_SHA
    engine.validate_provenance(receipt.get('fresh_V36_source_provenance', {}), dex, loader, staging)
    proof = receipt.get('production_route_accounting', {})
    if (receipt.get('status') != 'PROD_V9_ROOTED_PRODUCTION_V36_CORE_REBUILT_AND_ACCOUNTED'
            or receipt.get('prod_APK_sha256') != core.PROD_APK_SHA
            or receipt.get('core_sha256') != core.OUTPUT_SHA
            or actual['lib/arm64-v8a/libcocos2dcpp.so'] != core.OUTPUT_SHA
            or receipt.get('accepted_final_SO_used_as_build_input') is not False
            or proof.get('visible_and_encrypted_shared_routes_match_authentic_production') is not True
            or proof.get('all_other_fresh_V36_bytes_identical') is not True or proof.get('changed_bytes') != 61):
        raise ValueError('Production V36 routing/source provenance differs')


def build(lock, paths, output, candidate=False, assemble=False):
    if candidate and assemble:
        raise ValueError('Unaccepted candidate controls cannot assemble an APK')
    verify(lock, paths, candidate)
    source_hash, checkout_hash = digest(PROFILE), digest(CHECKOUT)
    output = Path(output)
    disk = engine.shared.physical_output(output)
    output.mkdir(parents=True)
    kit = output / 'private-kit'
    hydrated = engine.shared.hydrate(lock, paths, kit)
    llvm = Path(hydrated['android-sdk/ndk/28.2.13676358/toolchains/llvm/prebuilt/windows-x86_64/bin/clang++.exe']).parent
    native, pins, provenance = core.build(hydrated[BASE_ROLE], kit, output / 'core', llvm)
    for role, name in (('semantic/owned/owned_core_pins.h', 'owned_core_pins.h'),
                       ('semantic/song-v9/cli_song_pins.h', 'cli_song_pins.h'),
                       ('semantic/native/cli_pins.h', 'cli_pins.h')):
        if digest(pins / name) != digest(hydrated[role]):
            raise ValueError('Regenerated production runtime pins differ')
    monitor = engine.final.compile_monitor(kit, hydrated, output / 'monitor')
    normalized, dex_receipt = engine.build_prod_rebase_dex.build(hydrated[BASE_ROLE], hydrated['tools/java-17/bin/java.exe'],
        hydrated['tools/jadx-1.5.6-all.jar'], hydrated['tools/RawDexTool.java'], output / 'prod-dex-normalization')
    for name in ('classes3', 'classes4'):
        hydrated['dex/' + name + '-source.dex'] = str(normalized[name + '.dex'])
    base_dex = engine.shared.dex(kit, hydrated, output / 'startup-dex')
    classes3, pacing = engine.build_cap60_dex.build(base_dex['classes3.dex'], Path(hydrated['tools/java-17/bin/java.exe']),
        Path(hydrated['tools/jadx-1.5.6-all.jar']), Path(hydrated['tools/RawDexTool.java']), output / 'pacing-dex', kit / 'pacing')
    previous = partial_cache.OUTPUT_SHA
    partial_cache.OUTPUT_SHA = None if candidate else expected_payloads(lock)['classes3.dex']
    try:
        classes3, partials = partial_cache.build(classes3, Path(hydrated['tools/java-17/bin/java.exe']),
            Path(hydrated['tools/java-17/bin/javac.exe']), Path(hydrated['tools/jadx-1.5.6-all.jar']),
            Path(hydrated['tools/RawDexTool.java']), Path(hydrated['tools/android-build-35/d8.jar']),
            output / 'bundle-partials-dex', kit / 'bundle-partials', candidate=candidate)
    finally:
        partial_cache.OUTPUT_SHA = previous
    loader = engine.build_loader_equivalence.build(json.loads(engine.LOADER_PROFILE.read_bytes()), engine.final.loader_paths(paths), output / 'loader')
    payloads = {'lib/arm64-v8a/libcocos2dcpp.so': native, 'lib/arm64-v8a/libakaineanomaly_monitor.so': monitor,
                'lib/arm64-v8a/libakfcloader.so': output / 'loader/libakfcloader.so',
                'classes3.dex': classes3, 'classes4.dex': base_dex['classes4.dex']}
    actual = {name: digest(path) for name, path in payloads.items()}
    validate_provenance(provenance, dex_receipt, loader, actual)
    assets = engine.assetset_identity.verify_apk(hydrated[BASE_ROLE], hydrated['assetset/manifest.json'])
    if assets['assetset_sha256'] != lock['assetset_sha256']:
        raise ValueError('Authentic production asset set differs')
    if not candidate and actual != expected_payloads(lock):
        raise ValueError('Production source payload differs; stop before APK')
    for name, path in payloads.items():
        target = output / 'payload-kit/final/payload' / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target)
    result = dict(status='UNACCEPTED_CANDIDATE_FIVE_SOURCE_PAYLOADS' if candidate else 'FIVE_SOURCE_PAYLOADS_MATCH_NO_APK_ASSEMBLED',
                  release=RELEASE, prod_APK_sha256=core.PROD_APK_SHA, payload_sha256=actual,
                  source_lock_sha256=source_hash, checkout_map_sha256=checkout_hash,
                  core_provenance=provenance, DEX_provenance=dex_receipt, loader_receipt=loader,
                  pacing_receipt=pacing, partial_cache_receipt=partials, base_assets=assets,
                  external_disk=disk, APK_assembled=False, signed=False, device_or_server_actions=False, runtime_accepted=False)
    if assemble:
        result['builder_receipt'] = engine.build_android_client.build(Path(hydrated[BASE_ROLE]), PLAN, output / 'payload-kit', output / 'unsigned.apk')
        result['output_assets'] = engine.assetset_identity.verify_apk(output / 'unsigned.apk', hydrated['assetset/manifest.json'])
        if result['output_assets']['assetset_sha256'] != lock['assetset_sha256']:
            raise ValueError('Production unsigned asset capability differs')
        result.update(status='FIVE_SOURCE_PAYLOADS_AND_UNSIGNED_APK_MATCH', APK_assembled=True, unsigned_apk_sha256=digest(output / 'unsigned.apk'))
    verify(lock, paths, candidate)
    if source_hash != digest(PROFILE) or checkout_hash != digest(CHECKOUT):
        raise ValueError('Production source profile changed during build')
    (output / 'BUILD_RECEIPT.json').write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8', newline='\n')
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=('verify', 'candidate', 'payloads', 'build'))
    parser.add_argument('--local-paths', required=True, type=Path)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    lock = json.loads(PROFILE.read_bytes())
    paths = bound_paths(lock, json.loads(args.local_paths.read_bytes())['paths'])
    candidate = args.mode == 'candidate'
    if args.mode == 'verify':
        result = dict(status='PRODUCTION_V36_SOURCE_INPUTS_VERIFIED', roles=len(verify(lock, paths)), opaque_header_accessed=False)
    else:
        if args.output is None:
            parser.error('Fresh physical-D output required')
        result = build(lock, paths, args.output, candidate, args.mode == 'build')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    try:
        main()
    except Exception:
        raise SystemExit('Production V36 build stopped; private compiler diagnostics suppressed') from None
