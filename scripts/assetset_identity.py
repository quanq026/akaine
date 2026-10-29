"""Canonical APK assets identity; file list stays in an operator-owned private kit."""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import struct
import zipfile

SCHEMA = 'akaine.apk-assets.v1'
DOMAIN = SCHEMA.encode('ascii') + b'\0'


def file_sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def canonical_digest(rows):
    result = hashlib.sha256(DOMAIN)
    seen = set()
    for row in sorted(rows, key=lambda row: row['path'].encode('utf-8')):
        name = row['path']
        path = PurePosixPath(name)
        if (not name or name == '.' or path.is_absolute() or path.as_posix() != name or '\\' in name or ':' in name or '\0' in name
                or '..' in path.parts or name in seen or type(row['bytes']) is not int or not 0 <= row['bytes'] <= 0xffffffffffffffff):
            raise ValueError('Unsafe or duplicate APK asset identity row')
        digest = row['sha256']
        if not isinstance(digest, str) or len(digest) != 64 or any(value not in '0123456789abcdef' for value in digest):
            raise ValueError('Asset SHA256 must be exact lowercase hexadecimal')
        seen.add(name)
        encoded = name.encode('utf-8')
        result.update(struct.pack('<I', len(encoded)))
        result.update(encoded)
        result.update(struct.pack('<Q', row['bytes']))
        result.update(bytes.fromhex(digest))
    if not seen:
        raise ValueError('APK asset set is empty')
    return result.hexdigest()


def inspect_apk(path, expected_apk_sha=None):
    path = Path(path)
    before = path.stat()
    if path.is_symlink() or not path.is_file():
        raise ValueError('Regular APK required')
    apk_sha = file_sha(path)
    if expected_apk_sha and apk_sha != expected_apk_sha:
        raise ValueError('Source APK hash differs')
    rows = []
    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()
        if len(names) != len(set(names)):
            raise ValueError('Duplicate APK ZIP member')
        for item in archive.infolist():
            if not item.filename.startswith('assets/') or item.is_dir():
                continue
            with archive.open(item) as stream:
                digest = hashlib.file_digest(stream, 'sha256').hexdigest()
            rows.append({'path': item.filename.removeprefix('assets/'), 'bytes': item.file_size, 'sha256': digest})
    result = canonical_digest(rows)
    after = path.stat()
    if (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) != (
            after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns):
        raise ValueError('APK changed while asset identity was read')
    return {'schema': SCHEMA, 'apk': str(path.resolve()), 'apk_sha256': apk_sha, 'assetset_sha256': result,
            'asset_count': len(rows), 'asset_bytes': sum(row['bytes'] for row in rows),
            'assets': sorted(rows, key=lambda row: row['path'].encode('utf-8'))}


def verify_apk(path, private_manifest, expected_apk_sha=None):
    expected = json.loads(Path(private_manifest).read_bytes())
    if expected['schema'] != SCHEMA or canonical_digest(expected['assets']) != expected['assetset_sha256']:
        raise ValueError('Private asset identity manifest differs')
    actual = inspect_apk(path, expected_apk_sha)
    if (actual['assetset_sha256'] != expected['assetset_sha256'] or actual['assets'] != expected['assets']):
        raise ValueError('APK asset set differs; do not advertise its capability')
    return {key: value for key, value in actual.items() if key != 'assets'}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=('create', 'verify'))
    parser.add_argument('--apk', type=Path, required=True)
    parser.add_argument('--private-manifest', type=Path, required=True)
    parser.add_argument('--expected-apk-sha256')
    args = parser.parse_args()
    if args.mode == 'create':
        if args.private_manifest.exists() or args.private_manifest.drive.upper() != 'D:':
            raise ValueError('Fresh private asset manifest on physical D required')
        result = inspect_apk(args.apk, args.expected_apk_sha256)
        args.private_manifest.parent.mkdir(parents=True, exist_ok=True)
        args.private_manifest.write_text(json.dumps(result, indent=2) + '\n')
        print(json.dumps({key: value for key, value in result.items() if key != 'assets'}))
    else:
        print(json.dumps(verify_apk(args.apk, args.private_manifest, args.expected_apk_sha256)))
