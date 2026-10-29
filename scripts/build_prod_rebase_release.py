"""Rebuild the five staging payloads from the authentic production V9 APK."""
import argparse
import json
from pathlib import Path
import shutil

import assetset_identity
import build_akfc_loader
import build_android_client
import build_bundle_partial_cache
import build_cap60_dex
import build_dynamic_core
import build_final_release_profile as final
import build_integrity_core
import build_loader_equivalence
import build_prod_rebase_core
import build_prod_rebase_dex
import build_release_profile as shared
import build_reset_core

ROOT = Path(__file__).resolve().parents[1]
PROFILE = ROOT / 'patches/arcaea-7.0.255-arm64/prod-rebase-source-lock.json'
CHECKOUT = PROFILE.with_name('prod-rebase-checkout-sources.json')
PLAN = PROFILE.with_name('prod-rebase-plan.json')
LOADER_PROFILE = PROFILE.with_name('staging-loader-v6-equivalence.json')
BASE_ROLE = 'base/prod-v9.apk'
PAYLOAD_NAMES = {'lib/arm64-v8a/libcocos2dcpp.so', 'lib/arm64-v8a/libakaineanomaly_monitor.so',
                 'lib/arm64-v8a/libakfcloader.so', 'classes3.dex', 'classes4.dex'}
ACTIVE_MODULES = (assetset_identity, build_akfc_loader, build_android_client, build_bundle_partial_cache,
                  build_cap60_dex, build_dynamic_core, final, build_integrity_core,
                  build_loader_equivalence, build_prod_rebase_core, build_prod_rebase_dex, shared, build_reset_core)


def digest(path):
    return shared.digest(path)


def bound_paths(lock, paths):
    document = json.loads(CHECKOUT.read_bytes())
    if document['source_lock_sha256'] != digest(PROFILE) or json.loads(PROFILE.read_bytes()) != lock:
        raise ValueError('Production-root checkout map differs from this source lock')
    return shared.checkout_paths(lock, paths, document, ROOT)


def expected_payloads(lock):
    rows = lock['expected_replacements']
    prefix = 'final/payload/'
    if any(not row['role'].startswith(prefix) for row in rows):
        raise ValueError('Unexpected production-root payload role')
    result = {row['role'][len(prefix):]: row['sha256'] for row in rows}
    if len(rows) != len(result) or set(result) != PAYLOAD_NAMES:
        raise ValueError('Exactly five distinct production-root payload controls required')
    return result


def verify_active_inputs(lock, paths, extra=()):
    rows = shared.manifest_rows(lock)
    bound = {Path(paths[row['role']]).resolve(): row['sha256'] for row in rows}
    files = [Path(__file__), LOADER_PROFILE,
             build_prod_rebase_dex.PATCH / 'baseline_setAnimationInterval.smali',
             build_prod_rebase_dex.PATCH / 'setAnimationInterval.smali',
             *(Path(module.__file__) for module in ACTIVE_MODULES), *extra]
    for path in files:
        if path.resolve() not in bound or digest(path) != bound[path.resolve()]:
            raise ValueError('Active authored builder/profile is not a pinned release input: ' + path.name)


def verify_plan(lock, plan):
    expected = expected_payloads(lock)
    rows = plan['replacements']
    if (len(rows) != 5 or len({row['archive_path'] for row in rows}) != 5
            or {row['archive_path']: row['sha256'] for row in rows} != expected
            or any(row['file'] != 'final/payload/' + row['archive_path'] for row in rows)
            or plan.get('source_sha256') != build_prod_rebase_core.PROD_APK_SHA
            or plan.get('content_version') != lock['content_version']
            or plan.get('environment') != 'staging' or plan.get('not_for_production') is not True
            or plan.get('binary_patches') != []):
        raise ValueError('Production-root five-payload assembly contract differs')


def verify(lock, paths):
    if (lock.get('release') != 'staging-prod-v9-rebase' or lock.get('content_version') != '7.0.255.20'
            or lock.get('application_version') != '7.0.255'
            or lock.get('base_apk', {}).get('role') != BASE_ROLE
            or lock['base_apk']['sha256'] != build_prod_rebase_core.PROD_APK_SHA):
        raise ValueError('Explicit authentic-production-root staging profile required')
    forbidden = {'base/v18-staging.apk', 'dex/classes3-source.dex', 'dex/classes4-source.dex'}
    if any(row['role'] in forbidden for row in shared.manifest_rows(lock)):
        raise ValueError('Foreign base/raw DEX inputs are forbidden in the production-root profile')
    rows = shared.verify(lock, paths)
    verify_active_inputs(lock, paths)
    if digest(PLAN) != lock['build_plan_sha256']:
        raise ValueError('Production-root replacement plan differs')
    verify_plan(lock, build_android_client.load_plan(PLAN))
    build_loader_equivalence.verify(json.loads(LOADER_PROFILE.read_bytes()), final.loader_paths(paths))
    return rows


