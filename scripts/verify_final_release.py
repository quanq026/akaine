"""Verify final source/private inputs and an optional signed staging artifact."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import zipfile

import assetset_identity
import build_final_release_profile as final


def validate_receipts(lock, build, artifact, source_hash, checkout_hash):
    expected = final.expected_payloads(lock)
    unsigned_sha = build.get('unsigned_apk_sha256')
    if (build.get('status') != 'FIVE_SOURCE_PAYLOADS_AND_UNSIGNED_APK_MATCH'
            or build.get('source_lock_sha256') != source_hash or build.get('checkout_map_sha256') != checkout_hash
            or build.get('payload_sha256') != expected
            or not isinstance(unsigned_sha, str) or re.fullmatch('[0-9a-f]{64}', unsigned_sha) is None):
        raise ValueError('Build receipt does not bind this source profile and five payloads')
    signer = lock['signing']['signer_certificate_sha256']
    if (artifact.get('environment') != 'staging' or artifact.get('package') != 'akai.arc.lmao'
            or artifact.get('payloads') != expected or artifact.get('signer_sha256') != signer
            or artifact.get('assembly', {}).get('output_sha256') != unsigned_sha
            or artifact.get('post_sign_assetset_verified', {}).get('assetset_sha256') != lock['assetset_sha256']):
        raise ValueError('Signed artifact receipt differs from the source build or signer/assets')
    return expected, signer


def signed_artifact(apk, artifact, expected, signer, java, apksigner, private_manifest):
    before = apk.stat()
    if apk.is_symlink() or not apk.is_file():
        raise ValueError('Regular signed APK required')
    actual_sha = final.digest(apk)
    if actual_sha != artifact.get('apk_sha256') or before.st_size != artifact.get('bytes'):
        raise ValueError('Signed APK identity differs from its receipt')
    with zipfile.ZipFile(apk) as archive:
        if len(archive.namelist()) != len(set(archive.namelist())):
            raise ValueError('Duplicate signed APK member')
        for name, expected_sha in expected.items():
            with archive.open(name) as stream:
                if hashlib.file_digest(stream, 'sha256').hexdigest() != expected_sha:
                    raise ValueError('Signed APK source payload differs: ' + name)
    result = subprocess.run([str(java), '-jar', str(apksigner), 'verify', '--verbose', '--print-certs', str(apk)],
                            capture_output=True, timeout=60)
    if result.returncode:
        raise ValueError('APK signature verification failed')
    text = (result.stdout + result.stderr).decode(errors='replace')
    certificates = re.findall(r'(?m)^Signer #\d+ certificate SHA-256 digest: ([0-9a-f]{64})\s*$', text)
    if certificates != [signer] or 'Verified using v2 scheme (APK Signature Scheme v2): true' not in text:
        raise ValueError('Actual APK signer or signature scheme differs')
    assets = assetset_identity.verify_apk(apk, private_manifest, actual_sha)
    if assets['assetset_sha256'] != artifact['post_sign_assetset_verified']['assetset_sha256']:
        raise ValueError('Actual signed APK asset capability differs')
    after = apk.stat()
    if (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) != (
            after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns):
        raise ValueError('Signed APK changed during verification')
    return {'apk_sha256': actual_sha, 'bytes': after.st_size, 'payloads_verified': len(expected),
            'signer_certificate_sha256': signer, 'v2_signature_verified': True,
            'assetset_sha256': assets['assetset_sha256'], 'asset_count': assets['asset_count']}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--local-paths', type=Path, required=True)
    parser.add_argument('--build-receipt', type=Path)
    parser.add_argument('--apk', type=Path)
    parser.add_argument('--apk-receipt', type=Path)
    args = parser.parse_args()
    lock = json.loads(final.PROFILE.read_bytes())
    paths = final.bound_paths(lock, json.loads(args.local_paths.read_bytes())['paths'])
    roles = final.verify(lock, paths)
    result = {'status': 'FINAL_SOURCE_INPUTS_VERIFIED', 'roles': len(roles),
              'source_lock_sha256': final.digest(final.PROFILE), 'checkout_map_sha256': final.digest(final.CHECKOUT),
              'opaque_header_accessed': False, 'signed_artifact': None}
    selected = (args.build_receipt, args.apk, args.apk_receipt)
    if any(selected):
        if not all(selected): parser.error('Artifact verification requires build receipt, APK and APK receipt together')
        build = json.loads(args.build_receipt.read_bytes())
        artifact = json.loads(args.apk_receipt.read_bytes())
        expected, signer = validate_receipts(lock, build, artifact, result['source_lock_sha256'], result['checkout_map_sha256'])
        result['signed_artifact'] = signed_artifact(args.apk, artifact, expected, signer,
            Path(paths['tools/java-17/bin/java.exe']), Path(paths['tools/android-build-35/apksigner.jar']),
            Path(paths['assetset/manifest.json']))
        result['status'] = 'FINAL_SOURCE_AND_SIGNED_ARTIFACT_VERIFIED'
    result['device_or_server_actions'] = False
    result['runtime_accepted'] = False
    print(json.dumps(result, indent=2))


if __name__ == '__main__': main()
