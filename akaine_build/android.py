"""Verify and merge the original Arcaea 7.3.1 ARM64 XAPK."""

import argparse
import json
from pathlib import Path, PurePosixPath
import shutil
import stat
import subprocess
import zipfile

from .apk import ROOT, checked_path, sha256_file


EDITOR = (7733037, 'a9cd40df818845456be6d696de6110c89edf4b0a0580cb83438ed6b25a366e67')
XAPK_73 = (1282543787, 'b996a23570e927f907a096da950f4347c818a388fc610a84fd0b8f58a7faa91e')
MERGED_73 = (1270354570, 'c622e705c5818d5773b61ca57bd3ea712e49668e984d38f6ae49003978f6908b')
MODULES_73 = {
    'moe.low.arc.apk': 'base',
    'config.arm64_v8a.apk': 'config.arm64_v8a',
    'config.en.apk': 'config.en',
    'config.xxxhdpi.apk': 'config.xxxhdpi',
    'arcassets.apk': 'arcassets',
}


def prepare_input(source, java, apkeditor, outputdir):
    """Verify and merge the original Arcaea 7.3.1 ARM64 input."""
    xapk, merged, modules = XAPK_73, MERGED_73, MODULES_73
    app_version, version_code = '7.3.1', '1210500'
    metadata = {'manifest.json'}
    source = checked_path(source)
    outputdir = checked_path(outputdir, fresh=True)
    size = source.stat().st_size
    if size not in (xapk[0], merged[0]):
        raise ValueError(f'Use the verified APKPure {app_version} arm64 XAPK or its verified merged APK; a base/split APK alone is incomplete')
    source_hash = sha256_file(source)
    kind = 'xapk' if (size, source_hash) == xapk else 'merged' if (size, source_hash) == merged else None
    if kind is None:
        raise ValueError(f'Input does not match the verified APKPure {app_version} arm64 input')
    if kind == 'xapk':
        java, apkeditor = checked_path(java), checked_path(apkeditor)
        if (apkeditor.stat().st_size, sha256_file(apkeditor)) != EDITOR:
            raise ValueError('APKEditor must match the verified 1.4.9 release')
        with zipfile.ZipFile(source) as archive:
            rows = archive.infolist()
            names = [row.filename for row in rows]
            if len(set(names)) != len(names) or set(names) != set(modules) | metadata:
                raise ValueError('XAPK must contain exactly the verified APK modules and metadata')
            for row in rows:
                path = PurePosixPath(row.filename)
                if (path.is_absolute() or path.as_posix() != row.filename or '..' in path.parts
                        or '\\' in row.filename or ':' in row.filename or row.is_dir()
                        or stat.S_ISLNK(row.external_attr >> 16) or row.flag_bits & 1):
                    raise ValueError('Unsafe XAPK entry')
            manifest_row = archive.getinfo('manifest.json')
            if manifest_row.file_size > 65536:
                raise ValueError('XAPK manifest is too large')
            manifest = json.loads(archive.read(manifest_row))
            if (manifest.get('package_name') != 'moe.low.arc' or manifest.get('version_name') != app_version
                    or str(manifest.get('version_code')) != version_code
                    or manifest.get('split_apks') != [{'file': name, 'id': value} for name, value in modules.items()]
                    or manifest.get('split_configs') != list(modules.values())[1:]):
                raise ValueError('XAPK package/version/split identity differs')
    outputdir.mkdir(parents=True)
    target = outputdir / 'merged.apk'
    if kind == 'merged':
        shutil.copy2(source, target)
    else:
        try:
            result = subprocess.run([str(java), '-Xmx4g', '-jar', str(apkeditor), 'merge',
                                     '-i', str(source), '-o', str(target)], capture_output=True, timeout=180)
        except (OSError, subprocess.TimeoutExpired):
            raise RuntimeError('APKPure merge failed or timed out; private tool diagnostics suppressed') from None
        if result.returncode:
            raise RuntimeError('APKPure merge failed; private tool diagnostics suppressed')
        if (apkeditor.stat().st_size, sha256_file(apkeditor)) != EDITOR:
            raise ValueError('APKEditor changed during input preparation')
    target = checked_path(target)
    if (target.stat().st_size, sha256_file(target)) != merged:
        raise ValueError('Merged APK does not match the verified reference; stop before patching')
    if (source.stat().st_size, sha256_file(source)) != (size, source_hash):
        raise ValueError('Source input changed during preparation')
    return target

def main():
    parser = argparse.ArgumentParser(description='Verify and merge the original Arcaea 7.3.1 ARM64 XAPK.')
    parser.add_argument('--source', type=Path, required=True, help='Original ARM64 XAPK or its verified merge')
    parser.add_argument('--java', type=Path, required=True, help='Java executable')
    parser.add_argument('--apkeditor', type=Path, required=True, help='APKEditor 1.4.9 JAR')
    parser.add_argument('--output', type=Path, required=True, help='New directory outside the repository')
    args = parser.parse_args()
    try:
        if args.output.resolve().is_relative_to(ROOT):
            raise ValueError('Output must remain outside the repository')
        apk = prepare_input(args.source, args.java, args.apkeditor, args.output)
    except (OSError, RuntimeError, ValueError, zipfile.BadZipFile) as error:
        parser.exit(1, f'{error}\n')
    print(f'Verified original APK: {apk}')


if __name__ == '__main__':
    main()
