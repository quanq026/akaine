"""Prepare or seal only the production V36 sibling profile and private input map."""
import argparse
import json
from pathlib import Path
import zipfile

import build_production_news_core as core
import build_release_profile as shared

ROOT = Path(__file__).resolve().parents[1]
PATCH = ROOT / 'patches/arcaea-7.0.255-arm64'
PROFILE = PATCH / 'production-news-v36-source-lock.json'
CHECKOUT = PATCH / 'production-news-v36-checkout-sources.json'
PLAN = PATCH / 'production-news-v36-plan.json'
SCRIPTS = ('build_production_news_core.py', 'build_production_news_release.py',
           'build_production_bundle_partial_cache.py', 'prepare_production_news_profile.py',
           'test_production_news_release.py', 'verify_production_news_release.py',
           'test_verify_production_news_release.py')


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + '\n', encoding='utf-8', newline='\n')


def prepare(frozen_kit, private_output, candidate_receipt=None):
    frozen_kit, private_output = map(Path, (frozen_kit, private_output))
    if private_output.drive.upper() != 'D:' or ROOT.resolve() in private_output.resolve().parents:
        raise ValueError('Private output must remain outside the repository on physical D')
    lock = json.loads((PATCH / 'prod-rebase-news-v36-source-lock.json').read_bytes())
    checkout = json.loads((PATCH / 'prod-rebase-news-v36-checkout-sources.json').read_bytes())
    plan = json.loads((PATCH / 'prod-rebase-news-v36-plan.json').read_bytes())
    paths = json.loads((frozen_kit / 'local-paths.json').read_bytes())['paths']
    shared.verify(lock, shared.checkout_paths(lock, paths, checkout, ROOT))
    shared.physical_output(private_output / 'unused-fresh-output-preflight')
    with zipfile.ZipFile(paths['base/prod-v9.apk']) as archive:
        prod = archive.read(core.original.CORE_ENTRY)
    pins = private_output / 'semantic/native/cli_pins.h'
    pins.parent.mkdir(parents=True, exist_ok=True)
    pins.write_text(core.cli_route_pins((frozen_kit / 'semantic/native/cli_pins.h').read_text('utf-8'), prod),
                    encoding='utf-8', newline='\n')
    paths['semantic/native/cli_pins.h'] = str(pins)
    remap = {'semantic/native/staging_cli_bridge.h': 'patches/arcaea-7.0.255-arm64/runtime/semantic/native/production_cli_bridge.h',
             'host-cli/akaine_stag.py': 'scripts/akaine_cli/akaine_prod.py',
             'bundle-partials/AkaineBundlePartialCache.java': 'patches/arcaea-7.0.255-arm64/runtime/bundle-partials-prod/AkaineBundlePartialCache.java',
             'bundle-partials/PartialCacheFixture.java': 'patches/arcaea-7.0.255-arm64/runtime/bundle-partials-prod/PartialCacheFixture.java'}
    for row in checkout['authored_sources']:
        row['repo_path'] = remap.get(row['role'], row['repo_path'])
        paths[row['role']] = str(ROOT / row['repo_path'])
    for name in SCRIPTS:
        role = 'production-v36/source/scripts/' + name
        lock['additional_build_inputs'].append(dict(role=role, sha256='', bytes=0, classification='authored_checkout_source'))
        checkout['authored_sources'].append(dict(role=role, repo_path='scripts/' + name))
        paths[role] = str(ROOT / 'scripts' / name)
    role = 'production-v36/source/scripts/akaine_cli/test_akaine_prod.py'
    lock['additional_build_inputs'].append(dict(role=role, sha256='', bytes=0, classification='authored_checkout_source'))
    checkout['authored_sources'].append(dict(role=role, repo_path='scripts/akaine_cli/test_akaine_prod.py'))
    paths[role] = str(ROOT / 'scripts/akaine_cli/test_akaine_prod.py')
    lock.update(release='production-prod-v9-news-v36', candidate='production-news-v36-20261027',
                content_version='7.0.255.25', status='PRODUCTION_V36_CANDIDATE_CONTROLS_UNACCEPTED')
    lock['limits'] = ['Production routing matches authentic V9 in both native layers.',
        'Accepted V36 source, normal FDE and complete media are preserved; the three unfinished lag areas remain deferred.',
        'No QA timing probes, culling, worker, preload, ANGLE or Vulkan experiments are included.',
        'Production base25 publication and signing are separate operator actions.',
        'Candidate control derivation is unaccepted and cannot assemble an APK.',
        'Opaque loader header remains compiler-only through its existing environment reference.']
    plan.update(environment='production', not_for_production=False, content_version=lock['content_version'])
    if candidate_receipt:
        receipt_path = Path(candidate_receipt)
        receipt = json.loads(receipt_path.read_bytes())
        if (receipt.get('status') != 'UNACCEPTED_CANDIDATE_FIVE_SOURCE_PAYLOADS'
                or receipt.get('prod_APK_sha256') != core.PROD_APK_SHA or receipt.get('APK_assembled') is not False
                or receipt['payload_sha256']['lib/arm64-v8a/libcocos2dcpp.so'] != core.OUTPUT_SHA):
            raise ValueError('Explicit production candidate five-payload receipt required')
        for row in lock['expected_replacements']:
            name = row['role'].removeprefix('final/payload/')
            path = receipt_path.parent / 'payload-kit' / row['role']
            if shared.digest(path) != receipt['payload_sha256'][name]:
                raise ValueError('Candidate control file differs')
            paths[row['role']] = str(path)
            row.update(sha256=receipt['payload_sha256'][name], bytes=path.stat().st_size)
        for row in plan['replacements']:
            row['sha256'] = receipt['payload_sha256'][row['archive_path']]
        lock.update(status='PRODUCTION_V36_CONTROLS_SEALED',
                    control_derivation_receipt_sha256=shared.digest(receipt_path))
    changed_roles = {*remap, 'semantic/native/cli_pins.h',
                     *(row['role'] for row in checkout['authored_sources'] if row['role'].startswith('production-v36/'))}
    for row in shared.manifest_rows(lock):
        if row['role'].startswith('final/payload/'):
            continue
        path = Path(paths[row['role']])
        if row['role'] in changed_roles:
            row.update(sha256=shared.digest(path), bytes=path.stat().st_size)
        elif shared.digest(path) != row['sha256']:
            raise ValueError('Unchanged V36 source/private input differs: ' + row['role'])
    write(PLAN, plan)
    lock['build_plan_sha256'] = shared.digest(PLAN)
    write(PROFILE, lock)
    checkout['source_lock_sha256'] = shared.digest(PROFILE)
    write(CHECKOUT, checkout)
    write(private_output / 'local-paths.json', dict(status='PRIVATE_PRODUCTION_V36_LOCAL_ONLY', paths=paths))
    return dict(status=lock['status'], source_lock_sha256=shared.digest(PROFILE),
                checkout_map_sha256=shared.digest(CHECKOUT), plan_sha256=shared.digest(PLAN),
                private_map_written=True, opaque_header_accessed=False)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--frozen-kit', required=True, type=Path)
    parser.add_argument('--private-output', required=True, type=Path)
    parser.add_argument('--seal-from-candidate-receipt', type=Path)
    args = parser.parse_args()
    print(json.dumps(prepare(args.frozen_kit, args.private_output, args.seal_from_candidate_receipt), indent=2))