def validate_provenance(core, dex, loader, expected):
    if (core.get('status') != 'PROD_V9_ROOTED_STAGING_CORE_REBUILT_AND_EVERY_BYTE_ACCOUNTED'
            or core.get('prod_APK_sha256') != build_prod_rebase_core.PROD_APK_SHA
            or core.get('core_sha256') != expected['lib/arm64-v8a/libcocos2dcpp.so']
            or core.get('compiled_from_prod_input_and_authored_gates') is not True
            or core.get('accepted_final_SO_used_as_build_input') is not False
            or core.get('accounting', {}).get('prod_input_sha256') != build_prod_rebase_core.PROD_CORE_SHA
            or core['accounting'].get('normalized_input_sha256') != build_prod_rebase_core.STAGING_INPUT_SHA
            or core['accounting'].get('final_core_sha256') != core.get('core_sha256')
            or core['accounting'].get('every_output_byte_reconstructed_from_prod_and_declared_changes') is not True
            or core['accounting'].get('all_unlisted_production_input_bytes_preserved') is not True):
        raise ValueError('Finite authentic production-root core provenance differs')
    if (dex.get('status') != 'PROD_V9_ROOTED_CLASSES3_EXACT_SINGLE_METHOD_NORMALIZATION_VERIFIED'
            or dex.get('prod_APK_sha256') != build_prod_rebase_dex.PROD_APK_SHA
            or dex.get('prod_classes3_sha256') != build_prod_rebase_dex.PROD_DEX3_SHA
            or dex.get('classes3_sha256') != build_prod_rebase_dex.STAGING_DEX3_SHA
            or dex.get('classes4_sha256') != build_prod_rebase_dex.DEX4_SHA
            or dex.get('classes4_copied_exact_from_production') is not True
            or dex.get('foreign_or_accepted_final_DEX_used_as_build_input') is not False
            or dex.get('comparison', {}).get('classes') != 725
            or dex['comparison'].get('unchanged_classes') != 724
            or dex['comparison'].get('all_other_methods_class_metadata_and_classes_identical') is not True):
        raise ValueError('Finite authentic production-root DEX provenance differs')
    if (loader.get('status') != 'EXACT_ACCEPTED_LOADER_REBUILT'
            or loader.get('loader_sha256') != expected['lib/arm64-v8a/libakfcloader.so']
            or loader.get('opaque_header_read_copied_hashed_or_logged_by_driver') is not False):
        raise ValueError('Accepted opaque-header loader provenance differs')


