"""Separate accepted-loader source profile; private header remains opaque."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess

import build_akfc_loader
import build_release_profile

ROOT = Path(__file__).resolve().parents[1]
PROFILE = ROOT / 'patches/arcaea-7.0.255-arm64/staging-loader-v6-equivalence.json'


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def verify(profile, paths):
    if profile['schema'] != 'akaine.loader-equivalence.v1' or profile['environment'] != 'staging':
        raise ValueError('Staging equivalence profile required')
    source = ROOT / profile['source']
    if source.is_symlink() or digest(source) != profile['source_sha256']:
        raise ValueError('Accepted loader source differs')
    compiler, crypto = Path(paths['compiler']), Path(paths['crypto'])
    for path, expected in ((compiler, profile['compiler_driver_sha256']),
                           (compiler.with_name('clang++.exe'), profile['compiler_executable_sha256']),
                           (crypto, profile['static_crypto_archive_sha256'])):
        if path.is_symlink() or not path.is_file() or digest(path) != expected:
            raise ValueError('Pinned nonsecret compiler/crypto input differs')
    if profile['opaque_header_environment_slot'] != 'AKAINE_PRODUCTION_KEY_HEADER':
        raise ValueError('Opaque header environment reference differs')
    return source, compiler, crypto


def tool(arguments):
    try:
        result = subprocess.run([str(value) for value in arguments], capture_output=True, timeout=30)
    except (OSError, subprocess.TimeoutExpired):
        raise RuntimeError('Loader static verification tool failed') from None
    if result.returncode:
        raise RuntimeError('Loader static verification tool failed')
    return result.stdout.decode(errors='replace')


def build(profile, paths, output):
    source, compiler, crypto = verify(profile, paths)
    disk = build_release_profile.physical_output(output)
    value = os.environ.get(profile['opaque_header_environment_slot'])
    if not value:
        raise ValueError('Existing opaque header environment reference is required')
    header = Path(value)
    if header.name != 'embedded_key.h' or header.is_symlink() or not header.is_file():
        raise ValueError('Existing opaque header reference is unavailable')
    if (source.parent / 'embedded_key.h').exists() or (source.parent / 'embedded_key.h').is_symlink():
        raise ValueError('Source-local opaque header would shadow the configured reference')
    try:
        header.resolve().relative_to(ROOT.resolve())
    except ValueError:
        pass
    else:
        raise ValueError('Opaque header must remain outside the source checkout')
    output.mkdir(parents=True)
    loader = output / 'libakfcloader.so'
    build_akfc_loader.build(source, header, crypto, loader, compiler)
    actual = digest(loader)
    llvm = compiler.parent
    symbols = tool([llvm / 'llvm-readelf.exe', '--dyn-syms', '--wide', loader])
    dynamic = tool([llvm / 'llvm-readelf.exe', '-d', loader])
    required = ('Java_low_moe_AkfcLoader_installHooks', 'Java_low_moe_AkfcLoader_wipeDecrypted')
    if (any(name not in symbols for name in required) or 'Java_low_moe_AkfcLoader_decryptFile' in symbols
            or any(' UND ' in line and ('akfc_' in line or 'EVP_' in line) for line in symbols.splitlines())
            or 'libcrypto.so' in dynamic or 'libc++_shared.so' in dynamic):
        raise ValueError('Loader export/static crypto contract differs')
    receipt = {'status': 'EXACT_ACCEPTED_LOADER_REBUILT' if actual == profile['expected_loader_sha256'] else 'SOURCE_EQUIVALENCE_BUILD_IDENTITY_MISMATCH_STOP_BEFORE_APK',
               'profile_sha256': digest(PROFILE), 'source_sha256': digest(source),
               'loader_sha256': actual, 'expected_loader_sha256': profile['expected_loader_sha256'],
               'static_crypto_archive_sha256': digest(crypto), 'compiler_driver_sha256': digest(compiler),
               'opaque_header_reference': profile['opaque_header_environment_slot'],
               'opaque_header_read_copied_hashed_or_logged_by_driver': False,
               'compiler_diagnostics_captured_not_printed_or_saved': True,
               'private_dependency_file': 'libakfcloader.d', 'static_contract_checks': True,
               'external_disk': disk, 'APK_packaged_or_installed': False, 'device_actions': False}
    (output / 'BUILD_RECEIPT.json').write_text(json.dumps(receipt, indent=2) + '\n')
    if actual != profile['expected_loader_sha256']:
        raise ValueError('Loader bytes differ; inspect nonsecret provenance before any APK packaging')
    return receipt


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=('verify', 'build'))
    parser.add_argument('--local-paths', type=Path, required=True)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    try:
        profile = json.loads(PROFILE.read_bytes())
        paths = json.loads(args.local_paths.read_bytes())['paths']
        if args.mode == 'verify':
            verify(profile, paths)
            print(json.dumps({'status': 'SOURCE_AND_NONSECRET_INPUTS_VERIFIED', 'opaque_header_accessed': False}))
        else:
            if args.output is None:
                parser.error('Build requires a fresh physical-D output directory')
            print(json.dumps(build(profile, paths, args.output)))
    except Exception:
        # No paths, command arguments or compiler exception text can escape this entry point.
        raise SystemExit('Loader equivalence operation stopped; private diagnostics suppressed') from None
