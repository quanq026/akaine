"""Bind sealed production V36 sources, unsigned build and signed APK evidence."""
import argparse
import json
from pathlib import Path
import re
import zipfile

import build_production_news_release as release
import verify_final_release as signed
import verify_prod_rebase_release as preserved


def pinned_verifier_inputs(lock, paths):
    rows = release.engine.shared.manifest_rows(lock)
    bound = {Path(paths[row['role']]).resolve(): row['sha256'] for row in rows}
    for path in (Path(__file__), Path(signed.__file__), Path(preserved.__file__)):
        if bound.get(path.resolve()) != release.digest(path):
            raise ValueError('Active signed verifier is not a pinned production source: ' + path.name)


def validate_receipts(lock, build, artifact, source_hash, checkout_hash):
    if (lock.get('release') != release.RELEASE or lock.get('status') != release.SEALED
            or lock.get('application_version') != '7.0.255' or lock.get('content_version') != '7.0.255.25'):
        raise ValueError('Sealed production V36 source profile required')
    expected = release.expected_payloads(lock)
    unsigned = build.get('unsigned_apk_sha256')
    if (build.get('release') != release.RELEASE
            or build.get('status') != 'FIVE_SOURCE_PAYLOADS_AND_UNSIGNED_APK_MATCH'
            or build.get('prod_APK_sha256') != release.core.PROD_APK_SHA
            or build.get('source_lock_sha256') != source_hash or build.get('checkout_map_sha256') != checkout_hash
            or build.get('payload_sha256') != expected or build.get('APK_assembled') is not True
            or build.get('signed') is not False
            or not isinstance(unsigned, str) or re.fullmatch('[0-9a-f]{64}', unsigned) is None):
        raise ValueError('Unsigned build does not bind the sealed production source and five payloads')
    release.validate_provenance(build.get('core_provenance', {}), build.get('DEX_provenance', {}),
                                build.get('loader_receipt', {}), expected)
    proof = build['core_provenance']['production_route_accounting']
    route_rows = [(row.get('runtime_VA'), row.get('bytes'), row.get('original_sha256'), row.get('staging_sha256'))
                  for row in proof.get('route_spans', [])]
    required = [(hex(address), size, before_sha, release.core.original.sha(staging))
                for address, size, before_sha, staging in release.core.original.ROUTES]
    if route_rows != required:
        raise ValueError('Both production routing layers lack exact source-span provenance')
    partials = build.get('partial_cache_receipt', {})
    if (partials.get('status') != 'AUTHORED_PRODUCTION_PARTIAL_CACHE_DEX_EXACT_REPRODUCTION_PASS'
            or partials.get('candidate_only') is not False
            or partials.get('sealed_expected_sha256') != expected['classes3.dex']
            or partials.get('classes3_sha256') != expected['classes3.dex']
            or partials.get('new_helper_compiled_from_Java') is not True
            or partials.get('compile_adapters_excluded') is not True
            or partials.get('all_reassembled_instruction_and_exception_coverage_equivalent') is not True):
        raise ValueError('Production partial-cache source/output provenance differs')
    if any(build.get(name, {}).get('assetset_sha256') != lock['assetset_sha256']
           for name in ('base_assets', 'output_assets')):
        raise ValueError('Production input/output asset receipts differ')
    certificate = lock['signing']['signer_certificate_sha256']
    if (artifact.get('environment') != 'production' or artifact.get('package') != 'akai.arc.lmao'
            or artifact.get('payloads') != expected or artifact.get('signer_sha256') != certificate
            or artifact.get('assembly', {}).get('output_sha256') != unsigned
            or artifact.get('post_sign_assetset_verified', {}).get('assetset_sha256') != lock['assetset_sha256']):
        raise ValueError('Production signed receipt differs from build, environment, signer or assets')
    return expected, certificate