def build(lock, paths, output):
    verify(lock, paths)
    source_hash, checkout_hash = digest(PROFILE), digest(CHECKOUT)
    disk = shared.physical_output(output)
    output.mkdir(parents=True)
    kit = output / 'private-kit'
    hydrated = shared.hydrate(lock, paths, kit)
    llvm = Path(hydrated['android-sdk/ndk/28.2.13676358/toolchains/llvm/prebuilt/windows-x86_64/bin/clang++.exe']).parent
    core, pins, core_receipt = build_prod_rebase_core.build(hydrated[BASE_ROLE], kit, output / 'core', llvm)
    for role, name in (('semantic/owned/owned_core_pins.h', 'owned_core_pins.h'),
                       ('semantic/song-v9/cli_song_pins.h', 'cli_song_pins.h')):
        if digest(pins / name) != digest(hydrated[role]):
            raise ValueError('Production-root regenerated private pins differ')
        shutil.copy2(pins / name, hydrated[role])
    monitor = final.compile_monitor(kit, hydrated, output / 'monitor')
    normalized, dex_receipt = build_prod_rebase_dex.build(hydrated[BASE_ROLE], hydrated['tools/java-17/bin/java.exe'],
        hydrated['tools/jadx-1.5.6-all.jar'], hydrated['tools/RawDexTool.java'], output / 'prod-dex-normalization')
    # Raw DEX are generated from the actual production APK, never hydrated from old fixtures.
    for name in ('classes3', 'classes4'):
        hydrated['dex/' + name + '-source.dex'] = str(normalized[name + '.dex'])
    base_dex = shared.dex(kit, hydrated, output / 'startup-dex')
    classes3, pacing = build_cap60_dex.build(base_dex['classes3.dex'], Path(hydrated['tools/java-17/bin/java.exe']),
        Path(hydrated['tools/jadx-1.5.6-all.jar']), Path(hydrated['tools/RawDexTool.java']), output / 'pacing-dex', kit / 'pacing')
    classes3, partials = build_bundle_partial_cache.build(classes3,
        Path(hydrated['tools/java-17/bin/java.exe']), Path(hydrated['tools/java-17/bin/javac.exe']),
        Path(hydrated['tools/jadx-1.5.6-all.jar']), Path(hydrated['tools/RawDexTool.java']),
        Path(hydrated['tools/android-build-35/d8.jar']), output / 'bundle-partials-dex', kit / 'bundle-partials')
    loader = build_loader_equivalence.build(json.loads(LOADER_PROFILE.read_bytes()), final.loader_paths(paths), output / 'loader')
    payloads = {'lib/arm64-v8a/libcocos2dcpp.so': core, 'lib/arm64-v8a/libakaineanomaly_monitor.so': monitor,
                'lib/arm64-v8a/libakfcloader.so': output / 'loader/libakfcloader.so',
                'classes3.dex': classes3, 'classes4.dex': base_dex['classes4.dex']}
    expected = expected_payloads(lock)
    validate_provenance(core_receipt, dex_receipt, loader, expected)
    actual = {name: digest(path) for name, path in payloads.items()}
    if actual != expected:
        (output / 'PAYLOAD_MISMATCH.json').write_text(json.dumps({'actual': actual, 'expected': expected}, indent=2) + '\n')
        raise ValueError('Production-root source payload differs; stop before APK')
    before_assets = assetset_identity.verify_apk(hydrated[BASE_ROLE], hydrated['assetset/manifest.json'])
    if before_assets['assetset_sha256'] != lock['assetset_sha256']:
        raise ValueError('Production-root base asset capability differs')
    for row in json.loads(PLAN.read_bytes())['replacements']:
        target = output / 'payload-kit' / row['file']
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(payloads[row['archive_path']], target)
    assembled = build_android_client.build(Path(hydrated[BASE_ROLE]), PLAN, output / 'payload-kit', output / 'unsigned.apk')
    after_assets = assetset_identity.verify_apk(output / 'unsigned.apk', hydrated['assetset/manifest.json'])
    if after_assets['assetset_sha256'] != lock['assetset_sha256']:
        raise ValueError('Production-root unsigned asset capability differs')
    verify(lock, paths)
    if digest(PROFILE) != source_hash or digest(CHECKOUT) != checkout_hash:
        raise ValueError('Production-root source profile changed during build')
    receipt = {'status': 'FIVE_SOURCE_PAYLOADS_AND_UNSIGNED_APK_MATCH', 'release': lock['release'],
        'prod_APK_sha256': build_prod_rebase_core.PROD_APK_SHA, 'payload_sha256': actual,
        'source_lock_sha256': source_hash, 'checkout_map_sha256': checkout_hash,
        'core_provenance': core_receipt, 'DEX_provenance': dex_receipt, 'loader_receipt': loader,
        'pacing_receipt': pacing, 'partial_cache_receipt': partials, 'builder_receipt': assembled,
        'base_assets': before_assets, 'output_assets': after_assets, 'unsigned_apk_sha256': digest(output / 'unsigned.apk'),
        'external_disk': disk, 'signed': False, 'device_or_server_actions': False, 'runtime_accepted': False}
    (output / 'BUILD_RECEIPT.json').write_text(json.dumps(receipt, indent=2) + '\n')
    return receipt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=('verify', 'build'))
    parser.add_argument('--local-paths', type=Path, required=True)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    lock = json.loads(PROFILE.read_bytes())
    paths = bound_paths(lock, json.loads(args.local_paths.read_bytes())['paths'])
    if args.mode == 'verify':
        print(json.dumps({'status': 'PROD_REBASE_SOURCE_INPUTS_AND_PLAN_VERIFIED', 'roles': len(verify(lock, paths)),
                          'opaque_header_accessed': False}))
    else:
        if args.output is None: parser.error('Build requires a fresh physical-D output')
        print(json.dumps(build(lock, paths, args.output)))


if __name__ == '__main__':
    try:
        main()
    except Exception:
        raise SystemExit('Production-root source operation stopped; private compiler diagnostics suppressed') from None
