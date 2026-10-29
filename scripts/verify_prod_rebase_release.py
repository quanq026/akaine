"""Bind production-root source, provenance and an optional signed staging APK."""
import argparse
import json
from pathlib import Path
import zipfile

import build_prod_rebase_release as release
import verify_final_release as signed


def preserved_production_members(base, apk, expected):
    with zipfile.ZipFile(base) as original, zipfile.ZipFile(apk) as candidate:
        if (len(original.namelist()) != len(set(original.namelist()))
                or len(candidate.namelist()) != len(set(candidate.namelist()))):
            raise ValueError('Duplicate production-root APK member')
        names = {name for name in original.namelist() if not release.build_android_client.is_v1_signature(name)}
        current = {name for name in candidate.namelist() if not release.build_android_client.is_v1_signature(name)}
        if names != current or not set(expected) <= names:
            raise ValueError('Production-root APK member set differs')
        preserved = names - set(expected)
        for name in preserved:
            with original.open(name) as left, candidate.open(name) as right:
                if release.build_android_client.sha256_stream(left) != release.build_android_client.sha256_stream(right):
                    raise ValueError('Undeclared production APK member changed: ' + name)
    return len(preserved)


def validate_receipts(lock, build, artifact, source_hash, checkout_hash):
    if (build.get('release') != 'staging-prod-v9-rebase'
            or build.get('prod_APK_sha256') != release.build_prod_rebase_core.PROD_APK_SHA):
        raise ValueError('Build receipt lacks authentic production-root release identity')
    expected = release.expected_payloads(lock)
    release.validate_provenance(build.get('core_provenance', {}), build.get('DEX_provenance', {}),
                                build.get('loader_receipt', {}), expected)
    if (build.get('base_assets', {}).get('assetset_sha256') != lock['assetset_sha256']
            or build.get('output_assets', {}).get('assetset_sha256') != lock['assetset_sha256']):
        raise ValueError('Production-root input/output asset receipts differ')
    return signed.validate_receipts(lock, build, artifact, source_hash, checkout_hash)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--local-paths', type=Path, required=True)
    parser.add_argument('--build-receipt', type=Path)
    parser.add_argument('--apk', type=Path)
    parser.add_argument('--apk-receipt', type=Path)
    args = parser.parse_args()
    lock = json.loads(release.PROFILE.read_bytes())
    paths = release.bound_paths(lock, json.loads(args.local_paths.read_bytes())['paths'])
    rows = release.verify(lock, paths)
    release.verify_active_inputs(lock, paths, (Path(__file__), Path(signed.__file__)))
    source_hash, checkout_hash = release.digest(release.PROFILE), release.digest(release.CHECKOUT)
    result = {'status': 'PROD_REBASE_SOURCE_INPUTS_VERIFIED', 'roles': len(rows),
              'source_lock_sha256': source_hash, 'checkout_map_sha256': checkout_hash,
              'opaque_header_accessed': False, 'signed_artifact': None}
    selected = (args.build_receipt, args.apk, args.apk_receipt)
    if any(selected):
        if not all(selected): parser.error('Build receipt, APK and artifact receipt are required together')
        build = json.loads(args.build_receipt.read_bytes())
        artifact = json.loads(args.apk_receipt.read_bytes())
        expected, certificate = validate_receipts(lock, build, artifact, source_hash, checkout_hash)
        if artifact.get('source_build_receipt_sha256') != release.digest(args.build_receipt):
            raise ValueError('Signed artifact is not bound to this exact production-root build receipt')
        result['signed_artifact'] = signed.signed_artifact(args.apk, artifact, expected, certificate,
            Path(paths['tools/java-17/bin/java.exe']), Path(paths['tools/android-build-35/apksigner.jar']),
            Path(paths['assetset/manifest.json']))
        result['preserved_production_members'] = preserved_production_members(
            Path(paths[release.BASE_ROLE]), args.apk, expected)
        if release.digest(args.apk) != artifact['apk_sha256'] or release.digest(Path(paths[release.BASE_ROLE])) != lock['base_apk']['sha256']:
            raise ValueError('Production base or signed APK changed during preservation verification')
        result['status'] = 'PROD_REBASE_SOURCE_AND_SIGNED_ARTIFACT_VERIFIED'
    release.verify(lock, paths)
    release.verify_active_inputs(lock, paths, (Path(__file__), Path(signed.__file__)))
    if source_hash != release.digest(release.PROFILE) or checkout_hash != release.digest(release.CHECKOUT):
        raise ValueError('Production-root profile changed during verification')
    result.update(device_or_server_actions=False, runtime_accepted=False)
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