def actual_routes(base, apk):
    if release.digest(base) != release.core.PROD_APK_SHA:
        raise ValueError('Authentic production V9 APK required for signed routing audit')
    with zipfile.ZipFile(base) as source, zipfile.ZipFile(apk) as candidate:
        prod, current = source.read(release.core.original.CORE_ENTRY), candidate.read(release.core.original.CORE_ENTRY)
    if (release.core.original.sha(prod) != release.core.PROD_CORE_SHA
            or release.core.original.sha(current) != release.core.OUTPUT_SHA):
        raise ValueError('Signed production core or authentic core identity differs')
    for address, size in release.core.ROUTE_PINS:
        a = release.core.original.file_offset(prod, address, size)
        b = release.core.original.file_offset(current, address, size)
        if prod[a:a + size] != current[b:b + size]:
            raise ValueError('Signed visible or encrypted shared API route differs from production V9')
    return dict(visible_and_encrypted_shared_routes_match_authentic_production=True, route_pin_spans=4)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--local-paths', required=True, type=Path)
    parser.add_argument('--build-receipt', type=Path)
    parser.add_argument('--apk', type=Path)
    parser.add_argument('--apk-receipt', type=Path)
    args = parser.parse_args()
    lock = json.loads(release.PROFILE.read_bytes())
    paths = release.bound_paths(lock, json.loads(args.local_paths.read_bytes())['paths'])
    rows = release.verify(lock, paths)
    pinned_verifier_inputs(lock, paths)
    source_hash, checkout_hash = release.digest(release.PROFILE), release.digest(release.CHECKOUT)
    result = dict(status='PRODUCTION_V36_SOURCE_INPUTS_VERIFIED', roles=len(rows),
                  source_lock_sha256=source_hash, checkout_map_sha256=checkout_hash,
                  opaque_header_accessed=False, signed_artifact=None)
    selected = args.build_receipt, args.apk, args.apk_receipt
    if any(selected):
        if not all(selected):
            parser.error('Build receipt, signed APK and artifact receipt are required together')
        build = json.loads(args.build_receipt.read_bytes())
        artifact = json.loads(args.apk_receipt.read_bytes())
        build_hash, artifact_hash = release.digest(args.build_receipt), release.digest(args.apk_receipt)
        expected, certificate = validate_receipts(lock, build, artifact, source_hash, checkout_hash)
        if artifact.get('source_build_receipt_sha256') != build_hash:
            raise ValueError('Signed production artifact is not bound to this exact source build receipt')
        result['signed_artifact'] = signed.signed_artifact(args.apk, artifact, expected, certificate,
            Path(paths['tools/java-17/bin/java.exe']), Path(paths['tools/android-build-35/apksigner.jar']),
            Path(paths['assetset/manifest.json']))
        result['production_routing'] = actual_routes(Path(paths[release.BASE_ROLE]), args.apk)
        result['preserved_production_members'] = preserved.preserved_production_members(
            Path(paths[release.BASE_ROLE]), args.apk, expected)
        if (result['preserved_production_members'] != 5413 or result['signed_artifact']['asset_count'] != 4996
                or release.digest(args.apk) != artifact['apk_sha256']
                or release.digest(Path(paths[release.BASE_ROLE])) != lock['base_apk']['sha256']
                or build_hash != release.digest(args.build_receipt) or artifact_hash != release.digest(args.apk_receipt)):
            raise ValueError('Production asset/member contract or frozen verification input changed')
        result.update(status='PRODUCTION_V36_SOURCE_AND_SIGNED_ARTIFACT_VERIFIED',
                      source_build_receipt_sha256=build_hash, APK_receipt_sha256=artifact_hash)
    release.verify(lock, paths)
    pinned_verifier_inputs(lock, paths)
    if source_hash != release.digest(release.PROFILE) or checkout_hash != release.digest(release.CHECKOUT):
        raise ValueError('Sealed production profile changed during verification')
    result.update(device_or_server_actions=False, runtime_accepted=False)
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
